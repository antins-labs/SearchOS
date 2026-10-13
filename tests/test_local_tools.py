"""Local catalog/open/find navigation and authorization contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from searchos.harness.middleware.extraction import (
    LocalEvidenceMiddleware,
    WebEvidenceMiddleware,
)
from searchos.local.reader.tools import (
    get_local_tools,
    local_catalog,
    local_find,
    local_open,
    reset_local_browser,
)


def _library(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "notes.md"
    source.write_text("# 范围\n本地检索正文\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    root = tmp_path / "index"
    (root / "subindexes").mkdir(parents=True)
    (root / "documents").mkdir()
    (root / "texts").mkdir()
    (root / "INDEX.md").write_text(
        "# Local Index\n\n"
        "- [本地搜索](subindexes/local.md)：本地文件检索资料。 (12 chars)\n",
        encoding="utf-8",
    )
    (root / "subindexes" / "local.md").write_text(
        "# 本地搜索\n\n"
        "- [notes.md](../documents/doc_notes.md)：介绍本地检索。 (12 chars)\n",
        encoding="utf-8",
    )
    (root / "documents" / "doc_notes.md").write_text(
        "# notes.md\n\n"
        "- [L1-2](../texts/doc_notes.md#L1-2)：介绍范围。 (12 chars)\n",
        encoding="utf-8",
    )
    (root / "texts" / "doc_notes.md").write_text(
        "# 提取正文：notes.md\n\n"
        "## 文件记录\n\n"
        "- 文档 ID：doc_notes\n"
        "- 原文：notes.md\n"
        f"- 原文绝对路径：{source}\n"
        f"- 授权根目录：{source_root}\n"
        "- 类型：markdown\n"
        f"- 内容哈希：sha256:{digest}\n"
        "- 生成指纹：sha256:"
        + "0" * 64
        + "\n"
        "- 处理状态：ready\n"
        "- 正文字符数：12\n"
        "- 文件 Recap：介绍本地检索。\n\n"
        "## 正文\n\n"
        "<!-- searchos:segment id=S1 location=L1-2 method=native -->\n"
        "# 范围\n本地检索正文\n",
        encoding="utf-8",
    )
    return root, source


@pytest.mark.asyncio
async def test_catalog_owns_all_index_navigation(tmp_path) -> None:
    root, _ = _library(tmp_path)
    reset_local_browser(root)

    catalog = await local_catalog.ainvoke({"path": "", "query": ""})
    subindex = await local_catalog.ainvoke(
        {"path": "subindexes/local.md", "query": ""}
    )
    document = await local_catalog.ainvoke(
        {"path": "documents/doc_notes.md", "query": ""}
    )

    assert '【本地搜索】 catalog_path="subindexes/local.md"' in catalog
    assert '【notes.md】 catalog_path="documents/doc_notes.md"' in subindex
    assert '【L1-2】 ref_id="local://index/doc_notes#L1-2"' in document
    assert "[LOCAL_SOURCE]" not in document


@pytest.mark.asyncio
async def test_open_and_find_use_explicit_source_ref(tmp_path) -> None:
    root, _ = _library(tmp_path)
    reset_local_browser(root)
    ref_id = "local://index/doc_notes#L1-2"

    first = await local_open.ainvoke(
        {"ref_id": ref_id, "loc": 0, "max_chars": 5}
    )
    second = await local_open.ainvoke(
        {"ref_id": ref_id, "loc": 5, "max_chars": 5}
    )
    matches = await local_find.ainvoke(
        {"ref_id": ref_id, "pattern": "检索正文"}
    )

    assert "[LOCAL_SOURCE]" in first
    assert "Source: local://index/doc_notes#L1-2" in first
    assert "Characters: [0, 5)" in first
    assert 'loc=5, max_chars=5' in first
    assert "Characters: [5, 10)" in second
    assert "[LOCAL_SOURCE]" in matches
    assert "loc=" in matches
    assert "本地检索正文" in matches


@pytest.mark.asyncio
async def test_catalog_query_and_path_traversal_are_bounded(tmp_path) -> None:
    root, _ = _library(tmp_path)
    reset_local_browser(root)

    result = await local_catalog.ainvoke({"path": "", "query": "检索"})
    traversal = await local_catalog.ainvoke(
        {"path": "../secret.md", "query": ""}
    )
    index_via_open = await local_open.ainvoke(
        {"ref_id": "documents/doc_notes.md", "loc": 0, "max_chars": 6000}
    )

    assert "documents/doc_notes.md" in result
    assert "路径超出当前资料库" in traversal
    assert "ref_id 必须是 local://" in index_via_open


@pytest.mark.asyncio
async def test_local_open_rejects_stale_original(tmp_path) -> None:
    root, source = _library(tmp_path)
    source.write_text("# 范围\n内容已经变化\n", encoding="utf-8")
    reset_local_browser(root)

    result = await local_open.ainvoke(
        {
            "ref_id": "local://index/doc_notes#L1-2",
            "loc": 0,
            "max_chars": 6000,
        }
    )

    assert "STALE_INDEX" in result


@pytest.mark.asyncio
async def test_local_open_validates_character_window(tmp_path) -> None:
    root, _ = _library(tmp_path)
    reset_local_browser(root)
    ref_id = "local://index/doc_notes#L1-2"

    negative = await local_open.ainvoke(
        {"ref_id": ref_id, "loc": -1, "max_chars": 10}
    )
    oversized = await local_open.ainvoke(
        {"ref_id": ref_id, "loc": 0, "max_chars": 20_001}
    )

    assert "loc 必须大于或等于 0" in negative
    assert "max_chars 必须在 1 到 20000 之间" in oversized


def test_local_tools_require_explicit_model_access(monkeypatch) -> None:
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_local_tools", True)
    monkeypatch.setattr(settings, "local_allow_model_access", False)
    assert get_local_tools() == []

    monkeypatch.setattr(settings, "local_allow_model_access", True)
    assert [item.name for item in get_local_tools()] == [
        "local_catalog",
        "local_open",
        "local_find",
    ]


def test_local_source_marker_maps_to_stable_evidence_uri() -> None:
    content = "[LOCAL_SOURCE]\nSource: local://default/doc_a#P1-3\n正文"

    assert (
        LocalEvidenceMiddleware._extract_source_url(content)
        == "local://default/doc_a#P1-3"
    )


def test_web_page_marker_preserves_the_persisted_page_id() -> None:
    from searchos.tools.simple_browser.render import PageContents
    from searchos.tools.simple_browser.state import BrowserState

    browser = BrowserState()
    browser.add_page(PageContents(url="https://example.com/final", title="页面", text="正文"))
    browser.page_ids["https://example.com/final"] = "abc123def456"
    content = browser.show_page()

    assert "Page ID: abc123def456" in content
    assert WebEvidenceMiddleware._extract_page_id(content) == "abc123def456"
