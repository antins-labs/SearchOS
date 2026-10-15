"""Versioned, source-bound ``local://`` references."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from pydantic import TypeAdapter, ValidationError

from searchos.local.models import (
    LineRangeLocator,
    PdfRegionLocator,
    RecordRangeLocator,
    SourceLocator,
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_PREFIX_RE = re.compile(r"^[0-9a-f]{24}$")
_REFERENCE_KEY_RE = re.compile(r"^(?:s[1-9][0-9]*|all)$")
_LOCATORS = TypeAdapter(list[SourceLocator])


@dataclass(frozen=True, slots=True)
class LocalReference:
    library_id: str
    document_id: str
    source_revision: str
    locators: tuple[SourceLocator, ...]
    reference_key: str = ""


def encode_locator_token(locators: list[SourceLocator]) -> str:
    if not locators:
        raise ValueError("引用至少需要一个原文位置")
    payload = _LOCATORS.dump_python(locators, mode="json")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def normalize_locators(locators: list[SourceLocator]) -> list[SourceLocator]:
    """Coalesce only ranges whose union preserves exact source semantics."""

    output: list[SourceLocator] = []
    for locator in locators:
        previous = output[-1] if output else None
        if isinstance(previous, LineRangeLocator) and isinstance(locator, LineRangeLocator):
            if previous.start_line <= locator.start_line <= previous.end_line + 1:
                output[-1] = LineRangeLocator(
                    start_line=previous.start_line,
                    end_line=max(previous.end_line, locator.end_line),
                )
                continue
        if isinstance(previous, PdfRegionLocator) and isinstance(locator, PdfRegionLocator):
            if (
                previous.bbox is None
                and locator.bbox is None
                and previous.page_start <= locator.page_start <= previous.page_end + 1
            ):
                output[-1] = PdfRegionLocator(
                    page_start=previous.page_start,
                    page_end=max(previous.page_end, locator.page_end),
                )
                continue
        if isinstance(previous, RecordRangeLocator) and isinstance(locator, RecordRangeLocator):
            if (
                previous.columns == locator.columns
                and previous.record_start <= locator.record_start <= previous.record_end + 1
            ):
                output[-1] = RecordRangeLocator(
                    record_start=previous.record_start,
                    record_end=max(previous.record_end, locator.record_end),
                    columns=previous.columns,
                )
                continue
        if locator != previous:
            output.append(locator)
    return output


def decode_locator_token(token: str) -> list[SourceLocator]:
    if not token or len(token) > 16_384:
        raise ValueError("locator token 为空或过长")
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        locators = _LOCATORS.validate_python(payload)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("locator token 无效") from exc
    if not locators:
        raise ValueError("locator token 未包含位置")
    canonical = encode_locator_token(locators)
    if canonical != token:
        raise ValueError("locator token 不是规范编码")
    return locators


def build_ref_id(
    *,
    library_id: str,
    document_id: str,
    source_revision: str,
    locators: list[SourceLocator] | None = None,
    reference_key: str = "",
) -> str:
    for field_name, value in (("library_id", library_id), ("document_id", document_id)):
        if not _ID_RE.fullmatch(value):
            raise ValueError(f"{field_name} 无效")
    revision = source_revision.removeprefix("sha256:")
    if not _REVISION_RE.fullmatch(revision):
        raise ValueError("source_revision 必须是 SHA-256")
    if reference_key:
        if not _REFERENCE_KEY_RE.fullmatch(reference_key):
            raise ValueError("reference_key 必须是 s 加正整数或 all")
        if locators:
            raise ValueError("短引用不能同时内嵌 locator")
        token = reference_key
    else:
        token = encode_locator_token(normalize_locators(locators or []))
    if reference_key:
        return (
            f"local://{quote(document_id, safe='._-')}/{token}?"
            f"{urlencode({'v': revision[:24]})}"
        )
    return (
        f"local://{quote(library_id, safe='._-')}/{quote(document_id, safe='._-')}?"
        f"{urlencode({'rev': revision})}#{token}"
    )


def parse_ref_id(ref_id: str) -> LocalReference:
    parsed = urlsplit(ref_id)
    if parsed.scheme != "local" or not parsed.netloc or not parsed.path:
        raise ValueError(
            "ref_id 必须是紧凑版本化引用或兼容的旧版 local:// 引用"
        )
    query = parse_qs(parsed.query, strict_parsing=True)
    if set(query) == {"v"} and len(query["v"]) == 1 and not parsed.fragment:
        document_id = unquote(parsed.netloc)
        reference_key = unquote(parsed.path.removeprefix("/"))
        revision = query["v"][0]
        if not _ID_RE.fullmatch(document_id):
            raise ValueError("ref_id 中的 document id 无效")
        if not _REFERENCE_KEY_RE.fullmatch(reference_key):
            raise ValueError("ref_id 中的短引用无效")
        if not _REVISION_PREFIX_RE.fullmatch(revision):
            raise ValueError("ref_id 的版本前缀无效")
        canonical = (
            f"local://{quote(document_id, safe='._-')}/{reference_key}?"
            f"{urlencode({'v': revision})}"
        )
        if canonical != ref_id:
            raise ValueError("ref_id 不是规范编码")
        return LocalReference("", document_id, revision, (), reference_key)

    library_id = unquote(parsed.netloc)
    document_id = unquote(parsed.path.removeprefix("/"))
    if not _ID_RE.fullmatch(library_id) or not _ID_RE.fullmatch(document_id):
        raise ValueError("ref_id 中的 library id 或 document id 无效")
    if set(query) != {"rev"} or len(query["rev"]) != 1:
        raise ValueError("ref_id 必须且只能包含一个 rev 参数")
    revision = query["rev"][0]
    if not _REVISION_RE.fullmatch(revision):
        raise ValueError("ref_id 的 rev 必须是 SHA-256")
    if _REFERENCE_KEY_RE.fullmatch(parsed.fragment):
        locators: tuple[SourceLocator, ...] = ()
        reference_key = parsed.fragment
    else:
        locators = tuple(decode_locator_token(parsed.fragment))
        reference_key = ""
    canonical = build_ref_id(
        library_id=library_id,
        document_id=document_id,
        source_revision=revision,
        locators=list(locators) or None,
        reference_key=reference_key,
    )
    if canonical != ref_id:
        raise ValueError("ref_id 不是规范编码")
    return LocalReference(library_id, document_id, revision, locators, reference_key)


def resolve_reference(
    reference: LocalReference,
    references: dict[str, list[SourceLocator]],
    *,
    library_id: str,
    source_revision: str,
) -> LocalReference:
    """Resolve a compact source handle against its versioned source record."""
    if not reference.reference_key:
        return reference
    if not source_revision.startswith(reference.source_revision):
        raise ValueError("VERSION_MISMATCH：该短引用绑定的原文版本当前不可用")
    if reference.reference_key == "all":
        # Expand only declared sections. Gaps in the index stay gaps; this
        # handle does not grant access to additional files or representations.
        locators = normalize_locators([
            locator
            for key in sorted(
                (key for key in references if re.fullmatch(r"s[1-9][0-9]*", key)),
                key=lambda key: int(key[1:]),
            )
            for locator in references[key]
        ])
        if locators and len(encode_locator_token(locators)) > 16_384:
            raise ValueError("整份文档的位置过多，请使用目录中的章节引用")
    else:
        locators = references.get(reference.reference_key)
    if not locators:
        raise ValueError("短引用在来源记录中不存在，请重新建立索引")
    return replace(
        reference,
        library_id=library_id,
        source_revision=source_revision,
        locators=tuple(locators),
    )


__all__ = [
    "LocalReference",
    "build_ref_id",
    "decode_locator_token",
    "encode_locator_token",
    "normalize_locators",
    "parse_ref_id",
    "resolve_reference",
]
