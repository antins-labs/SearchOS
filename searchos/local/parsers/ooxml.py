"""Shared safe inspection for OOXML ZIP containers."""

from __future__ import annotations

import zipfile
from pathlib import Path

from searchos.local.errors import LocalDocumentError


def validate_ooxml(path: Path, *, content_type_marker: bytes) -> None:
    if not zipfile.is_zipfile(path):
        raise LocalDocumentError("文件扩展名与 OOXML 容器不匹配")
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                content_types = archive.read("[Content_Types].xml")
            except KeyError as exc:
                raise LocalDocumentError("OOXML 容器缺少 [Content_Types].xml") from exc
    except zipfile.BadZipFile as exc:
        raise LocalDocumentError(f"OOXML 容器损坏：{exc}") from exc
    if content_type_marker not in content_types:
        raise LocalDocumentError("文件扩展名与 OOXML 文档类型不匹配")


def inspect_ooxml_limits(
    path: Path,
    *,
    max_uncompressed_bytes: int,
    max_members: int,
) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise LocalDocumentError(f"OOXML 对象数超过限制 {max_members}")
        total = sum(member.file_size for member in members)
        if total > max_uncompressed_bytes:
            raise LocalDocumentError(
                f"OOXML 解压后大小 {total} bytes，超过限制 {max_uncompressed_bytes} bytes"
            )
        if any(member.flag_bits & 0x1 for member in members):
            raise LocalDocumentError("不支持含加密成员的 OOXML 文档")
        return tuple(member.filename for member in members)


__all__ = ["inspect_ooxml_limits", "validate_ooxml"]
