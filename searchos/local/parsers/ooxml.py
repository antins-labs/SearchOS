"""Shared safe inspection for OOXML ZIP containers."""

from __future__ import annotations

import zipfile
from pathlib import Path

from searchos.local import messages
from searchos.local.errors import LocalDocumentError


def validate_ooxml(path: Path, *, content_type_marker: bytes) -> None:
    if not zipfile.is_zipfile(path):
        raise LocalDocumentError(messages.OOXML_CONTAINER_MISMATCH)
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                content_types = archive.read("[Content_Types].xml")
            except KeyError as exc:
                raise LocalDocumentError(messages.OOXML_CONTENT_TYPES_MISSING) from exc
    except zipfile.BadZipFile as exc:
        raise LocalDocumentError(messages.OOXML_CORRUPT.format(detail=exc)) from exc
    if content_type_marker not in content_types:
        raise LocalDocumentError(messages.OOXML_TYPE_MISMATCH)


def inspect_ooxml_limits(
    path: Path,
    *,
    max_uncompressed_bytes: int,
    max_members: int,
) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise LocalDocumentError(messages.OOXML_OBJECT_LIMIT.format(limit=max_members))
        total = sum(member.file_size for member in members)
        if total > max_uncompressed_bytes:
            raise LocalDocumentError(
                messages.OOXML_SIZE_LIMIT.format(size=total, limit=max_uncompressed_bytes)
            )
        if any(member.flag_bits & 0x1 for member in members):
            raise LocalDocumentError(messages.OOXML_ENCRYPTED)
        return tuple(member.filename for member in members)


__all__ = ["inspect_ooxml_limits", "validate_ooxml"]
