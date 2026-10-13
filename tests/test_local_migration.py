"""Conservative legacy local-index migration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from searchos.local.index.migration import migrate_legacy_index, write_migration_report
from searchos.local.index.source_registry import SourceRegistry
from searchos.local.reader.tools import local_open, reset_local_browser


def _legacy_index(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "notes.md"
    source.write_text("# 范围\n本地检索正文\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    root = tmp_path / "index"
    (root / "texts").mkdir(parents=True)
    (root / "documents").mkdir()
    legacy = root / "texts" / "doc_notes.md"
    legacy.write_text(
        "# 提取正文：notes.md\n\n"
        "## 文件记录\n\n"
        "- 文档 ID：doc_notes\n"
        "- 原文：notes.md\n"
        f"- 原文绝对路径：{source}\n"
        f"- 授权根目录：{source_root}\n"
        "- 类型：markdown\n"
        f"- 内容哈希：sha256:{digest}\n"
        f"- 生成指纹：sha256:{'0' * 64}\n"
        "- 处理状态：ready\n"
        "- 正文字符数：12\n"
        "- 文件 Recap：介绍本地检索。\n\n"
        "## 正文\n\n"
        "<!-- searchos:segment id=S1 location=L1-2 method=native -->\n"
        "# 范围\n本地检索正文\n",
        encoding="utf-8",
    )
    return root, source_root, legacy


@pytest.mark.asyncio
async def test_migration_reprocesses_verified_source_and_preserves_legacy_cache(
    tmp_path: Path,
) -> None:
    root, source_root, legacy = _legacy_index(tmp_path)

    items = await migrate_legacy_index(root, authorized_roots=[source_root])

    assert [(item.document_id, item.status) for item in items] == [
        ("doc_notes", "migrated")
    ]
    assert legacy.is_file()
    record = SourceRegistry(root).read("doc_notes")
    assert record.source_revision == hashlib.sha256(
        (source_root / "notes.md").read_bytes()
    ).hexdigest()
    document_index = (root / "documents" / "doc_notes.md").read_text(encoding="utf-8")
    ref_id = document_index.split("](", 1)[1].split(")：", 1)[0]
    reset_local_browser(root, source_roots=[source_root])
    opened = await local_open.ainvoke({"ref_id": ref_id})
    assert "本地检索正文" in opened


@pytest.mark.asyncio
async def test_migration_reports_changed_source_without_publishing(tmp_path: Path) -> None:
    root, source_root, legacy = _legacy_index(tmp_path)
    (source_root / "notes.md").write_text("# 已变化\n", encoding="utf-8")

    items = await migrate_legacy_index(root, authorized_roots=[source_root])
    report = root / "migration-report.md"
    write_migration_report(report, items)

    assert items[0].status == "source_changed"
    assert legacy.is_file()
    assert not (root / "sources" / "doc_notes.md").exists()
    assert "source_changed" in report.read_text(encoding="utf-8")
