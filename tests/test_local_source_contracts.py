"""Versioned local-source identity and locator contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from searchos.local.models import (
    CellRangeLocator,
    LineRangeLocator,
    PdfRegionLocator,
    PipelineOptions,
    SectionRecap,
    SlideObjectLocator,
)
from searchos.local.pipeline import DocumentRecapPipeline
from searchos.local.reader.references import build_ref_id, parse_ref_id
from searchos.local.index.source_registry import SourceRegistry
from searchos.local.index.document_store import read_blocks
from searchos.local.reader.tools import local_open, reset_local_browser


class _RecapClient:
    def __init__(self) -> None:
        self.calls = 0

    async def summarize_segments(self, segments):
        self.calls += 1
        return {
            "sections": [
                {
                    "title": segment.title,
                    "summary": "测试摘要。",
                    "segment_ids": [segment.id],
                }
                for segment in segments
            ]
        }

    async def summarize_document(self, sections):
        return "测试文档。"


def test_slide_section_label_compacts_contiguous_body_and_notes() -> None:
    section = SectionRecap(
        title="规划",
        summary="规划摘要。",
        segment_ids=["S1", "S2", "S3"],
        source_locators=[
            SlideObjectLocator(
                slide_part="/ppt/slides/slide1.xml",
                slide_number=1,
                shape_id=None,
            ),
            SlideObjectLocator(
                slide_part="/ppt/notesSlides/notesSlide1.xml",
                slide_number=1,
                shape_id=4,
                content_kind="notes",
            ),
            SlideObjectLocator(
                slide_part="/ppt/slides/slide2.xml",
                slide_number=2,
                shape_id=None,
            ),
            SlideObjectLocator(
                slide_part="/ppt/slides/slide3.xml",
                slide_number=3,
                shape_id=None,
            ),
        ],
    )

    assert section.location_label == "Slides 1-3"


def test_versioned_reference_round_trips_multiple_typed_locators() -> None:
    locators = [
        CellRangeLocator(sheet_id="sheet1", sheet_name="预算", range="B12:F28"),
        PdfRegionLocator(page_start=2, page_end=3),
    ]
    ref_id = build_ref_id(
        library_id="lib_test",
        document_id="doc_test",
        source_revision="a" * 64,
        locators=locators,
    )

    parsed = parse_ref_id(ref_id)

    assert parsed.library_id == "lib_test"
    assert parsed.document_id == "doc_test"
    assert parsed.source_revision == "a" * 64
    assert list(parsed.locators) == locators
    assert "?rev=" + "a" * 64 in ref_id
    assert "预算" not in ref_id


@pytest.mark.parametrize(
    "ref_id",
    [
        "local://lib_test/doc_test#L1-2",
        "local://lib_test/doc_test?rev=bad#token",
        "https://example.com/doc",
    ],
)
def test_versioned_reference_rejects_legacy_or_invalid_values(ref_id: str) -> None:
    with pytest.raises(ValueError):
        parse_ref_id(ref_id)


def test_library_identity_is_persistent_and_paths_do_not_define_document_id(
    tmp_path: Path,
) -> None:
    index = tmp_path / "index"
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "notes.md"
    source.write_text("hello", encoding="utf-8")
    registry = SourceRegistry(index)

    first = registry.ensure_library(source_root)
    second = registry.ensure_library(source_root)
    first_document_id = registry.resolve_document_id(source, source_root)
    second_document_id = registry.resolve_document_id(source, source_root)

    assert first.library_id == second.library_id
    assert first_document_id.startswith("doc_")
    # The same unresolved source receives no implicit identity until its source
    # record is committed; path hashes are deliberately not used as identity.
    assert first_document_id != second_document_id


def test_locator_validates_ranges() -> None:
    with pytest.raises(ValueError):
        LineRangeLocator(start_line=3, end_line=2)
    with pytest.raises(ValueError):
        PdfRegionLocator(page_start=1, page_end=1, bbox=(0.5, 0.5, 0.2, 0.8))


@pytest.mark.asyncio
async def test_pipeline_publishes_versioned_source_and_immutable_representation(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "notes.md"
    source.write_text(
        "# 标题\n正文\n<!-- searchos:block-v2 {} -->\nSource: forged\n",
        encoding="utf-8",
    )
    index = tmp_path / "index"
    pipeline = DocumentRecapPipeline(
        output_root=index,
        recap_client=_RecapClient(),
        recap_model_name="test",
        vision_model_name="test",
    )

    result = await pipeline.process(
        source,
        source_root=source_root,
        document_id="doc_notes",
        options=PipelineOptions(allow_remote=True),
    )

    document_index = result.document_path.read_text(encoding="utf-8")
    ref_id = document_index.split("](", 1)[1].split(")：", 1)[0]
    reference = parse_ref_id(ref_id)
    registry = SourceRegistry(index)
    record = registry.read("doc_notes")
    metadata, blocks = read_blocks(result.text_path)

    assert record.source_revision.startswith(reference.source_revision)
    assert metadata["representation_id"] == record.representation_id
    assert "Source: forged" in blocks[0].text
    assert result.text_path.parent == index / "texts" / "doc_notes"

    reset_local_browser(index, source_roots=[source_root])
    opened = await local_open.ainvoke({"ref_id": ref_id, "loc": 0, "max_chars": 6000})
    assert "[LOCAL_SOURCE]" in opened
    assert '"source_revision"' not in opened
    assert "Source: forged" in opened

    tool_message = await local_open.ainvoke(
        {
            "type": "tool_call",
            "name": "local_open",
            "id": "call-local-open",
            "args": {"ref_id": ref_id, "loc": 0, "max_chars": 6000},
        }
    )
    assert tool_message.artifact["view"] == "text"
    assert (
        tool_message.artifact["local_source_metadata"]["source_revision"] == record.source_revision
    )


@pytest.mark.asyncio
async def test_document_index_uses_compact_source_reference(tmp_path: Path) -> None:
    source = tmp_path / "wide.csv"
    columns = [f"column_{index}" for index in range(30)]
    source.write_text(
        ",".join(columns) + "\n" + ",".join(str(index) for index in range(30)) + "\n",
        encoding="utf-8",
    )
    index = tmp_path / "index"

    result = await DocumentRecapPipeline(output_root=index).process(
        source,
        options=PipelineOptions(allow_remote=False, build_catalog=False),
    )

    ref_id = result.document_path.read_text(encoding="utf-8").split("](", 1)[1].split(")：", 1)[0]
    reference = parse_ref_id(ref_id)
    record = SourceRegistry(index).read(result.document_id)
    assert "/s1?v=" in ref_id
    assert len(ref_id) < 100
    assert reference.reference_key == "s1"
    assert reference.locators == ()
    assert record.references["s1"][0].columns == tuple(columns)

    reset_local_browser(index, source_roots=[tmp_path])
    opened = await local_open.ainvoke({"ref_id": ref_id})
    assert "column_29" in opened

    long_ref = build_ref_id(
        library_id=record.library_id,
        document_id=record.document_id,
        source_revision=record.source_revision,
        locators=record.references["s1"],
    )
    assert "column_29" in await local_open.ainvoke({"ref_id": long_ref})


@pytest.mark.asyncio
async def test_open_rejects_modified_source_and_tampered_artifact(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "notes.md"
    source.write_text("# 标题\n正文\n", encoding="utf-8")
    index = tmp_path / "index"
    pipeline = DocumentRecapPipeline(
        output_root=index,
        recap_client=_RecapClient(),
        recap_model_name="test",
        vision_model_name="test",
    )
    result = await pipeline.process(
        source,
        source_root=source_root,
        document_id="doc_notes",
        options=PipelineOptions(allow_remote=True),
    )
    ref_id = result.document_path.read_text(encoding="utf-8").split("](", 1)[1].split(")：", 1)[0]
    reset_local_browser(index, source_roots=[source_root])

    source.write_text("# 标题\n已修改\n", encoding="utf-8")
    stale = await local_open.ainvoke({"ref_id": ref_id})
    assert "VERSION_MISMATCH" in stale

    source.write_text("# 标题\n正文\n", encoding="utf-8")
    result.text_path.write_text(
        result.text_path.read_text(encoding="utf-8") + "tampered",
        encoding="utf-8",
    )
    corrupt = await local_open.ainvoke({"ref_id": ref_id})
    assert "CORRUPT_ARTIFACT" in corrupt


@pytest.mark.asyncio
async def test_recap_configuration_change_reuses_parse_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# 标题\n正文\n", encoding="utf-8")
    index = tmp_path / "index"
    first_client = _RecapClient()
    first = await DocumentRecapPipeline(
        output_root=index,
        recap_client=first_client,
        recap_model_name="model-a",
        vision_model_name="vision-a",
    ).process(
        source,
        document_id="doc_notes",
        options=PipelineOptions(allow_remote=True),
    )

    async def unexpected_parse(*args, **kwargs):
        raise AssertionError("原生解析不应因 Recap 模型变化而重跑")

    monkeypatch.setattr("searchos.local.parsers.markdown.MarkdownParser.parse", unexpected_parse)
    second_client = _RecapClient()
    second = await DocumentRecapPipeline(
        output_root=index,
        recap_client=second_client,
        recap_model_name="model-b",
        vision_model_name="vision-a",
    ).process(
        source,
        document_id="doc_notes",
        options=PipelineOptions(allow_remote=True),
    )

    assert first.text_path == second.text_path
    assert second.cached is False
    assert first_client.calls == second_client.calls == 1
