"""根据文档摘要维护主题归属和 Markdown 导航。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from searchos.local import messages
from searchos.local.errors import RecapValidationError, user_message
from searchos.local.models import DocumentRecap, ParsedDocument
from searchos.local.parsers.vision import _message_text
from searchos.local.prompts import catalog as prompts
from searchos.local.storage.documents import _one_line
from searchos.local.storage.files import AsyncAdvisoryLock, advisory_lock, atomic_write_text
from searchos.utils.json_extract import extract_json_object

CATALOG_PROMPT_VERSION = prompts.PROMPT_VERSION
logger = logging.getLogger(__name__)
_SUBINDEX_LINK_RE = re.compile(
    r"^- \[(?P<title>.+?)\]\(subindexes/(?P<id>[^/)]+)\.md\)："
    r"(?P<summary>.*) \((?P<chars>\d+) chars\)$"
)
_FILE_LINK_RE = re.compile(
    r"^- \[(?P<name>.+?)\]\(\.\./documents/(?P<id>[A-Za-z0-9._-]+)\.md\)："
    r"(?P<summary>.*) \((?P<chars>\d+) chars\)$"
)


def _label(value: str) -> str:
    return _one_line(value).replace("]", "\\]")


def _subindex_id(title: str, existing: object = ()) -> str:
    """Return a readable, filesystem-safe title with numeric collision handling."""
    value = unicodedata.normalize("NFKC", _one_line(title))
    value = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "-", value)
    value = re.sub(r"\s+", "-", value).strip(" .-")[:80].rstrip(" .-")
    base = value or messages.UNCLASSIFIED
    used = {str(item).casefold() for item in existing}
    candidate = base
    suffix = 2
    while candidate.casefold() in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@dataclass(frozen=True, slots=True)
class CatalogDocument:
    document_id: str
    name: str
    summary: str
    character_count: int


@dataclass(slots=True)
class Subindex:
    subindex_id: str
    title: str
    summary: str = ""
    documents: dict[str, CatalogDocument] = field(default_factory=dict)

    @property
    def character_count(self) -> int:
        return sum(item.character_count for item in self.documents.values())


def topic_revision(topic: Subindex) -> str:
    payload = [
        topic.title,
        [
            [item.document_id, item.name, item.summary, item.character_count]
            for item in sorted(topic.documents.values(), key=lambda item: item.document_id)
        ],
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


class CatalogClient(Protocol):
    async def classify_document(
        self,
        document: CatalogDocument,
        existing: list[Subindex],
    ) -> dict[str, Any]: ...

    async def revise_subindex(
        self,
        title: str,
        documents: list[CatalogDocument],
    ) -> dict[str, Any]: ...


class _Assignment(BaseModel):
    subindex_id: str = ""
    title: str = Field(min_length=1, max_length=80)


class _Assignments(BaseModel):
    display_name: str = Field(default="", max_length=80)
    subindexes: list[_Assignment] = Field(min_length=1, max_length=3)


class _SubindexRevision(BaseModel):
    summary: str = Field(min_length=1, max_length=2_000)


class ModelCatalogClient:
    def __init__(self, model: Any | None = None) -> None:
        if model is None:
            from searchos.config.models import get_model_for

            model = get_model_for("local_recap")
        self._model = model

    async def _invoke_json(self, prompt: str) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self._model.ainvoke(
            [
                SystemMessage(content=prompts.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        payload = extract_json_object(_message_text(response))
        if payload is None:
            raise RecapValidationError(messages.MODEL_JSON_INVALID)
        return payload

    async def classify_document(
        self,
        document: CatalogDocument,
        existing: list[Subindex],
    ) -> dict[str, Any]:
        return await self._invoke_json(prompts.classify_document(document, existing))

    async def revise_subindex(
        self,
        title: str,
        documents: list[CatalogDocument],
    ) -> dict[str, Any]:
        return await self._invoke_json(prompts.revise_subindex(title, documents))


class CatalogMarkdownStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index_path = root / "INDEX.md"
        self.subindexes_dir = root / "subindexes"

    def load(self) -> dict[str, Subindex]:
        manual_topics = set(self.read_state()["manual_topics"])
        summaries: dict[str, tuple[str, str]] = {}
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                match = _SUBINDEX_LINK_RE.match(line)
                if match:
                    summaries[match.group("id")] = (
                        match.group("title").replace("\\]", "]"),
                        match.group("summary"),
                    )

        output: dict[str, Subindex] = {}
        if not self.subindexes_dir.exists():
            return output
        for path in sorted(self.subindexes_dir.glob("*.md")):
            stored_id = path.stem
            lines = path.read_text(encoding="utf-8").splitlines()
            heading = lines[0].removeprefix("# ").strip() if lines else stored_id
            title, summary = summaries.get(stored_id, (heading, ""))
            subindex_id = stored_id
            item = Subindex(subindex_id=subindex_id, title=title, summary=summary)
            for line in lines:
                match = _FILE_LINK_RE.match(line)
                if match:
                    document = CatalogDocument(
                        document_id=match.group("id"),
                        name=match.group("name").replace("\\]", "]"),
                        summary=match.group("summary"),
                        character_count=int(match.group("chars")),
                    )
                    item.documents[document.document_id] = document
            if item.documents or stored_id in manual_topics:
                output[subindex_id] = item
        return output

    def read_state(self) -> dict[str, Any]:
        path = self.root / "catalog_state.json"
        state = (
            json.loads(path.read_text())
            if path.exists()
            else {"manual_documents": [], "topics": {}}
        )
        state.setdefault("display_names", {})
        state.setdefault("manual_display_names", [])
        state.setdefault("manual_topics", [])
        state.setdefault("manual_topic_summaries", [])
        return state

    def write_state(self, state: dict[str, Any]) -> None:
        atomic_write_text(
            self.root / "catalog_state.json", json.dumps(state, ensure_ascii=False, indent=2)
        )

    def mark_pending(
        self, catalog: dict[str, Subindex], affected: set[str], state: dict[str, Any]
    ) -> None:
        for key in affected:
            item = catalog.get(key)
            if item is None or not item.documents:
                state["topics"].pop(key, None)
                continue
            revision = topic_revision(item)
            if key in state["manual_topic_summaries"]:
                state["topics"][key] = {"revision": revision, "status": "ready", "error": ""}
                continue
            if state["topics"].get(key, {}).get("revision") != revision:
                state["topics"][key] = {"revision": revision, "status": "pending", "error": ""}

    def contains_document(self, document_id: str) -> bool:
        return any(document_id in item.documents for item in self.load().values())

    def write(self, subindexes: dict[str, Subindex]) -> None:
        with advisory_lock(self.root / ".locks" / "catalog.lock"):
            self._write_locked(subindexes)

    def _write_locked(self, subindexes: dict[str, Subindex]) -> None:
        self.subindexes_dir.mkdir(parents=True, exist_ok=True)
        manual_topics = set(self.read_state()["manual_topics"])
        active = [
            item
            for item in subindexes.values()
            if item.documents or item.subindex_id in manual_topics
        ]
        active.sort(key=lambda item: (item.title.casefold(), item.subindex_id))
        active_paths: set[Path] = set()
        for item in active:
            lines = [f"# {_one_line(item.title)}", ""]
            documents = sorted(
                item.documents.values(),
                key=lambda value: (value.name.casefold(), value.document_id),
            )
            for document in documents:
                lines.append(
                    f"- [{_label(document.name)}](../documents/{document.document_id}.md)："
                    f"{_one_line(document.summary)} ({document.character_count} chars)"
                )
            path = self.subindexes_dir / f"{item.subindex_id}.md"
            active_paths.add(path)
            atomic_write_text(path, "\n".join(lines).rstrip() + "\n")

        for path in self.subindexes_dir.glob("*.md"):
            if path not in active_paths:
                path.unlink()

        lines = ["# Local Index", ""]
        for item in active:
            lines.append(
                f"- [{_label(item.title)}](subindexes/{item.subindex_id}.md)："
                f"{_one_line(item.summary)} ({item.character_count} chars)"
            )
        atomic_write_text(self.index_path, "\n".join(lines).rstrip() + "\n")


class CatalogService:
    def __init__(self, root: Path, client: CatalogClient) -> None:
        self._store = CatalogMarkdownStore(root)
        self._client = client

    async def upsert(self, document: ParsedDocument, recap: DocumentRecap) -> list[Path]:
        if not recap.summary.strip():
            raise RecapValidationError(messages.CLASSIFICATION_NEEDS_SUMMARY)
        record = CatalogDocument(
            document_id=document.document_id,
            name=document.name,
            summary=recap.summary.strip(),
            character_count=sum(len(segment.text) for segment in document.primary_segments),
        )
        # Classification is serialized with other automatic classifiers, but
        # never holds the membership lock while waiting for a model.
        async with AsyncAdvisoryLock(self._store.root / ".locks" / "catalog-classify.lock"):
            async with AsyncAdvisoryLock(self._store.root / ".locks" / "catalog-transaction.lock"):
                snapshot = self._store.load()
                manual = document.document_id in self._store.read_state()["manual_documents"]
            payload = (
                None
                if manual
                else await self._client.classify_document(
                    record,
                    sorted(snapshot.values(), key=lambda item: item.subindex_id),
                )
            )
            async with AsyncAdvisoryLock(self._store.root / ".locks" / "catalog-transaction.lock"):
                from searchos.local.storage.sources import SourceRegistry

                SourceRegistry(self._store.root).ensure_active(document.document_id)
                catalog = self._store.load()
                state = self._store.read_state()
                old_ids = {
                    key for key, item in catalog.items() if record.document_id in item.documents
                }
                # A manual edit made while classification was in flight wins.
                if record.document_id in state["manual_documents"]:
                    selected = old_ids
                    previous = next(
                        (catalog[key].documents[record.document_id] for key in old_ids), None
                    )
                    name = state["display_names"].get(record.document_id) or (
                        previous.name if previous else record.name
                    )
                    record = CatalogDocument(
                        record.document_id, name, record.summary, record.character_count
                    )
                else:
                    if payload and payload.get("subindexes") == []:
                        payload = {**payload, "subindexes": [{"title": messages.UNCLASSIFIED}]}
                    try:
                        classification = _Assignments.model_validate(payload)
                        assignments = classification.subindexes
                        if classification.display_name.strip():
                            record = CatalogDocument(
                                record.document_id,
                                _one_line(classification.display_name),
                                record.summary,
                                record.character_count,
                            )
                    except ValidationError as exc:
                        raise RecapValidationError(messages.CLASSIFICATION_INVALID) from exc
                    selected = set()
                    for assignment in assignments:
                        title = _one_line(assignment.title)
                        if not title:
                            raise RecapValidationError(messages.TOPIC_NAME_REQUIRED)
                        item = (
                            catalog.get(assignment.subindex_id)
                            if assignment.subindex_id
                            else next(
                                (
                                    item
                                    for item in catalog.values()
                                    if item.title.casefold() == title.casefold()
                                ),
                                None,
                            )
                        )
                        if assignment.subindex_id and item is None:
                            raise RecapValidationError(messages.CLASSIFICATION_UNKNOWN_TOPIC)
                        if item is None:
                            key = _subindex_id(title, catalog)
                            item = Subindex(subindex_id=key, title=title)
                            catalog[key] = item
                        selected.add(item.subindex_id)
                if record.document_id in state["manual_display_names"]:
                    record = CatalogDocument(
                        record.document_id,
                        state["display_names"][record.document_id],
                        record.summary,
                        record.character_count,
                    )
                for item in catalog.values():
                    item.documents.pop(record.document_id, None)
                for key in selected:
                    catalog[key].documents[record.document_id] = record
                state["display_names"][record.document_id] = record.name
                self._store.mark_pending(catalog, old_ids | selected, state)
                self._store.write(catalog)
                self._store.write_state(state)
        await self.refresh_pending()
        return [
            self._store.index_path,
            *(self._store.subindexes_dir / f"{key}.md" for key in sorted(selected)),
        ]

    async def refresh_pending(self, *, retry_failed: bool = False) -> None:
        """Coalesce edits and publish only summaries of the current membership."""
        async with AsyncAdvisoryLock(self._store.root / ".locks" / "catalog-recap.lock"):
            attempted: set[tuple[str, str]] = set()
            while True:
                async with AsyncAdvisoryLock(
                    self._store.root / ".locks" / "catalog-transaction.lock"
                ):
                    catalog = self._store.load()
                    state = self._store.read_state()
                    from searchos.local.storage.sources import SourceRegistry

                    SourceRegistry(self._store.root).ensure_active()
                    candidates = [
                        key
                        for key, value in state["topics"].items()
                        if key in catalog
                        and key not in state["manual_topic_summaries"]
                        and value["status"]
                        in ({"pending", "failed"} if retry_failed else {"pending"})
                        and (key, value["revision"]) not in attempted
                    ]
                    if not candidates:
                        break
                    key = sorted(candidates)[0]
                    topic = catalog[key]
                    revision = state["topics"][key]["revision"]
                    attempted.add((key, revision))
                error = ""
                try:
                    payload = await self._client.revise_subindex(
                        topic.title,
                        sorted(topic.documents.values(), key=lambda item: item.document_id),
                    )
                    revised = _SubindexRevision.model_validate(payload)
                    summary = _one_line(revised.summary)
                    if not summary:
                        raise RecapValidationError(messages.TOPIC_SUMMARY_EMPTY)
                except ValidationError:
                    logger.warning("local topic summary validation failed", exc_info=True)
                    error = messages.TOPIC_RESPONSE_INVALID
                except Exception as exc:
                    logger.warning("local topic summary failed", exc_info=True)
                    error = user_message(exc, messages.TOPIC_RECAP_FAILED)
                async with AsyncAdvisoryLock(
                    self._store.root / ".locks" / "catalog-transaction.lock"
                ):
                    SourceRegistry(self._store.root).ensure_active()
                    current = self._store.load()
                    state = self._store.read_state()
                    if (
                        key not in current
                        or topic_revision(current[key]) != revision
                        or key in state["manual_topic_summaries"]
                    ):
                        continue  # A newer edit remains pending; discard stale model output.
                    state["topics"][key] = {
                        "revision": revision,
                        "status": "failed" if error else "ready",
                        "error": error,
                    }
                    if not error:
                        current[key].summary = summary
                        self._store.write(current)
                    self._store.write_state(state)


__all__ = [
    "CATALOG_PROMPT_VERSION",
    "CatalogClient",
    "CatalogDocument",
    "CatalogMarkdownStore",
    "CatalogService",
    "ModelCatalogClient",
    "Subindex",
]
