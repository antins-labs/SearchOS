"""证据抽取生命周期：接收、调度、结算与提交协调。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Literal

from searchos.harness.middleware.extraction.core.commit import ingest_facts, ingest_rows
from searchos.harness.middleware.extraction.core.conflicts import ConflictReviewer
from searchos.harness.middleware.extraction.core.judge import RowExtractor
from searchos.harness.middleware.extraction.core.models import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionProgress,
    ExtractionReceipt,
    ExtractionReport,
    ExtractionSummary,
)
from searchos.harness.middleware.extraction.core.preparation import (
    ObservationPreparer,
    OriginalWindowPreparer,
)
from searchos.harness.middleware.extraction.core.routing import SchemaRouting, TaskRouting
from searchos.harness.middleware.extraction.core.store import EvidenceStore, WorkspaceEvidenceStore
from searchos.harness.middleware.models import TaskContext

logger = logging.getLogger(__name__)


class ExtractionCoordinator:
    """管理观察批次、异步任务、表级串行执行和原子提交顺序。"""

    def __init__(
        self,
        judge_model: Any,
        store: EvidenceStore | None = None,
        trajectory_logger: Any = None,
        batch_n: int = 5,
        config: ExtractionConfig | None = None,
        routing: TaskRouting | None = None,
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
        self._routing = routing or (SchemaRouting() if policy == "schema_facts" else TaskRouting())
        self._commit_rows = commit_rows or (
            ingest_facts if policy == "schema_facts" else ingest_rows
        )
        self._trajectory_logger = trajectory_logger
        self._config = config or ExtractionConfig()
        preparer_type = OriginalWindowPreparer if policy == "schema_facts" else ObservationPreparer
        self._preparer = preparer or preparer_type(self._config, trajectory_logger)
        self._extractor = RowExtractor(judge_model, self._config, trajectory_logger)
        self._conflicts = (
            ConflictReviewer(self._store, self._extractor.invoke, trajectory_logger=trajectory_logger)
            if judge_model is not None else None
        )

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
        # Serializes snapshot→extract→ingest per table so concurrent flushes
        # don't render stale snapshots and emit duplicate rows.
        self._table_flush_locks: dict[str, asyncio.Lock] = {}
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
                    self._recovered.append(record["item"])
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
        if not completed or not all(report.succeeded for report in completed):
            return
        productive = any(
            report.committed_nodes or report.evidence_links_added or report.cells_filled
            for report in completed
        )
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

    async def submit(
        self,
        observation: EvidenceObservation,
        *,
        delivery: DeliveryMode = DeliveryMode.BUFFERED,
    ) -> ExtractionReceipt:
        """接收 Observation；同步模式返回本次提交的 EvidenceNode。"""
        content = observation.content or ""
        import hashlib

        state = self._store.load_state()
        task = next((q for q in state.frontier.questions if q.id == observation.task_id), None)
        result_mode = self._routing.result_mode(state, task, observation.result_mode)
        target_table = observation.target_table or (task.table_id if task else "")
        if not content.strip() or (result_mode == "table" and len(content) < 50):
            return ExtractionReceipt(accepted=False, reason="content_too_short")
        identity = json.dumps(
            [observation.source_url, observation.task_id, result_mode, target_table, content],
            ensure_ascii=False,
        )
        content_hash = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
        item = {
            "content": content,
            "source_url": observation.source_url,
            "page_id": observation.page_id,
            "content_hash": content_hash,
            "target_table": target_table,
            "task_id": observation.task_id,
            "result_mode": result_mode,
            "task_text": observation.task_text
            or (task.task_prompt or task.question if task else state.intent),
            "local_source_metadata": observation.local_source_metadata,
            "source_kind": str(observation.source_kind),
        }
        flushes: list[tuple[str, list[dict[str, Any]]]] = []
        async with self._buffer_lock:
            if content_hash in self._extracted_content_hashes:
                self._duplicate_count += 1
                return ExtractionReceipt(
                    accepted=False,
                    duplicate=True,
                    reason="duplicate_content",
                    feedback=self._take_feedback(),
                )
            if self._journal is not None:
                self._journal.write(item, "pending")
            self._retry_items.pop(content_hash, None)
            self._extracted_content_hashes.add(content_hash)
            self._accepted_count += 1
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
            recovered, self._recovered = self._recovered, []
            self._flush_in_flight_count += len(recovered)
            try:
                await self._run_snapshot(recovered, reason="recovery")
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
        """等待已触发批次并提交剩余缓冲；失败和超时交给运行方处理。"""
        try:
            async with asyncio.timeout(timeout):
                await self.drain_before_model()
                await self.flush(reason="finalize")
        except TimeoutError:
            pending = tuple(self._flush_tasks)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise
        return self.summary()

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

        async def _run() -> None:
            batch = snapshot
            snapshot_size = len(batch)
            self._flush_in_flight_count += snapshot_size
            self._report_pending()
            try:
                async with self._flush_semaphore:
                    await self._run_snapshot(batch, reason=reason, raise_on_failure=False)
            except Exception as exc:  # noqa: BLE001
                self._background_flush_errors.append(exc)
                logger.warning(
                    "Background extraction flush failed (reason=%s)",
                    reason,
                    exc_info=True,
                )
            finally:
                self._flush_in_flight_count -= snapshot_size
                self._report_pending()

        task = asyncio.create_task(_run())
        self._flush_tasks.add(task)
        task.add_done_callback(self._flush_tasks.discard)

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
                reports = await self._run_snapshot([item], reason=reason, raise_on_failure=False)
            after = self._store.load_state()
            attached = {
                b.evidence_id for b in after.evidence_graph.task_bindings if b.task_id == task_id
            } - previous_bindings
            return [
                n
                for n in after.evidence_graph.nodes
                if (n.id not in pre or n.id in attached) and n.source == source_url
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
                + len(getattr(self, "_retry_items", {}))
                + len(getattr(self, "_recovered", []))
            )
            self._store.report_extraction_pending(self, total)
        except Exception:  # noqa: BLE001
            pass

    async def _flush_pending(self, *, reason: str) -> None:
        """取出剩余与失败批次；失败时保留原始观测，允许下一次显式结算重试。"""
        async with self._buffer_lock:
            combined = {item["content_hash"]: item for item in self._pending_buffer}
            combined.update(self._retry_items)
            snapshot = list(combined.values())
            self._pending_buffer.clear()
            self._retry_items.clear()
        if snapshot:
            self._flush_in_flight_count += len(snapshot)
            try:
                await self._run_snapshot(snapshot, reason=reason)
            finally:
                self._flush_in_flight_count -= len(snapshot)
                self._report_pending()
        self._report_pending()

    async def _run_snapshot(self, snapshot, *, reason, raise_on_failure=True):
        """执行及结算持久记录；取消或异常不能使已接收观测凭空消失。"""
        try:
            reports = await self._flush_snapshot(snapshot, reason=reason)
            if any(not report.succeeded for report in reports):
                self._retain_failed(snapshot, "extraction_failed")
                self._pending_feedback.append(
                    "[Extraction feedback] Extraction failed; observations are retained for retry. "
                    "This is not an empty evidence result."
                )
                if raise_on_failure:
                    raise RuntimeError("Evidence extraction returned a failed report")
            else:
                for item in snapshot:
                    self._extracted_content_hashes.add(item["content_hash"])
                    self._retry_items.pop(item["content_hash"], None)
                    if self._journal is not None:
                        self._journal.write(item, "done")
            return reports
        except BaseException as exc:
            self._retain_failed(snapshot, f"{type(exc).__name__}: {exc}")
            raise
        finally:
            self._report_pending()

    def _retain_failed(self, snapshot, error):
        for item in snapshot:
            key = item["content_hash"]
            self._retry_items[key] = item
            # No automatic infinite retry loop: retain for explicit flush or
            # restart, and allow the caller to resubmit the original viewport.
            self._extracted_content_hashes.discard(key)
            if self._journal is not None:
                self._journal.write(item, "failed", error=error)

    async def _flush_snapshot(self, snapshot, *, reason):
        # Schema is authoritative at extraction time, including observations
        # buffered before schema creation. Preserve the originating task ID.
        state = self._store.load_state()
        snapshot, rejected = self._routing.expand(state, snapshot)
        for item, table_id in rejected:
            self._pending_feedback.append(
                f"Target table {table_id!r} no longer exists; select an existing schema."
            )
        groups = {}
        for item in snapshot:
            key = (
                item.get("task_id", ""),
                item.get("target_table", ""),
                item.get("result_mode", ""),
            )
            groups.setdefault(key, []).append(item)
        reports = [
            ExtractionReport(
                table_id=table_id,
                status="failed",
                succeeded=False,
                warnings=("target_table_missing",),
            )
            for _item, table_id in rejected
        ]
        for group in groups.values():
            reports.extend(await self._flush_group(group, reason=reason))
        self._record_settlement(reports)
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

        items = self._preparer.prepare_pages(snapshot)

        state = self._store.load_state()
        if items and items[0].get("result_mode") == "findings":
            from searchos.harness.middleware.extraction.core.findings import extract_and_commit

            new_ids: set[str] = set()
            succeeded = True
            for chunk in self._preparer.chunk_items(items):
                for item in chunk:
                    try:
                        ids = await extract_and_commit(
                            [item],
                            store=self._store,
                            invoke=self._extractor.invoke,
                        )
                        new_ids.update(set(ids) - self._added_node_ids)
                        self._added_node_ids.update(ids)
                    except Exception:
                        succeeded = False
                        logger.warning(
                            "Findings extraction failed for %s",
                            item.get("source_url"),
                            exc_info=True,
                        )
            return [
                ExtractionReport(
                    committed_nodes=len(new_ids),
                    status="complete" if new_ids else "empty",
                    succeeded=succeeded,
                )
            ]
        target_tid = next(
            (str(item.get("target_table") or "") for item in items if item.get("target_table")),
            "",
        )

        if target_tid and target_tid in state.coverage_map.tables:
            schema = state.coverage_map.tables[target_tid]
        else:
            schema = state.coverage_map.table_schema
        if not schema.attributes:
            # No schema yet (explore). Stash agent:// summaries for
            # create_schema to replay post-commit.
            agent_items = [
                {
                    "source_url": it.get("source_url", "") or "",
                    "content": it.get("content", "") or "",
                }
                for it in items
                if (it.get("source_url", "") or "").startswith("agent://")
            ]
            if agent_items:

                def _stash(s: Any) -> Any:
                    s.pending_agent_summaries.extend(agent_items)
                    return s

                self._store.atomic_update_state(_stash)
                if self._trajectory_logger:
                    self._trajectory_logger._append_raw(
                        {
                            "type": "harness",
                            "kind": "pending_summary_stashed",
                            "count": len(agent_items),
                            "reason": reason,
                        }
                    )
            return []

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
            reports.append(await self._extract_and_ingest_table(items, schema.table_id))
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
            for rel_tid in backfill:
                reports.append(await self._extract_and_ingest_table(items, rel_tid))

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

    def _table_lock(self, tid: str) -> asyncio.Lock:
        lock = self._table_flush_locks.get(tid)
        if lock is None:
            lock = asyncio.Lock()
            self._table_flush_locks[tid] = lock
        return lock

    async def _extract_and_ingest_table(
        self,
        items: list[dict[str, Any]],
        tid: str,
    ) -> ExtractionReport:
        """Run FILL then DISCOVER, committing between phases.

        Held under a per-table lock so the snapshot reflects rows committed by
        a prior flush for this same table — concurrent same-table flushes would
        otherwise render stale snapshots and emit duplicate new rows. Chunks
        within one phase run concurrently; phases never do."""
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
        all_ok = True
        async with self._table_lock(tid):
            fresh = self._store.load_state()
            schema = fresh.coverage_map.tables.get(tid)
            if schema is None or not schema.attributes:
                return ExtractionReport(
                    table_id=tid,
                    raw_record_count=raw_record_count,
                    input_chunks=len(chunks),
                    status="skipped",
                    warnings=("missing schema",),
                )
            phase_order = [mode for mode, _view in self._extractor.plan_calls(tid, fresh)]

            for phase_index, mode in enumerate(phase_order):
                # No await or write precedes phase zero; reuse the same snapshot.
                phase_state = fresh if phase_index == 0 else self._store.load_state()
                phase_schema = phase_state.coverage_map.tables.get(tid)
                if phase_schema is None or not phase_schema.attributes:
                    continue
                phase_views = dict(self._extractor.plan_calls(tid, phase_state))
                view = phase_views.get(mode)
                if view is None:
                    continue
                results = await asyncio.gather(
                    *(
                        self._extractor.extract_rows(
                            chunk,
                            phase_schema,
                            view,
                            phase_state,
                            mode=mode,
                        )
                        for chunk in chunks
                    )
                )
                all_ok = all_ok and all(ok for _bundles, ok in results)
                for idx, ((chunk_bundles, _ok), chunk) in enumerate(
                    zip(results, chunks, strict=False),
                    start=1,
                ):
                    chunk_records = self._preparer.count_records_in_items(chunk)
                    if (
                        mode in {"discover", "merged"}
                        and chunk_records
                        and not chunk_bundles
                        and not (
                            mode == "discover"
                            and raw_record_count is not None
                            and len(getattr(phase_schema, "entities", []) or []) >= raw_record_count
                        )
                    ):
                        warnings.append(
                            f"{mode} chunk {idx}/{len(chunks)} contained "
                            f"{chunk_records} structured record(s) but returned []"
                        )
                bundles = [bundle for result, _ok in results for bundle in result]
                mode_counts[mode] = mode_counts.get(mode, 0) + len(bundles)

                # Page indexes are local to each judge call. Keep each bundle's
                # own source and excerpt; atomic commit deduplicates real facts.
                if not bundles:
                    continue
                all_extracted_rows.extend(
                    self._extractor.strip_row_metadata(bundle[0]) for bundle in bundles
                )

                phase_written: dict[str, Any] = {"count": 0, "ids": [], "rejected": []}

                def _merge(s: Any) -> Any:
                    if s.source_scope != phase_state.source_scope:
                        raise ValueError("Source scope changed during table extraction")
                    nodes, rejected = self._commit_rows(bundles, tid, s, commit_stats=phase_written)
                    task_id = items[0].get("task_id", "") if items else ""
                    accepted_ids = phase_written.get("accepted_ids", [node.id for node in nodes])
                    if task_id and accepted_ids:
                        from searchos.socm.evidence import bind_task_evidence

                        phase_written["task_bindings_added"] = bind_task_evidence(
                            s,
                            task_id,
                            accepted_ids,
                        )
                    phase_written["count"] = len(nodes)
                    phase_written["ids"] = [node.id for node in nodes]
                    phase_written["rejected"] = rejected
                    return s

                self._store.atomic_update_state(_merge)
                accepted_ids = phase_written.get("accepted_ids", phase_written["ids"])
                if self._conflicts is not None and accepted_ids:
                    current = self._store.load_state()
                    accepted = set(accepted_ids)
                    touched = {
                        key for key, cell in current.coverage_map.cells.items()
                        if accepted.intersection(cell.supporting_evidence_ids)
                    }
                    await self._conflicts.review(touched)
                self._added_node_ids.update(accepted_ids)
                written_node_ids.update(accepted_ids)
                total_written += int(phase_written["count"])
                total_links_added += phase_written.get(
                    "evidence_links_added", 0
                ) + phase_written.get("task_bindings_added", 0)
                total_cells_filled += phase_written.get("cells_filled", 0)
                all_rejected.extend(phase_written["rejected"])
                all_bundles.extend(bundles)

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
            succeeded=all_ok,
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
        parts = [f"[Extraction feedback] {len(recent)} findings recorded this batch."]
        entity_hints = sorted({n.entity for n in recent if n.entity})
        if entity_hints and len(entity_hints) <= 8:
            parts.append(f"Entities seen: {', '.join(entity_hints[:8])}")
        elif entity_hints:
            parts.append(f"Entities seen: {len(entity_hints)} unique")
        return "\n".join(parts)
