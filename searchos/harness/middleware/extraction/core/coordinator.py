"""证据抽取生命周期：接收、调度、结算与提交协调。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Literal

from searchos.harness.middleware.extraction.core.models import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionProgress,
    ExtractionReceipt,
    ExtractionReport,
    ExtractionSummary,
)
from searchos.harness.middleware.extraction.core.source_windows import (
    ObservationPreparer,
    OriginalWindowPreparer,
)
from searchos.harness.middleware.extraction.core.store import EvidenceStore, WorkspaceEvidenceStore
from searchos.harness.middleware.extraction.core.tables.conflicts import ConflictReviewer
from searchos.harness.middleware.extraction.core.tables.evidence import ingest_facts, ingest_rows
from searchos.harness.middleware.extraction.core.tables.rows import RowExtractor
from searchos.harness.middleware.extraction.core.tables.targets import (
    capture_task_targets,
    restrict_task_rows,
    route_observations,
)
from searchos.harness.middleware.models import TaskContext
from searchos.socm.evidence import EvidenceStatus

logger = logging.getLogger(__name__)


def _source_hashes(items: list[dict[str, Any]]) -> set[str]:
    return {
        key for item in items
        for key in item.get("content_hashes", ()) or [item.get("content_hash", "")]
        if key
    }


def _schema_definition(schema: Any) -> dict[str, Any]:
    return schema.model_dump(mode="json", exclude={"entities", "entity_aliases", "removed_entities"})


class ExtractionCoordinator:
    """管理观察批次、并发抽取、逐来源结算和原子提交。"""

    def __init__(
        self,
        judge_model: Any,
        store: EvidenceStore | None = None,
        trajectory_logger: Any = None,
        batch_n: int = 5,
        config: ExtractionConfig | None = None,
        commit_rows: Callable | None = None,
        preparer: ObservationPreparer | None = None,
        *,
        workspace: Any = None,
        task: TaskContext = TaskContext(),
        policy: Literal["task_rows", "schema_facts"] = "task_rows",
    ) -> None:
        if policy not in {"task_rows", "schema_facts"}:
            raise ValueError(f"Unknown extraction policy: {policy}")
        if (store is None) == (workspace is None):
            raise ValueError("Provide exactly one of workspace or store")
        self.workspace = workspace
        self.task = task
        self._store = store if store is not None else WorkspaceEvidenceStore(workspace)
        self._commit_rows = commit_rows or (
            ingest_facts if policy == "schema_facts" else ingest_rows
        )
        self._trajectory_logger = trajectory_logger
        self._config = config or ExtractionConfig()
        preparer_type = OriginalWindowPreparer if policy == "schema_facts" else ObservationPreparer
        self._preparer = preparer or preparer_type(self._config, trajectory_logger)
        self._extractor = RowExtractor(judge_model, self._config, trajectory_logger)
        self._conflicts = (
            ConflictReviewer(
                self._store, self._extractor.invoke, trajectory_logger=trajectory_logger
            )
            if judge_model is not None else None
        )
        self._finalizing = False
        self._comparison_tasks: set[asyncio.Task] = set()
        self._deferred_comparison_keys: set[str] = set()

        # Node ids this instance committed. One instance per sub-agent, so it's
        # the authoritative per-agent extraction tally the completion report
        # reads instead of a concurrency-polluted global pre/post graph diff.
        self._added_node_ids: set[str] = set()
        self._progress = ExtractionProgress()

        self._extracted_content_hashes: set[str] = set()

        # batch_n is the buffer threshold that triggers a background flush
        # spawn — NOT a judge-call batch size. RowExtractor caps actual calls;
        # this semaphore separately bounds active batches.
        self._batch_n = max(1, int(batch_n))
        self._pending_buffer: list[dict[str, Any]] = []
        self._flush_semaphore: asyncio.Semaphore = asyncio.Semaphore(self._config.flush_concurrency)
        self._flush_tasks: set[asyncio.Task] = set()
        self._background_flush_errors: list[Exception] = []
        self._buffer_lock: asyncio.Lock = asyncio.Lock()
        self._flush_in_flight_count: int = 0
        self._report_pending()

        self._pending_feedback: list[str] = []
        self._accepted_count = 0
        self._duplicate_count = 0
        self._retry_items: dict[str, dict[str, Any]] = {}
        factory = getattr(self._store, "observation_journal", None)
        owner = json.dumps([policy, task.task_id or task.agent_id or "default"])
        self._journal = factory(owner) if callable(factory) else None
        self._recovered: list[dict[str, Any]] = []
        if self._journal is not None:
            for record in self._journal.load():
                self._extracted_content_hashes.add(record["content_hash"])
                if record["status"] != "done":
                    item = record["item"]
                    item.pop("result_mode", None)
                    self._recovered.append(item)
        self._report_pending()

    @property
    def committed_node_ids(self) -> frozenset[str]:
        """本 Extraction 实例提交的节点，用于并发 Agent 归因。"""
        return frozenset(self._added_node_ids)

    @property
    def progress(self) -> ExtractionProgress:
        return self._progress

    def _record_settlement(self, reports: list[ExtractionReport]) -> None:
        completed = [report for report in reports if report.status != "skipped"]
        productive = any(
            report.committed_nodes or report.evidence_links_added or report.cells_filled
            for report in completed
        )
        if not completed or (not productive and any(not report.succeeded for report in completed)):
            return
        self._progress = ExtractionProgress(
            settled_batches=self._progress.settled_batches + 1,
            consecutive_empty_batches=(
                0 if productive else self._progress.consecutive_empty_batches + 1
            ),
        )

    def summary(self) -> ExtractionSummary:
        return ExtractionSummary(
            accepted=self._accepted_count,
            duplicates=self._duplicate_count,
            committed_node_ids=self.committed_node_ids,
            buffered=len(self._pending_buffer) + len(self._retry_items) + len(self._recovered),
            in_flight=self._flush_in_flight_count,
        )

    def _accept(self, observation: EvidenceObservation, state: Any) -> dict | ExtractionReceipt:
        """在缓冲锁内登记可抽取内容，重复或过短时返回回执。"""
        content = observation.content or ""
        import hashlib

        task = next((q for q in state.frontier.questions if q.id == observation.task_id), None)
        target_table = observation.target_table or (task.table_id if task else "")
        if not content.strip() or (state.coverage_map.tables and len(content) < 50):
            return ExtractionReceipt(accepted=False, reason="content_too_short")
        item = {
            "content": content,
            "source_url": observation.source_url,
            "source_urls": [observation.referring_page[0]] if observation.referring_page else list(observation.source_urls),
            "referring_page": observation.referring_page,
            "page_id": observation.page_id,
            "target_table": target_table,
            "task_id": observation.task_id,
            "task_text": observation.task_text
            or (task.task_prompt or task.question if task else state.intent),
            "local_source_metadata": observation.local_source_metadata,
            "source_kind": str(observation.source_kind),
            "linked_records": list(observation.linked_records),
        }
        item = capture_task_targets(state, item)
        schemas = {tid: _schema_definition(schema)
                   for tid, schema in state.coverage_map.tables.items()
                   if not target_table or tid == target_table}
        identity = json.dumps([
            observation.source_url, observation.task_id, target_table,
            ObservationPreparer._strip_extraction_noise(content).strip(),
            schemas, sorted(item["task_target_cells"]), item["task_text"],
            item["source_urls"], observation.referring_page, observation.linked_records,
        ], ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
        item["content_hash"] = content_hash
        if content_hash in self._extracted_content_hashes:
            self._duplicate_count += 1
            return ExtractionReceipt(accepted=False, duplicate=True, reason="duplicate_content")
        if self._journal is not None:
            self._journal.write(item, "pending")
        self._retry_items.pop(content_hash, None)
        self._extracted_content_hashes.add(content_hash)
        self._accepted_count += 1
        return item

    async def submit(
        self,
        observation: EvidenceObservation,
        *,
        delivery: DeliveryMode = DeliveryMode.BUFFERED,
    ) -> ExtractionReceipt:
        """接收 Observation；同步模式返回本次提交的 EvidenceNode。"""
        flushes: list[tuple[str, list[dict[str, Any]]]] = []
        async with self._buffer_lock:
            item = self._accept(observation, self._store.load_state())
            if isinstance(item, ExtractionReceipt):
                if item.duplicate:
                    return replace(item, feedback=self._take_feedback())
                return item
            if delivery is DeliveryMode.BUFFERED:
                # Keep one source URL per pending batch.  When the agent moves
                # to a new URL, freeze the completed source batch for
                # extraction and start a fresh buffer with the new page.
                # Snapshot under the lock so a concurrent submit cannot leak
                # the new URL into the old extraction call.
                if self._pending_buffer and self._pending_buffer[-1].get("source_url") != item.get(
                    "source_url"
                ):
                    flushes.append(("url_switch", list(self._pending_buffer)))
                    self._pending_buffer.clear()
                self._pending_buffer.append(item)
                if len(self._pending_buffer) >= self._batch_n:
                    flushes.append(("buffer_full", list(self._pending_buffer)))
                    self._pending_buffer.clear()

        if delivery is DeliveryMode.SYNC:
            nodes, reports = await self._extract_sync(
                item,
                observation.source_url,
                reason="sync_submit",
            )
            return ExtractionReceipt(
                accepted=True,
                committed_nodes=tuple(nodes),
                reason="extraction_failed" if any(not r.succeeded for r in reports) else "",
                feedback=self._take_feedback(),
                extraction_reports=tuple(reports),
            )

        self._report_pending()
        for reason, snapshot in flushes:
            self._spawn_background_flush(reason, snapshot=snapshot)
        return ExtractionReceipt(accepted=True, feedback=self._take_feedback())

    async def submit_exec(self, observations: list[EvidenceObservation]) -> str:
        """兼容来源有界合批，整次编排只结算一次进展。"""
        async with self._buffer_lock:
            state = self._store.load_state()
            batch = []
            for observation in observations:
                item = self._accept(observation, state)
                if isinstance(item, dict):
                    batch.append(item)
            if batch:
                if self._pending_buffer:
                    pending, self._pending_buffer = self._pending_buffer, []
                    self._spawn_background_flush("url_switch", snapshot=pending)
                self._spawn_background_flush("exec", snapshot=batch)
        return self._take_feedback()

    def _take_feedback(self) -> str:
        feedback = "\n".join(item for item in self._pending_feedback if item)
        self._pending_feedback.clear()
        return feedback

    async def await_idle(self, timeout: float = 5.0) -> int:
        """Block until in-flight background flushes complete (or timeout).
        Returns the number of tasks still pending. Best-effort: never raises."""
        if not self._flush_tasks:
            return 0
        pending = list(self._flush_tasks)
        try:
            done, still_pending = await asyncio.wait(pending, timeout=timeout)
        except Exception:
            logger.warning("ExtractionCoordinator.await_idle: asyncio.wait raised", exc_info=True)
            return len(self._flush_tasks)
        if still_pending:
            logger.warning(
                "ExtractionCoordinator.await_idle: %d/%d tasks pending after %.1fs",
                len(still_pending),
                len(pending),
                timeout,
            )
        return len(still_pending)

    async def drain_before_model(self) -> ExtractionSummary:
        """等待已触发的抽取完成；未满且未切 URL 的缓冲留待后续观察。"""
        if self._recovered:
            from searchos.config.settings import settings

            recovered, self._recovered = self._recovered, []
            self._flush_in_flight_count += len(recovered)
            recovery_deadline = asyncio.timeout(settings.extraction_finalize_timeout_s)
            try:
                async with recovery_deadline:
                    self._record_settlement(await self._run_snapshot(recovered, reason="recovery"))
            except TimeoutError:
                if not recovery_deadline.expired():
                    raise
                self._retain_failed(recovered, "recovery_timeout")
                self._pending_feedback.append(
                    """[Extraction feedback] Recovery timed out; observations remain saved for an extraction retry. Continue with committed evidence and assess remaining gaps."""
                )
            finally:
                self._flush_in_flight_count -= len(recovered)
                self._report_pending()
        while True:
            if self._flush_tasks:
                done, _ = await asyncio.wait(list(self._flush_tasks))
                self._flush_tasks.difference_update(done)
                for task in done:
                    task.result()
            if self._background_flush_errors:
                errors, self._background_flush_errors = self._background_flush_errors, []
                raise RuntimeError("Background evidence extraction failed") from errors[0]
            if not self._flush_tasks:
                return self.summary()

    async def flush(self, *, reason: str = "explicit") -> ExtractionSummary:
        """同步提交当前缓冲。"""
        await self._flush_pending(reason=reason)
        return self.summary()

    async def finalize(self, *, timeout: float = 30.0) -> ExtractionSummary:
        """有界收尾；抽取超时保留观测，存储异常和外部取消继续传播。"""
        deadline = asyncio.get_running_loop().time() + timeout
        self._finalizing = True
        # 核验不占用证据提交的收尾时间；已启动的抽取仍须结算。
        for task in tuple(self._comparison_tasks):
            task.cancel()
        settlement = asyncio.timeout_at(deadline)
        deferred_reason = "extraction_failed"
        try:
            try:
                async with settlement:
                    await self.drain_before_model()
                    await self.flush(reason="finalize")
            except TimeoutError:
                if not settlement.expired():
                    raise
                pending = tuple(self._flush_tasks)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                # _run_snapshot 已保存被取消的观测。尚未开始的缓冲仍在 journal。
                deferred_reason = "finalize_timeout"
                if self._background_flush_errors:
                    errors, self._background_flush_errors = self._background_flush_errors, []
                    raise RuntimeError("Background evidence extraction failed") from errors[0]
            keys = set(self._deferred_comparison_keys)
            if self._conflicts is not None and keys:
                try:
                    async with asyncio.timeout_at(deadline):
                        await self._conflicts.review(keys)
                except TimeoutError:
                    # SOCM 保留 conflict_status=pending；后续调度核验可恢复。
                    # 核验结果延后处理；外部取消仍向上传播。
                    if self._trajectory_logger:
                        self._trajectory_logger._append_raw({
                            "type": "harness", "kind": "evidence_comparison_deferred",
                            "agent": self.task.agent_id, "reason": "finalize_timeout",
                            "cell_keys": sorted(keys),
                        })
                else:
                    self._deferred_comparison_keys.difference_update(keys)
            summary = self.summary()
            if summary.buffered and self._trajectory_logger:
                self._trajectory_logger._append_raw({
                    "type": "harness", "kind": "evidence_extraction_deferred",
                    "agent": self.task.agent_id, "reason": deferred_reason,
                    "observations": summary.buffered,
                })
            return summary
        finally:
            self._finalizing = False
            self._store.report_extraction_pending(self, 0)

    async def _review_conflicts(self, keys: set[str]) -> None:
        if self._conflicts is None or not keys:
            return
        if self._finalizing:
            self._deferred_comparison_keys.update(keys)
            return
        task = asyncio.create_task(self._conflicts.review(keys))
        self._comparison_tasks.add(task)
        try:
            await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if not self._finalizing or (current is not None and current.cancelling()):
                raise
            self._deferred_comparison_keys.update(keys)
        finally:
            self._comparison_tasks.discard(task)

    def _spawn_background_flush(
        self,
        reason: str,
        *,
        snapshot: list[dict[str, Any]],
    ) -> None:
        """Fire-and-forget one frozen batch; semaphore caps judge concurrency.

        ``submit`` passes an exact snapshot for URL and size boundaries.
        """
        if not snapshot:
            return

        queued = {item["content_hash"]: item for item in snapshot}
        self._flush_in_flight_count += len(queued)
        self._report_pending()

        async def _extract(batch):
            try:
                async with self._flush_semaphore:
                    for item in batch:
                        queued.pop(item["content_hash"])
                    try:
                        return await self._run_snapshot(batch, reason=reason)
                    finally:
                        self._flush_in_flight_count -= len(batch)
                        self._report_pending()
            except Exception as exc:  # noqa: BLE001
                self._background_flush_errors.append(exc)
                logger.warning(
                    "Background extraction flush failed (reason=%s)",
                    reason,
                    exc_info=True,
                )
                return [ExtractionReport(status="failed", succeeded=False)]
        def _finished(task):
            self._flush_tasks.discard(task)
            if queued:
                # 编排在获得并发槽之前取消；这些来源仍在 journal，可单独重试。
                self._retry_items.update(queued)
                self._extracted_content_hashes.difference_update(queued)
                self._flush_in_flight_count -= len(queued)
                self._report_pending()

        async def _run() -> None:
            if reason == "exec":
                batches = self._preparer.pack_items(snapshot)
                results = await asyncio.gather(*(_extract(batch) for batch in batches))
                reports = [report for group in results for report in group]
            else:
                reports = await _extract(snapshot)
            self._record_settlement(reports)

        task = asyncio.create_task(_run())
        self._flush_tasks.add(task)
        task.add_done_callback(_finished)

    async def _extract_sync(
        self,
        item: dict[str, Any],
        source_url: str,
        *,
        reason: str,
    ) -> tuple[list[Any], list[ExtractionReport]]:
        """同步抽取单条观测，返回本来源新增或新关联的证据及报告。

        此路径服务于 SYNC 回执，不与后台阅读批次混合；执行期间计入待完成量。
        """
        self._flush_in_flight_count += 1
        self._report_pending()
        try:
            before = self._store.load_state()
            pre = {n.id for n in before.evidence_graph.nodes}
            task_id = item.get("task_id", "")
            previous_bindings = {
                b.evidence_id for b in before.evidence_graph.task_bindings if b.task_id == task_id
            }
            async with self._flush_semaphore:
                reports = await self._run_snapshot([item], reason=reason)
            self._record_settlement(reports)
            after = self._store.load_state()
            attached = {
                b.evidence_id for b in after.evidence_graph.task_bindings if b.task_id == task_id
            } - previous_bindings
            return [
                n
                for n in after.evidence_graph.nodes
                if n.status == EvidenceStatus.ACTIVE and (n.id not in pre or n.id in attached)
                and n.source == source_url
            ], reports
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Synchronous skill extraction failed (reason=%s)",
                reason,
                exc_info=True,
            )
            return [], [
                ExtractionReport(
                    status="failed",
                    succeeded=False,
                    warnings=(f"{type(exc).__name__}: {exc}",),
                )
            ]
        finally:
            self._flush_in_flight_count -= 1
            self._report_pending()

    def _report_pending(self) -> None:
        """Publish in-flight count (buffered + snapshotted-but-not-yet-written)
        so LoopSensor mode-5 doesn't declare stall mid-flush."""
        try:
            total = (
                len(self._pending_buffer)
                + self._flush_in_flight_count
                + len(getattr(self, "_recovered", []))
            )
            self._store.report_extraction_pending(self, total)
        except Exception:  # noqa: BLE001
            pass

    async def _flush_pending(self, *, reason: str) -> None:
        """取出剩余与失败批次；失败时保留原始观测，允许下一次显式结算重试。"""
        async with self._buffer_lock:
            combined = {item["content_hash"]: item for item in self._pending_buffer}
            if reason != "finalize":
                combined.update(self._retry_items)
                self._retry_items.clear()
            snapshot = list(combined.values())
            self._pending_buffer.clear()
        if snapshot:
            self._flush_in_flight_count += len(snapshot)
            try:
                self._record_settlement(await self._run_snapshot(snapshot, reason=reason))
            finally:
                self._flush_in_flight_count -= len(snapshot)
                self._report_pending()
        self._report_pending()

    async def _run_snapshot(self, snapshot, *, reason):
        """执行及结算持久记录；取消或异常不能使已接收观测凭空消失。"""
        tracked = [{**item, "_extraction_result": {
            "pending": None, "failed": False, "produced": False,
        }} for item in snapshot]
        try:
            reports = await self._flush_snapshot(tracked, reason=reason)
            failed = set().union(*(set(report.failed_hashes) for report in reports))
            produced = set().union(*(set(report.produced_hashes) for report in reports))
            for item in tracked:
                outcome = item["_extraction_result"]
                if outcome["pending"] is None:
                    outcome["failed"] = item["content_hash"] in failed or any(
                        not report.succeeded and not report.failed_hashes for report in reports
                    )
                    outcome["produced"] = item["content_hash"] in produced or any(
                        not report.produced_hashes and (report.extracted_rows or report.committed_nodes)
                        for report in reports
                    )
                if outcome["failed"] or outcome["pending"]:
                    self._retain_failed([item], "extraction_failed")
                else:
                    self._settle_source(item, outcome["produced"])
            if any(item["_extraction_result"]["failed"] for item in tracked):
                self._pending_feedback.append(
                    "[Extraction feedback] Some sources remain saved for an extraction retry. "
                    "Successfully processed sources have been settled."
                )
            return reports
        except BaseException as exc:
            for item in tracked:
                outcome = item["_extraction_result"]
                if outcome["pending"] == set() and not outcome["failed"]:
                    # 已完成来源保留结算；同包的取消或后续失败只恢复未完成来源。
                    try:
                        self._settle_source(item, outcome["produced"])
                        continue
                    except Exception:
                        pass
                self._retain_failed([item], f"{type(exc).__name__}: {exc}")
            raise
        finally:
            self._report_pending()

    def _retain_failed(self, snapshot, error):
        for item in snapshot:
            item = {k: v for k, v in item.items() if k != "_extraction_result"}
            key = item["content_hash"]
            self._retry_items[key] = item
            # No automatic infinite retry loop: retain for explicit flush or
            # restart, and allow the caller to resubmit the original viewport.
            self._extracted_content_hashes.discard(key)
            if self._journal is not None:
                self._journal.write(item, "failed", error=error)

    def _settle_source(self, item, produced):
        item = {k: v for k, v in item.items() if k != "_extraction_result"}
        key = item["content_hash"]
        self._retry_items.pop(key, None)
        if produced:
            if self._journal is not None:
                self._journal.write(item, "done")
            self._extracted_content_hashes.add(key)
        else:
            if self._journal is not None:
                self._journal.discard(item)
            self._extracted_content_hashes.discard(key)

    @staticmethod
    def _finish_sources(items, table_id, *, failed=(), produced=()):
        for item in items:
            outcomes = item.get("_extraction_results", [])
            if not outcomes and item.get("_extraction_result") is not None:
                outcomes = [(key, item["_extraction_result"]) for key in _source_hashes([item])]
            for key, outcome in outcomes:
                outcome["failed"] |= key in failed
                outcome["produced"] |= key in produced
                if outcome["pending"] is not None:
                    outcome["pending"].discard(table_id)

    async def _flush_snapshot(self, snapshot, *, reason):
        # Schema is authoritative at extraction time, including observations
        # buffered before schema creation. Preserve the originating task ID.
        state = self._store.load_state()
        snapshot = [capture_task_targets(state, item) for item in snapshot]
        snapshot, rejected = route_observations(state, snapshot)
        for item in snapshot:
            outcome = item.get("_extraction_result")
            if outcome is not None:
                if outcome["pending"] is None:
                    outcome["pending"] = set()
                tid = item.get("target_table", "")
                outcome["pending"].add(tid)
                if tid and not item.get("all_schema_targets"):
                    outcome["pending"].update(self._related_backfill_tables(state, tid))
        for item, table_id in rejected:
            if outcome := item.get("_extraction_result"):
                outcome["failed"] = True
                outcome["pending"] = set()
            self._pending_feedback.append(
                f"""Target table {table_id!r} no longer exists; select an existing schema."""
            )
        groups = {}
        for item in snapshot:
            key = (
                item.get("task_id", ""),
                item.get("target_table", ""),
                tuple(sorted(item.get("task_target_cells", ()))),
                item.get("task_target_table", ""),
            )
            groups.setdefault(key, []).append(item)
        reports = [
            ExtractionReport(
                table_id=table_id,
                status="failed",
                succeeded=False,
                warnings=("target_table_missing",),
                failed_hashes=tuple(_source_hashes([_item])),
            )
            for _item, table_id in rejected
        ]
        for group in groups.values():
            try:
                reports.extend(await self._flush_group(group, reason=reason))
            except ValueError as exc:
                if not str(exc).startswith("extraction_input_exceeds_budget:"):
                    raise
                failed = _source_hashes(group)
                self._finish_sources(group, group[0].get("target_table", ""), failed=failed)
                reports.append(ExtractionReport(
                    table_id=group[0].get("target_table", ""), status="failed", succeeded=False,
                    warnings=(str(exc),), failed_hashes=tuple(sorted(failed)),
                ))
        return reports

    async def _flush_group(
        self,
        snapshot: list[dict[str, Any]],
        *,
        reason: str,
    ) -> list[ExtractionReport]:
        """Extract a buffer snapshot via per-page concurrent judge calls.
        Caller owns the snapshot; this method must NOT touch _pending_buffer."""
        if not snapshot:
            return []

        target_tid = snapshot[0]["target_table"]
        if not target_tid:
            from searchos.harness.middleware.extraction.core.findings import extract_and_commit

            items = self._preparer.original_windows(snapshot)
            new_ids: set[str] = set()
            failed, produced = set(), set()
            succeeded = True
            windows = [item for chunk in self._preparer.chunk_items(items) for item in chunk]
            remaining = Counter(key for item in windows for key in _source_hashes([item]))
            for item in windows:
                hashes = _source_hashes([item])
                try:
                    ids = await extract_and_commit(
                        [item], store=self._store, invoke=self._extractor.invoke,
                    )
                    new_ids.update(set(ids) - self._added_node_ids)
                    self._added_node_ids.update(ids)
                    if ids:
                        produced.update(hashes)
                except Exception:
                    succeeded = False
                    failed.update(hashes)
                    logger.warning("Findings extraction failed for %s",
                                   item.get("source_url"), exc_info=True)
                remaining.subtract(hashes)
                completed = [raw for raw in snapshot if all(
                    remaining[key] == 0 for key in _source_hashes([raw])
                )]
                self._finish_sources(completed, "", failed=failed, produced=produced)
            return [
                ExtractionReport(
                    committed_nodes=len(new_ids),
                    status="complete" if new_ids else "empty",
                    succeeded=succeeded,
                    failed_hashes=tuple(sorted(failed)),
                    produced_hashes=tuple(sorted(produced)),
                )
            ]
        items = self._preparer.prepare_pages(snapshot)
        if not items:
            self._finish_sources(snapshot, target_tid)
            return []
        outcomes = {item["content_hash"]: item["_extraction_result"]
                    for item in snapshot if "_extraction_result" in item}
        for item in items:
            item["_extraction_results"] = [(key, outcomes[key])
                                           for key in _source_hashes([item]) if key in outcomes]
        state = self._store.load_state()
        schema = state.coverage_map.tables.get(target_tid)
        if schema is None:
            failed = _source_hashes(snapshot)
            self._finish_sources(snapshot, target_tid, failed=failed)
            return [ExtractionReport(table_id=target_tid, status="failed", succeeded=False,
                                     warnings=("target_table_missing",),
                                     failed_hashes=tuple(sorted(failed)))]

        if self._trajectory_logger:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "extraction_flush",
                    "reason": reason,
                    "items": len(items),
                }
            )

        pre_evidence_ids = {n.id for n in state.evidence_graph.nodes}
        reports: list[ExtractionReport] = []

        if getattr(schema, "primary_key", None):
            backfill = (
                []
                if any(item.get("all_schema_targets") for item in items)
                else self._related_backfill_tables(state, schema.table_id)
            )
            if backfill and self._trajectory_logger:
                self._trajectory_logger._append_raw(
                    {
                        "type": "harness",
                        "kind": "cross_table_backfill",
                        "target_table": schema.table_id,
                        "backfill_tables": backfill,
                        "items": len(items),
                    }
                )
            for table_id in [schema.table_id, *backfill]:
                report = await self._extract_and_ingest_table(items, table_id)
                reports.append(report)
                failed = report.failed_hashes or (
                    _source_hashes(snapshot) if not report.succeeded else ()
                )
                produced = report.produced_hashes or (
                    _source_hashes(snapshot) if report.extracted_rows or report.committed_nodes else ()
                )
                self._finish_sources(snapshot, table_id, failed=failed, produced=produced)
        else:
            self._finish_sources(snapshot, target_tid)

        if feedback := self._build_feedback(pre_evidence_ids):
            self._pending_feedback.append(feedback)
        return reports

    def _related_backfill_tables(self, state: Any, tid: str) -> list[str]:
        """Relation-linked tables to extract from the same pages as ``tid``
        — a table the orchestrator never targets still gets fed (its rows
        grow via discover-mode / orphan promotion). Runs for the whole
        session regardless of how filled the linked table is: pages keep
        carrying cross-table facts after the row set stabilizes, and the
        ingest-time dedup absorbs re-extraction of known values."""
        if not self._config.cross_table_backfill or not tid:
            return []
        cmap = state.coverage_map
        linked: list[str] = []
        for rel in cmap.relations:
            other = ""
            if rel.from_table == tid:
                other = rel.foreign_key.target_table
            elif rel.foreign_key.target_table == tid:
                other = rel.from_table
            if other and other != tid and other not in linked:
                linked.append(other)
        return [
            other
            for other in linked
            if (schema := cmap.tables.get(other)) is not None
            and schema.attributes
            and schema.primary_key
        ]

    async def _extract_and_ingest_table(
        self,
        items: list[dict[str, Any]],
        tid: str,
    ) -> ExtractionReport:
        """冻结任务起始分区，模型调用并发执行，提交时复核最新约束。"""
        if not tid:
            return ExtractionReport(status="skipped", warnings=("missing table_id",))
        chunks = self._preparer.chunk_items(items)
        all_bundles: list[tuple] = []
        all_extracted_rows: list[dict[str, Any]] = []
        all_rejected: list[dict[str, str]] = []
        warnings: list[str] = []
        mode_counts: dict[str, int] = {}
        total_written = 0
        total_links_added = 0
        total_cells_filled = 0
        written_node_ids: set[str] = set()
        raw_record_count = self._preparer.count_records_in_chunks(chunks)
        failed, produced = set(), set()
        all_ok = True
        fresh = self._store.load_state()
        schema = fresh.coverage_map.tables.get(tid)
        if schema is None or not schema.attributes:
            failed = _source_hashes(items)
            self._finish_sources(items, tid, failed=failed)
            return ExtractionReport(
                table_id=tid, raw_record_count=raw_record_count, input_chunks=len(chunks),
                status="failed", succeeded=False, warnings=("missing schema",),
                failed_hashes=tuple(sorted(failed)),
            )
        definition = _schema_definition(schema)
        plans = []
        for mode, targets in self._extractor.plan_calls(tid, fresh, items):
            view = self._extractor.render_call(mode, tid, fresh, targets)
            if mode != "fill" or view:
                plans.append((mode, targets, view))
        remaining = Counter(key for _plan in plans for chunk in chunks
                            for key in _source_hashes(chunk))
        if not plans:
            self._finish_sources(items, tid)

        for mode, targets, view in plans:
            async def extract_chunk(index, chunk):
                bundles, ok = await self._extractor.extract_rows(
                    chunk, schema, view, fresh, mode=mode, target_cells=targets,
                )
                chunk_failed = set()
                if not ok and len(chunk) > 1:
                    # 单次拆包回退；合法空结果直接结算，不进入回退。
                    results = await asyncio.gather(*(
                        self._extractor.extract_rows(
                            [item], schema, view, fresh, mode=mode, target_cells=targets,
                        ) for item in chunk
                    ))
                    ok = all(single_ok for _bundles, single_ok in results)
                    for item, (single_bundles, single_ok) in zip(chunk, results, strict=True):
                        bundles.extend(single_bundles)
                        if not single_ok:
                            chunk_failed.update(_source_hashes([item]))
                elif not ok:
                    chunk_failed.update(_source_hashes(chunk))
                return index, chunk, bundles, chunk_failed, ok

            calls = [asyncio.create_task(extract_chunk(index, chunk))
                     for index, chunk in enumerate(chunks, start=1)]
            try:
                for ready in asyncio.as_completed(calls):
                    index, chunk, bundles, chunk_failed, ok = await ready
                    all_ok = all_ok and ok
                    hashes = _source_hashes(chunk)
                    failed.update(chunk_failed)
                    chunk_records = self._preparer.count_records_in_items(chunk)
                    if mode in {"discover", "merged"} and chunk_records and not bundles and not (
                        mode == "discover" and raw_record_count is not None
                        and len(schema.entities) >= raw_record_count
                    ):
                        warnings.append(
                            f"{mode} chunk {index}/{len(chunks)} contained "
                            f"{chunk_records} structured record(s) but returned []"
                        )
                    mode_counts[mode] = mode_counts.get(mode, 0) + len(bundles)
                    all_extracted_rows.extend(
                        self._extractor.strip_row_metadata(bundle[0]) for bundle in bundles
                    )
                    written: dict[str, Any] = {"count": 0, "ids": [], "rejected": []}

                    def merge(current):
                        latest_schema = current.coverage_map.tables.get(tid)
                        if (latest_schema is None or _schema_definition(latest_schema) != definition
                                or current.source_scope != fresh.source_scope):
                            written["stale"] = True
                            return current
                        scoped, scope_rejected = restrict_task_rows(current, chunk, tid, bundles)
                        nodes, rejected = self._commit_rows(scoped, tid, current, commit_stats=written)
                        accepted_ids = written.get("accepted_ids", [node.id for node in nodes])
                        task_id = chunk[0].get("task_id", "")
                        if task_id:
                            from searchos.socm.evidence import bind_task_evidence

                            if accepted_ids:
                                written["task_bindings_added"] = bind_task_evidence(
                                    current, task_id, accepted_ids,
                                )
                            candidate_ids = {record["candidate_id"] for record in rejected
                                             if record.get("candidate_id")}
                            candidate_ids = [node.id for node in current.evidence_graph.nodes
                                             if node.id in candidate_ids
                                             and node.status == EvidenceStatus.CANDIDATE]
                            if candidate_ids:
                                bind_task_evidence(current, task_id, candidate_ids, relation="context")
                        written.update(count=len(nodes), ids=[node.id for node in nodes],
                                       rejected=scope_rejected + rejected)
                        return current

                    if bundles:
                        self._store.atomic_update_state(merge)
                    else:
                        current = self._store.load_state()
                        latest_schema = current.coverage_map.tables.get(tid)
                        if (latest_schema is None or _schema_definition(latest_schema) != definition
                                or current.source_scope != fresh.source_scope):
                            written["stale"] = True
                    if written.get("stale"):
                        all_ok = False
                        failed.update(hashes)
                        warnings.append("schema_or_source_scope_changed")
                    else:
                        for bundle in bundles:
                            produced.update(_source_hashes([
                                item for item in chunk
                                if item.get("source_url", "") == bundle[2]
                                and (len(bundle) < 6 or item.get(
                                    "observation_text", item.get("content", "")
                                ) == bundle[5])
                            ]))
                    accepted_ids = written.get("accepted_ids", written["ids"])
                    self._added_node_ids.update(accepted_ids)
                    written_node_ids.update(accepted_ids)
                    total_written += int(written["count"])
                    total_links_added += (written.get("evidence_links_added", 0)
                                          + written.get("task_bindings_added", 0))
                    total_cells_filled += written.get("cells_filled", 0)
                    all_rejected.extend(written["rejected"])
                    all_bundles.extend(bundles)
                    remaining.subtract(hashes)
                    for item in chunk:
                        completed = _source_hashes([item])
                        if all(remaining[key] == 0 for key in completed):
                            self._finish_sources([item], tid, failed=failed, produced=produced)
                    if self._conflicts is not None and accepted_ids:
                        current = self._store.load_state()
                        accepted = set(accepted_ids)
                        touched = {key for key, cell in current.coverage_map.cells.items()
                                   if accepted.intersection(cell.supporting_evidence_ids)}
                        await self._review_conflicts(touched)
            finally:
                for call in calls:
                    if not call.done():
                        call.cancel()
                await asyncio.gather(*calls, return_exceptions=True)

        if self._trajectory_logger and all_bundles:
            event = {
                "type": "harness",
                "kind": "row_extraction",
                "rows_returned": len(all_bundles),
                "rows_by_mode": mode_counts,
                "input_chunks": len(chunks),
                "findings_written": total_written,
                "evidence_links_added": total_links_added,
                "cells_filled": total_cells_filled,
                "table_id": tid,
                "extraction_index": self._extractor.call_count,
            }
            if all_rejected:
                event["rows_rejected_by_check"] = len(all_rejected)
                event["rejected_samples"] = all_rejected[:5]
            if warnings:
                event["warnings"] = list(warnings)
            self._trajectory_logger._append_raw(event)
        committed_state = self._store.load_state()
        nodes = committed_state.evidence_graph.nodes
        projected_rows = {
            target[1]
            for key, bindings in committed_state.coverage_map.evidence_bindings.items()
            if key in committed_state.coverage_map.cells
            and (target := committed_state.coverage_map.cell_binding(key)) is not None
            and target[0] == tid
            and any(
                b.evidence_id in written_node_ids and b.status.value == "active" for b in bindings
            )
        }
        committed_rows = len(
            {
                str(getattr(node, "entity", "") or "")
                for node in nodes
                if node.id in written_node_ids and getattr(node, "table_id", "") == tid
            }
            | projected_rows
        )
        extracted_count = len(all_extracted_rows)
        if raw_record_count is not None and raw_record_count > 0:
            status = "complete" if extracted_count >= raw_record_count else "partial"
        elif extracted_count:
            status = "complete"
        elif warnings:
            status = "partial"
        else:
            status = "empty"
        return ExtractionReport(
            table_id=tid,
            primary_key=tuple(schema.primary_key),
            data_columns=tuple(schema.data_columns),
            raw_record_count=raw_record_count,
            input_chunks=len(chunks),
            extracted_rows=tuple(all_extracted_rows),
            committed_rows=committed_rows,
            committed_nodes=total_written,
            evidence_links_added=total_links_added,
            cells_filled=total_cells_filled,
            status=status,
            warnings=tuple(warnings),
            succeeded=all_ok and not failed,
            failed_hashes=tuple(sorted(failed)),
            produced_hashes=tuple(sorted(produced)),
        )

    def _build_feedback(self, pre_filled: set[str]) -> str:
        """Brief summary of what the last flush extracted (recent findings
        count + entity hints). Search agent doesn't see CoverageMap."""
        state = self._store.load_state()
        graph = state.evidence_graph
        if not graph.nodes:
            return ""
        recent = [n for n in graph.nodes if n.id not in pre_filled]
        if not recent:
            return ""
        parts = [f"""[Extraction feedback] {len(recent)} findings recorded this batch."""]
        entity_hints = sorted({n.entity for n in recent if n.entity})
        if entity_hints and len(entity_hints) <= 8:
            parts.append(f"Entities seen: {', '.join(entity_hints[:8])}")
        elif entity_hints:
            parts.append(f"Entities seen: {len(entity_hints)} unique")
        return "\n".join(parts)
