"""Local-library QA orchestration and streaming citation binding."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from searchos.local import messages
from searchos.local.refs import LOCAL_LINK_RE
from searchos.local.storage.documents import StoredBlock
from searchos.local.storage.sources import SourceRecord

if TYPE_CHECKING:
    from searchos.local.library.service import LocalLibraryService

_NUMBERED_CITATION_LINK_RE = re.compile(
    r"\[(?P<label>[^\]\n]*(?:资料|source)\s*(?P<index>\d+)[^\]\n]*)\]"
    r"\((?P<href>[^)\n]*)\)",
    re.IGNORECASE,
)
_NUMBERED_CITATION_TEXT_RE = re.compile(
    r"\[(?P<label>[^\]\n]*(?:资料|source)\s*(?P<index>\d+)[^\]\n]*)\]"
    r"(?!\()",
    re.IGNORECASE,
)
_SHORT_CITATION_RE = re.compile(r"\[(?P<label>(?P<index>\d+))\]\(citation:(?P<target>\d+)\)")


@dataclass(frozen=True, slots=True)
class LocalAnswer:
    answer: str
    input_tokens_estimate: int = 0
    citation_count: int = 0
    citation_status: str = "unverified"
    citations: tuple[dict[str, Any], ...] = ()
    model_calls: int = 1
    tool_counts: dict[str, int] | None = None
    reading_stop_reason: str = "answered"
    read_observations: tuple[dict[str, Any], ...] = ()
    source_documents: tuple[dict[str, Any], ...] = ()


class CitationStream:
    """Bind complete citation tokens while immediately passing ordinary text."""

    def __init__(self, bind, emit):
        self.bind = bind
        self.emit = emit
        self.pending = ""

    def push(self, delta: str, *, final=False):
        self.pending += delta
        text = self.pending
        index = 0
        parts = []
        while index < len(text):
            char = text[index]
            if char == "[":
                nl = text.find("\n", index + 1)
                close = text.find("]", index + 1)
                if close < 0:
                    if nl < 0 and not final:
                        break
                    end = index + 1
                elif nl >= 0 and nl < close:
                    end = index + 1
                elif close + 1 == len(text) and not final:
                    break
                else:
                    end = close + 1
                    if end < len(text) and text[end] == "(":
                        nl2 = text.find("\n", end + 1)
                        close2 = text.find(")", end + 1)
                        if close2 < 0:
                            if nl2 < 0 and not final:
                                break
                        elif nl2 < 0 or close2 < nl2:
                            end = close2 + 1
            elif text.startswith("local://", index):
                match = re.search(r"[\s)>\"']", text[index:])
                if match is None and not final:
                    break
                end = index + match.start() if match else len(text)
            elif char == "l" and not final and "local://".startswith(text[index:]):
                break
            else:
                next_bracket = text.find("[", index + 1)
                next_l = text.find("l", index + 1)
                if next_bracket >= 0 and next_l >= 0:
                    end = min(next_bracket, next_l)
                elif next_bracket >= 0:
                    end = next_bracket
                elif next_l >= 0:
                    end = next_l
                else:
                    end = len(text)
            parts.append(self.bind(text[index:end]))
            index = end
        self.pending = text[index:]
        if final and self.pending:
            parts.append(self.bind(self.pending))
            self.pending = ""
        if parts and self.emit:
            self.emit("".join(parts))


def bind_numbered_citations(answer: str, ordered_refs: list[str]) -> str:
    """Bind short model citation aliases to server-owned source handles."""

    def bind(match: re.Match[str]) -> str:
        index = int(match.group("index")) - 1
        target = match.groupdict().get("target")
        if (
            index < 0
            or index >= len(ordered_refs)
            or (target is not None and target != match.group("index"))
        ):
            return messages.SOURCE_UNAVAILABLE.format(label=match.group("label"))
        return f"[{match.group('label')}]({ordered_refs[index]})"

    linked = _SHORT_CITATION_RE.sub(bind, answer)
    linked = _NUMBERED_CITATION_LINK_RE.sub(bind, linked)
    return _NUMBERED_CITATION_TEXT_RE.sub(bind, linked)


async def answer_query(
    service: LocalLibraryService,
    library_id: str,
    document_ids: list[str],
    query: str,
    *,
    history: list[dict[str, str]] | None = None,
    model: Any | None = None,
    on_delta: Callable[[str], None] | None = None,
    on_tool=None,
    on_read=None,
    on_round_end=None,
) -> LocalAnswer:
    from searchos.agents.local_search.qa import run_document_qa

    library_scope = not document_ids
    if library_scope:
        document_ids = [
            item["document_id"]
            for item in await asyncio.to_thread(service.list_documents, library_id)
            if item.get("searchable")
        ]
        if not document_ids:
            raise ValueError(messages.NO_SEARCHABLE_DOCUMENTS)
    document_ids = list(dict.fromkeys(document_ids))
    # Verify the selected upload scope once before constructing any model.
    if library_scope:
        records = await asyncio.to_thread(service._verified_records, library_id, document_ids)
        verified: list[tuple[SourceRecord, StoredBlock]] = []
    else:
        verified = await asyncio.to_thread(service._verified_blocks, library_id, document_ids)
        records = {record.document_id: record for record, _ in verified}
    if set(records) != set(document_ids):
        raise ValueError(messages.SELECTION_UNREADABLE)
    library = service.get_library(library_id)
    stream_refs: list[str] = []
    stream_aliases: dict[str, str] = {}

    def record_read(item):
        stream_refs.append(item["ref_id"])
        stream_aliases[item["ref_id"]] = item["ref_id"]
        stream_aliases[item["tool_ref_id"]] = item["ref_id"]
        if on_read:
            on_read(item)

    def bind(text):
        text = bind_numbered_citations(text, stream_refs)
        return LOCAL_LINK_RE.sub(
            lambda match: stream_aliases.get(match.group(), "invalid-local-reference"),
            text,
        )

    stream = CitationStream(bind, on_delta)
    result = await run_document_qa(
        index_root=library.index_root,
        records=[records[doc] for doc in document_ids],
        query=query,
        history=history,
        model=model,
        on_tool=on_tool,
        on_read=record_read,
        on_delta=stream.push,
        preload_blocks=[] if library_scope else verified,
        library_scope=library_scope,
    )
    stream.push("", final=True)
    bound_answer = bind_numbered_citations(
        result.answer,
        [item["ref_id"] for item in result.observations],
    )
    answer = LOCAL_LINK_RE.sub(
        lambda match: result.aliases.get(match.group(), "invalid-local-reference"),
        bound_answer,
    )
    if (
        result.observations
        and not LOCAL_LINK_RE.search(answer)
        and not re.search(r"local://|\[(?:资料|source)|\[\d+\]\(citation:", result.answer, re.I)
    ):
        # A navigation fallback, not a fabricated claim-to-source attribution.
        documents = {}
        for item in result.observations:
            documents.setdefault(item["document_id"], item)
        links = []
        for item in documents.values():
            label = f"{item['file']} · {item['location_label']}".replace("[", r"\[").replace(
                "]", r"\]"
            )
            links.append(f"- [{label}]({item['ref_id']})")
        footer = messages.ANSWER_SOURCES + "\n".join(links)
        answer += footer
        if on_delta:
            on_delta(footer)
    cited = set(LOCAL_LINK_RE.findall(answer))
    citations = tuple(
        {
            "ref_id": item["ref_id"],
            "window_id": item["window_id"],
            "validation": "source_bound_not_grounded",
        }
        for item in result.observations
        if item["ref_id"] in cited
    )
    local_answer = LocalAnswer(
        answer=answer,
        read_observations=tuple(result.observations),
        citations=citations,
        citation_count=len(cited),
        citation_status="source_bound_not_grounded" if cited else "missing",
        model_calls=result.model_calls,
        tool_counts=result.tool_counts,
        input_tokens_estimate=result.input_tokens_estimate,
        reading_stop_reason=result.stop_reason,
        source_documents=tuple(
            {
                "document_id": record.document_id,
                "source_revision": record.source_revision,
                "generation": record.generation,
            }
            for record in records.values()
        ),
    )
    if on_round_end:
        on_round_end()
    return local_answer
