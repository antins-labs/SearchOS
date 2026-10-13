from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from searchos.config.run_config import (
    EffectiveRunConfig,
    activate_run_config,
    current_run_config,
)
from searchos.harness.middleware.context.utils.messages import estimate_tokens
from searchos.harness.middleware.extraction import (
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.socm import SearchState


def test_jina_retain_mode_and_cache_namespace(monkeypatch):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.backend.jina import JinaReaderBackend

    monkeypatch.setattr(settings, "enable_web_image_read", False)
    monkeypatch.setattr(settings, "jina_retain_images", "auto")
    baseline = JinaReaderBackend()
    assert baseline._headers()["X-Retain-Images"] == "alt"
    assert baseline.cache_namespace == "jina-images-alt-v1"

    monkeypatch.setattr(settings, "enable_web_image_read", True)
    multimodal = JinaReaderBackend()
    assert multimodal._headers()["X-Retain-Images"] == "all"
    assert multimodal.cache_namespace == "jina-images-all-v1"


def test_disk_cache_namespaces_do_not_cross_hit(tmp_path):
    from searchos.tools.simple_browser.backend.base import FetchResult
    from searchos.tools.simple_browser.cache import DiskFetchCache

    url = "https://example.com/article"
    alt = DiskFetchCache(tmp_path, namespace="jina-images-alt-v1")
    all_images = DiskFetchCache(tmp_path, namespace="jina-images-all-v1")
    alt.put(FetchResult(url=url, markdown="alt-only"))
    assert alt.peek(url).markdown == "alt-only"
    assert all_images.peek(url) is None


def test_markdown_image_url_is_not_wrapped():
    from searchos.tools.simple_browser.render import _wrap_lines

    url = "https://cdn.example.com/chart.png?signature=" + "a" * 180 + "&expires=123"
    lines = _wrap_lines(f"Figure: ![chart]({url}) after", width=40)
    assert any(url in line for line in lines)
    assert sum(url in line for line in lines) == 1


def test_pdf_without_page_reports_the_required_view_argument():
    from searchos.tools.simple_browser.image_reading import _sniff_mime

    with pytest.raises(ValueError, match="为 read_visual 指定.*page"):
        _sniff_mime(b"%PDF-1.7\n", "application/pdf")


def test_read_visual_registered_only_for_search_agent_when_enabled(monkeypatch):
    from searchos.agents import search as search_agent
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_web_image_read", False)
    assert [tool.name for tool in search_agent.get_tools()] == ["search", "open", "find"]
    monkeypatch.setattr(settings, "enable_web_image_read", True)
    assert [tool.name for tool in search_agent.get_tools()] == [
        "search", "open", "find", "read_visual",
    ]


def test_eval_run_config_is_text_only_and_task_local(monkeypatch):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.backend.jina import JinaReaderBackend

    monkeypatch.setattr(settings, "enable_web_image_read", True)
    monkeypatch.setattr(settings, "jina_retain_images", "all")
    baseline = EffectiveRunConfig.from_settings(for_eval=True)
    assert baseline.enable_web_image_read is False
    assert baseline.jina_retain_images == "alt"
    with activate_run_config(baseline):
        assert current_run_config() is baseline
        assert JinaReaderBackend()._headers()["X-Retain-Images"] == "alt"
    assert current_run_config().enable_web_image_read is True


@pytest.mark.asyncio
async def test_auto_native_returns_an_actual_image_block(monkeypatch):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import image_reading

    payload = image_reading.ImagePayload(
        "https://example.com/a.png", "https://cdn.example.com/a.png", "image/png", b"png",
    )
    monkeypatch.setattr(settings, "web_image_read_mode", "auto")
    monkeypatch.setattr(image_reading, "fetch_image", lambda _url: _async_value(payload))
    monkeypatch.setattr(
        image_reading,
        "detect_native_image_support",
        lambda: _async_value(image_reading.CapabilityEntry("supported", 1.0)),
    )
    content = await image_reading.read_image(payload.requested_url, "read it")
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_auto_unknown_falls_back_without_marking_unsupported(monkeypatch):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import image_reading

    payload = image_reading.ImagePayload("https://e.test/a", "https://e.test/a", "image/png", b"x")
    monkeypatch.setattr(settings, "web_image_read_mode", "auto")
    monkeypatch.setattr(image_reading, "fetch_image", lambda _url: _async_value(payload))
    monkeypatch.setattr(image_reading, "detect_native_image_support", lambda: _async_value(None))
    monkeypatch.setattr(
        image_reading, "vision_content", lambda _payload, _question: _async_value("vision result"),
    )
    assert await image_reading.read_image(payload.requested_url) == "vision result"


@pytest.mark.asyncio
async def test_pdf_page_uses_physical_page_and_existing_vision_path(monkeypatch):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser import image_reading

    payload = image_reading.ImagePayload(
        "https://e.test/report.pdf",
        "https://e.test/report.pdf#page=3",
        "image/jpeg",
        b"rendered-page",
    )
    monkeypatch.setattr(settings, "web_image_read_mode", "vision")
    monkeypatch.setattr(
        image_reading,
        "fetch_pdf_page",
        lambda url, page: _async_value(payload if page == 3 else None),
    )
    monkeypatch.setattr(
        image_reading,
        "vision_content",
        lambda value, question: _async_value(f"{value.final_url}|{question}"),
    )

    result = await image_reading.read_pdf_page(payload.requested_url, 3, "读取表格")

    assert result == "https://e.test/report.pdf#page=3|读取表格"


@pytest.mark.asyncio
async def test_fetch_pdf_page_renders_only_requested_physical_page(monkeypatch):
    import io

    from pypdf import PdfWriter

    from searchos.tools.simple_browser import image_reading

    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.add_blank_page(width=600, height=800)
    writer.write(output)
    monkeypatch.setattr(
        image_reading,
        "_fetch_visual_bytes",
        lambda _url: _async_value((
            "https://cdn.example.com/report.pdf",
            output.getvalue(),
            "application/pdf",
        )),
    )

    payload = await image_reading.fetch_pdf_page("https://example.com/report.pdf", 2)

    assert payload.requested_url == "https://example.com/report.pdf"
    assert payload.final_url == "https://cdn.example.com/report.pdf#page=2"
    assert payload.mime_type == "image/jpeg"
    assert payload.content.startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_fetch_pdf_page_rejects_out_of_range_page(monkeypatch):
    import io

    from pypdf import PdfWriter

    from searchos.tools.simple_browser import image_reading

    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.write(output)
    monkeypatch.setattr(
        image_reading,
        "_fetch_visual_bytes",
        lambda _url: _async_value((
            "https://example.com/report.pdf",
            output.getvalue(),
            "application/pdf",
        )),
    )

    with pytest.raises(ValueError, match="不存在第 2 页"):
        await image_reading.fetch_pdf_page("https://example.com/report.pdf", 2)


@pytest.mark.asyncio
async def test_read_visual_exposes_one_based_pdf_page_argument(monkeypatch):
    from searchos.tools.simple_browser import image_reading
    from searchos.tools.simple_browser.tools import read_visual

    monkeypatch.setattr(
        image_reading,
        "read_pdf_page",
        lambda url, page, question: _async_value(f"{url}|{page}|{question}"),
    )

    result = await read_visual.ainvoke({
        "url": "https://example.com/report.pdf",
        "page": 4,
        "question": "查看图表",
    })

    assert result == "https://example.com/report.pdf|4|查看图表"
    assert "page" in read_visual.args_schema.model_json_schema()["properties"]


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["OK", "CANNOT_SEE", "WRONG1", "The code is ABC234"])
async def test_capability_probe_rejects_nonmatching_text(monkeypatch, answer):
    from searchos.tools.simple_browser import image_reading

    monkeypatch.setattr(
        image_reading, "_make_image_probe",
        lambda: ("data:image/png;base64,test", "ABC234"),
    )

    class Model:
        async def ainvoke(self, messages):
            assert "ABC234" not in str(messages)
            return AIMessage(content=answer)

    result = await image_reading._run_probe(Model())
    assert result.status == "unsupported"
    assert result.reason


@pytest.mark.asyncio
async def test_capability_probe_accepts_only_matching_answer(monkeypatch):
    from searchos.tools.simple_browser import image_reading

    monkeypatch.setattr(
        image_reading, "_make_image_probe",
        lambda: ("data:image/png;base64,test", "ABC234"),
    )

    class Model:
        async def ainvoke(self, messages):
            assert messages[1].content[1]["type"] == "image_url"
            return AIMessage(content="  ABC234\n")

    assert (await image_reading._run_probe(Model())).status == "supported"


def test_image_probe_generates_random_png_content(monkeypatch):
    import base64
    import io

    from PIL import Image

    from searchos.tools.simple_browser.image_reading import _make_image_probe

    characters = iter("ABC234XYZ789")
    monkeypatch.setattr("searchos.tools.simple_browser.image_reading.secrets.choice",
                        lambda alphabet: next(characters))

    uri, answer = _make_image_probe()
    other_uri, other_answer = _make_image_probe()
    assert answer == "ABC234"
    assert other_answer == "XYZ789"
    assert answer != other_answer
    assert uri != other_uri
    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert image.format == "PNG"
    assert image.width >= 400 and image.height >= 100
    assert len(image.getcolors(maxcolors=100000)) > 1


@pytest.mark.asyncio
async def test_capability_probe_keeps_transient_errors_unknown():
    from searchos.tools.simple_browser.image_reading import _run_probe

    class Model:
        def __init__(self, error=None):
            self.error = error

        async def ainvoke(self, _messages):
            if self.error:
                raise self.error
            return AIMessage(content="")

    assert await _run_probe(Model()) is None
    unsupported = await _run_probe(Model(RuntimeError("image input is not supported")))
    assert unsupported.status == "unsupported"
    assert await _run_probe(Model(TimeoutError("timeout"))) is None


@pytest.mark.asyncio
async def test_inconclusive_retest_clears_previous_supported_status(monkeypatch):
    import time

    from searchos.tools.simple_browser import image_reading

    monkeypatch.setattr(image_reading, "_active_agent_model", lambda: object())
    monkeypatch.setattr(image_reading, "_model_key", lambda model: "test-probe")
    monkeypatch.setattr(image_reading, "_capability_cache", {
        "test-probe": image_reading.CapabilityEntry("supported", time.time()),
    })
    monkeypatch.setattr(image_reading, "_capability_inflight", {})
    monkeypatch.setattr(image_reading, "_run_probe", lambda model: _async_value(None))
    assert await image_reading.detect_native_image_support(force=True) is None
    assert image_reading.capability_status()["status"] == "unknown"


@pytest.mark.asyncio
async def test_native_fallback_preserves_tool_message_pairing(monkeypatch):
    from searchos.tools.simple_browser import image_reading

    original = ToolMessage(
        content=[
            {"type": "text", "text": "来源：https://example.com/chart.png\n读取方式：native"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,eA=="}},
        ],
        tool_call_id="call-read_visual-1",
        name="read_visual",
    )
    monkeypatch.setattr(
        image_reading,
        "vision_content",
        lambda payload, _question: _async_value(f"vision:{payload.final_url}"),
    )
    converted = await image_reading.replace_native_image_tool_results([original])
    assert converted[0].tool_call_id == "call-read_visual-1"
    assert converted[0].name == "read_visual"
    assert converted[0].content == "vision:https://example.com/chart.png"


def test_dynamic_trim_does_not_count_base64_as_text():

    encoded = "a" * 100_000
    message = ToolMessage(
        content=[
            {"type": "text", "text": "source"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        ],
        tool_call_id="call",
    )
    assert estimate_tokens([message]) < 2_000


@pytest.mark.asyncio
async def test_read_visual_uses_the_same_page_observation_contract_as_open():
    from searchos.harness.middleware.extraction import (
        DeliveryMode,
        EvidenceSourceKind,
        WebEvidenceMiddleware,
    )

    middleware = WebEvidenceMiddleware(
        ExtractionCoordinator(None, InMemoryEvidenceStore(SearchState()))
    )

    class CaptureExtraction:
        def __init__(self):
            self.calls = []

        async def submit(self, observation, *, delivery):
            self.calls.append((observation, delivery))
            return SimpleNamespace(duplicate=False, feedback="", extraction_reports=())

    capture = CaptureExtraction()
    middleware.coordinator = capture
    contents = {
        "open": (
            "[Now viewing] Report\nURL: https://example.com/report\n"
            "The report contains enough grounded text to enter Evidence Extraction. " * 2
        ),
        "read_visual": (
            "来源：https://example.com/chart.png\n读取方式：local_vision\n\n"
            "原始内容 OCR 转录：表格包含足够的文本，可作为普通页面观测进入 "
            "Evidence Extraction。" * 2
        ),
    }

    for tool_name in ("open", "read_visual"):
        request = SimpleNamespace(tool_call={"name": tool_name, "args": {}})

        async def handler(_request, *, content=contents[tool_name]):
            return SimpleNamespace(content=content)

        await middleware.awrap_tool_call(request, handler)

    assert len(capture.calls) == 2
    for observation, delivery in capture.calls:
        assert observation.source_kind is EvidenceSourceKind.PAGE
        assert observation.local_source_metadata is None
        assert delivery is DeliveryMode.BUFFERED
    assert capture.calls[0][0].source_url == "https://example.com/report"
    assert capture.calls[1][0].source_url == "https://example.com/chart.png"


async def _async_value(value):
    return value
