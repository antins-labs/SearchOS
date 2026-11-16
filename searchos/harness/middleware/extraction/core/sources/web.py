"""网页、附件和技能结果的来源识别与观测构造。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urldefrag

from searchos.harness.middleware.extraction.core.models import (
    EvidenceObservation,
    EvidenceSourceKind,
)
from searchos.harness.middleware.extraction.core.source_windows import (
    ObservationPreparer,
    is_extractable_page,
)
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.utils.messages import extract_tool_name
from searchos.socm.evidence.provenance import is_original_source
from searchos.tools.simple_browser.session import is_url_allowed


def _skill_attachments(value):
    """从同一条技能记录读取公告身份和附件，保留各记录自己的归属。"""
    if isinstance(value, list):
        for item in value:
            yield from _skill_attachments(item)
    elif isinstance(value, dict):
        title = value.get("title")
        parent = value.get("canonical_url") or value.get("source_url") or value.get("url")
        if isinstance(title, str) and isinstance(parent, str):
            for field in ("images", "attachments", "pdf_links"):
                items = value.get(field, [])
                for item in items if isinstance(items, list) else [items]:
                    url = item
                    if isinstance(item, dict):
                        url = item.get("url") or item.get("src") or item.get("href")
                    if isinstance(url, str):
                        yield url, parent, title
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from _skill_attachments(item)


def _directory_records(value, parents=(), *, in_list=False):
    """记录列表项的原文 URL 和上级标量信息，不推测字段语义。"""
    if isinstance(value, list):
        for item in value:
            yield from _directory_records(item, parents, in_list=True)
    elif isinstance(value, dict):
        scalars = {key: item for key, item in value.items() if not isinstance(item, (dict, list))}
        url = value.get("canonical_url") or value.get("source_url") or value.get("url")
        if in_list and isinstance(url, str) and is_original_source(url):
            yield urldefrag(url).url, {"parents": list(parents), "record": scalars}
        for item in value.values():
            if isinstance(item, (dict, list)):
                yield from _directory_records(item, (*parents, scalars))


class WebObservationSource:
    _EXTRACTABLE_TOOLS = {"open", "find", "read_visual"}

    def __init__(self, trajectory_logger: Any = None) -> None:
        self._trajectory_logger = trajectory_logger
        self._attachment_parents: dict[str, tuple[str, str] | None] = {}
        self._linked_records: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _content(result: Any) -> str:
        return str(result.content) if hasattr(result, "content") else str(result)

    def _remember_attachment(self, url: str, parent: str, title: str) -> None:
        if not (
            is_original_source(url)
            and is_original_source(parent)
            and url.startswith(("https://", "http://"))
            and parent.startswith(("https://", "http://"))
            and parent != url
            and title.strip()
            and is_url_allowed(parent)
        ):
            return
        url = urldefrag(url).url
        identity = (parent, title.strip())
        if self._attachment_parents.setdefault(url, identity) != identity:
            self._attachment_parents[url] = None

    def _remember_skill(self, content: str, source_url: str) -> None:
        try:
            value = json.loads(content)
        except (ValueError, RecursionError):
            return
        for url, parent, title in _skill_attachments(value):
            self._remember_attachment(url, parent, title)
        for url, record in _directory_records(value):
            if not url.startswith(("https://", "http://")) or not is_url_allowed(url):
                continue
            entry = {"source_url": source_url, **record}
            records = self._linked_records.setdefault(url, [])
            if entry not in records:
                records.append(entry)
                del records[:-4]

    def _related_records(self, source_url: str, source_urls) -> tuple[dict[str, Any], ...]:
        return tuple(record for url in source_urls
                     for record in self._linked_records.get(urldefrag(url).url, ())
                     if record["source_url"] != source_url)

    def _remember_page(self, source: dict) -> None:
        if source.get("access", {}).get("status") == "error":
            return
        for attachment in source.get("attachment_urls", ()):
            self._remember_attachment(
                attachment, source.get("source_url", ""), source.get("source_title", "")
            )

    def execution_observations(
        self, result: Any, context: TaskContext
    ) -> list[EvidenceObservation]:
        from searchos.tools.simple_browser.session import _read_page_from_disk

        artifact = getattr(result, "artifact", None) or {}
        pages = []
        for item in artifact.get("source_observations", []):
            page = _read_page_from_disk(item["page_url"])
            if page is None or not page.metadata.get("evidence_eligible"):
                continue
            self._remember_skill(page.text, page.url)
            pages.append((item, page))
        observations = []
        for item, page in pages:
            observations.append(
                EvidenceObservation(
                    content=page.text,
                    source_url=page.url,
                    source_urls=tuple(page.metadata.get("source_urls", [])),
                    page_id=item["page_id"],
                    source_kind=EvidenceSourceKind.SKILL,
                    target_table=context.target_table,
                    task_id=context.task_id,
                    task_text=context.task_text,
                    linked_records=self._related_records(page.url, page.metadata.get("source_urls", [])),
                )
            )
        return observations

    async def observations(
        self, request: Any, result: Any, context: TaskContext
    ) -> list[EvidenceObservation]:
        tool_name = extract_tool_name(request, default="")
        artifact = getattr(result, "artifact", None)
        if tool_name in {
            "local_open",
            "local_find",
            "local_catalog",
            "exec",
            "read_skill_file",
            "load_skill",
            "list_skills",
        }:
            return []
        artifact = getattr(result, "artifact", None)
        if tool_name == "explore_web":
            # Each page carries its own trusted tool metadata; never extract
            # the aggregate search snippets as if they belonged to one URL.
            pages = artifact.get("pages", []) if isinstance(artifact, dict) else []
            observations = []
            for page in pages:
                content = page.get("content", "")
                url = page.get("source_url", "")
                if (
                    not page.get("evidence_eligible")
                    or not url.startswith(("https://", "http://"))
                    or len(content) < 50
                    or not is_extractable_page(content)
                ):
                    continue
                page_source = page.get("page_source") or {}
                self._remember_page(page_source)
                referring_page = self._attachment_parents.get(urldefrag(url).url)
                observations.append(
                    EvidenceObservation(
                        content=content,
                        source_url=url,
                        referring_page=referring_page,
                        page_id=page_source.get("page_id") or self._extract_page_id(content),
                        source_kind=EvidenceSourceKind.PAGE,
                        target_table=context.target_table,
                        task_id=context.task_id,
                        task_text=context.task_text,
                    )
                )
            return observations
        if isinstance(artifact, dict):
            source = artifact.get("page_source", {})
            if isinstance(source, dict) and (
                source.get("evidence_eligible") is False
                or source.get("kind") in {"diagnostic", "fixture", "execution_index"}
            ):
                return []
            if artifact.get("input_mode") == "fixture" or artifact.get("fixture") is True:
                return []
            if isinstance(source, dict) and (
                source.get("input_mode") == "fixture" or source.get("fixture") is True
            ):
                return []
        visible = self._content(result)
        header = visible.split("\n\n", 1)[0]
        is_page_view = visible.startswith("[Now viewing]") and bool(
            re.search(r"^URL:\s*(?:https?://|skill://)", header, re.MULTILINE)
        )
        if tool_name not in self._EXTRACTABLE_TOOLS and not is_page_view:
            return []

        extraction_result = result
        if tool_name == "read_visual" and isinstance(getattr(result, "content", None), list):
            from searchos.tools.simple_browser.images import (
                replace_native_image_tool_results,
            )

            extraction_result = (await replace_native_image_tool_results([result]))[0]
        content = self._content(extraction_result)
        if len(content) < 50 or tool_name == "read_visual" and content.startswith("Error:"):
            return []
        page_source = self._structured_page_source(extraction_result)
        source_url = page_source.get("source_url") or self._extract_source_url(content)
        from searchos.tools.simple_browser import FETCH_ERROR_SENTINEL

        reason = ""
        if FETCH_ERROR_SENTINEL in content[:200]:
            reason = "fetch_error"
        elif not is_extractable_page(content):
            reason = "unextractable_page"
        if reason:
            self._log_skip(source_url, reason)
            return []

        if page_source.get("kind") == "skill_result":
            self._remember_skill(ObservationPreparer._strip_extraction_noise(content), source_url)
        elif page_source:
            self._remember_page(page_source)
        referring_page = self._attachment_parents.get(urldefrag(source_url).url)
        if tool_name == "read_visual":
            # read_visual 的输出标记最终 URL；链接可经过重定向。
            requested = getattr(request, "tool_call", {}).get("args", {}).get("url", "")
            if requested and is_original_source(source_url):
                candidates = {
                    self._attachment_parents[key]
                    for key in (urldefrag(requested).url, urldefrag(source_url).url)
                    if key in self._attachment_parents
                }
                referring_page = candidates.pop() if len(candidates) == 1 else None
        return [
            EvidenceObservation(
                content=content,
                source_url=source_url,
                source_urls=tuple(page_source.get("source_urls", []))
                if source_url.startswith("skill://")
                else (),
                referring_page=referring_page,
                page_id=page_source.get("page_id") or self._extract_page_id(content),
                source_kind=(
                    EvidenceSourceKind.SKILL
                    if page_source.get("kind") == "skill_result"
                    else EvidenceSourceKind.PAGE
                ),
                target_table=context.target_table,
                task_id=context.task_id,
                task_text=context.task_text,
                linked_records=self._related_records(source_url, page_source.get("source_urls", [])),
            )
        ]

    def _log_skip(self, source_url: str, reason: str) -> None:
        if self._trajectory_logger:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "extraction_skipped",
                    "reason": reason,
                    "source": source_url[:200],
                }
            )

    @staticmethod
    def _structured_page_source(result: Any) -> dict:
        """只从工具 artifact 取来源身份，不接受正文中的伪造元数据。"""
        artifact = getattr(result, "artifact", None)
        payload = artifact.get("page_source") if isinstance(artifact, dict) else None
        if not isinstance(payload, dict):
            return {}
        url = payload.get("source_url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://", "skill://")):
            return {}
        page_id = payload.get("page_id")
        return {
            "source_url": url,
            "page_id": page_id if isinstance(page_id, str) else "",
            "kind": payload.get("kind", ""),
            "source_urls": payload.get("source_urls", []),
            "access": payload.get("access", {}),
            "source_title": payload.get("source_title", ""),
            "attachment_urls": payload.get("attachment_urls", []),
        }

    @staticmethod
    def _extract_source_url(content: str) -> str:
        match = re.search(r"<Page \d+>[^\n]*?\((https?://\S+)", content)
        if match:
            url = match.group(1)
            while url.endswith(")") and url.count(")") > url.count("("):
                url = url[:-1]
            return url
        match = re.search(r"^URL:\s*((?:https?://|skill://)\S+)", content, re.MULTILINE)
        if match:
            return match.group(1)
        match = re.search(r"https?://\S+", content)
        return match.group(0) if match else ""

    @staticmethod
    def _extract_page_id(content: str) -> str:
        match = re.search(r"^Page ID:\s*([a-f0-9]{12})\s*$", content, re.MULTILINE)
        if match:
            return match.group(1)
        from searchos.tools.simple_browser.session import _compute_page_id

        source = WebObservationSource._extract_source_url(content)
        return _compute_page_id(source) if source else ""
