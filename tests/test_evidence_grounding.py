"""行级证据溯源：一行 finding 必须锚回单一原始页面的原文表述。

回归背景（workspace 20260709_123458）：5 页合批的 judge 调用把每一行都绑上
拼接文本 + 逗号拼接 URL，导致 page_id 对应不到任何已存页面、香山公园的
"5A" 证据混入水立方页面、摘录锚到拼接文本的第一句话。
"""

from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction.evidence_extraction import (
    EvidenceExtractionMiddleware as MW,
    _extract_context,
)
from searchos.harness.middleware.extraction.prompts import build_fill_row_prompt


PAGES = [
    {
        "source_url": "https://news.example.com/xiangshan-5a",
        "content": (
            "Title: 区两会｜香山公园今年有望成为5A级旅游景区\n"
            "Markdown Content: 海淀区将支持香山公园创建国家5A级旅游景区。"
        ),
    },
    {
        "source_url": "https://visit.example.com/water-cube",
        "content": "水立方（国家游泳中心）位于北京市朝阳区，门票30元，开放时间9:00-18:00。",
    },
    {
        "source_url": "https://gov.example.com/notice",
        "content": "市文化和旅游局关于会员单位管理的通知。",
    },
]


class TestResolveRowPage:
    def test_trusts_valid_source_page(self):
        row = {"景点名称": "水立方", "_source_page": 2}
        text, url = MW._resolve_row_page(row, PAGES)
        assert url == PAGES[1]["source_url"]
        assert "水立方" in text

    def test_source_page_accepts_numeric_string(self):
        row = {"景点名称": "香山公园", "_source_page": "1"}
        _text, url = MW._resolve_row_page(row, PAGES)
        assert url == PAGES[0]["source_url"]

    @pytest.mark.parametrize("bad", [None, "", 0, 99, "abc"])
    def test_invalid_index_falls_back_to_excerpt_anchor(self, bad):
        row = {
            "景点名称": "水立方",
            "门票价格": "30",
            "_source_page": bad,
            "_source_excerpt": "门票30元，开放时间9:00-18:00",
        }
        _text, url = MW._resolve_row_page(row, PAGES)
        assert url == PAGES[1]["source_url"]

    def test_fallback_scores_by_cell_text_containment(self):
        # 无 excerpt、无页码：按行内文本命中数选页。
        row = {"景点名称": "香山公园", "景区等级": "5A"}
        _text, url = MW._resolve_row_page(row, PAGES)
        assert url == PAGES[0]["source_url"]

    def test_single_page_is_trivial(self):
        row = {"景点名称": "别处的实体", "_source_page": 42}
        text, url = MW._resolve_row_page(row, PAGES[:1])
        assert url == PAGES[0]["source_url"]
        assert text == PAGES[0]["content"]

    def test_never_returns_joined_urls(self):
        # 任何行都只绑一个 URL——不再出现逗号拼接串。
        for row in ({}, {"_source_page": "nope"}, {"景点名称": "水立方"}):
            _text, url = MW._resolve_row_page(row, PAGES)
            assert url in {p["source_url"] for p in PAGES}
            assert "," not in url


class TestDedupRows:
    SCHEMA = SimpleNamespace(
        primary_key=["景点名称"],
        attributes=["景点名称", "景区等级", "门票价格"],
    )

    def test_same_pk_different_pages_both_kept(self):
        rows = [
            {"景点名称": "香山公园", "景区等级": "AAAA级", "_source_page": 1},
            {"景点名称": "香山公园", "门票价格": "10", "_source_page": 2},
        ]
        assert len(MW._dedup_rows(rows, self.SCHEMA)) == 2

    def test_same_pk_same_page_keeps_fuller_row(self):
        rows = [
            {"景点名称": "香山公园", "景区等级": "AAAA级", "_source_page": 1},
            {
                "景点名称": "香山公园", "景区等级": "AAAA级",
                "门票价格": "10", "_source_page": 1,
            },
        ]
        out = MW._dedup_rows(rows, self.SCHEMA)
        assert len(out) == 1
        assert out[0]["门票价格"] == "10"

    def test_rows_without_page_tag_dedup_by_pk(self):
        rows = [
            {"景点名称": "香山公园", "景区等级": "AAAA级"},
            {"景点名称": "香山公园"},
        ]
        assert len(MW._dedup_rows(rows, self.SCHEMA)) == 1


class TestExtractContext:
    PAGE = (
        "区两会｜香山公园今年有望成为5A级旅游景区。"
        + "无关段落。" * 40
        + "北京奥林匹克公园是国家5A级旅游景区，水立方坐落其中。"
    )

    def test_value_nearest_entity_wins_over_first_occurrence(self):
        # "5A" 首次出现在香山标题里；水立方的证据窗口必须取第二处。
        ctx = _extract_context(self.PAGE, "5A", "水立方")
        assert "水立方" in ctx
        assert "香山公园" not in ctx

    def test_first_occurrence_when_entity_absent(self):
        ctx = _extract_context(self.PAGE, "5A", "不存在的实体")
        assert "香山公园" in ctx

    def test_entity_window_when_value_absent(self):
        ctx = _extract_context(self.PAGE, "找不到的值", "水立方")
        assert "水立方" in ctx

    def test_empty_when_nothing_found(self):
        assert _extract_context(self.PAGE, "没有", "也没有") == ""
        assert _extract_context("", "5A", "水立方") == ""

    def test_prefers_body_over_scraper_preamble(self):
        page = (
            "Title: 区两会｜香山公园今年有望成为5A级旅游景区 "
            "URL Source: https://news.example.com/x "
            "Markdown Content: 海淀区将支持香山公园创建国家5A级旅游景区。"
        )
        ctx = _extract_context(page, "5A", "香山公园")
        assert "海淀区将支持" in ctx

    def test_preamble_hit_kept_when_body_lacks_value(self):
        page = (
            "Title: 香山公园升级为5A "
            "Markdown Content: 正文只谈红叶，不提等级。"
        )
        ctx = _extract_context(page, "5A", "香山公园")
        assert "5A" in ctx


class TestPromptContract:
    def test_pages_are_numbered_and_schema_has_source_page(self):
        prompt = build_fill_row_prompt(
            sub_agent_task="t",
            global_task="g",
            primary_key=["景点名称"],
            data_columns=["景区等级"],
            column_desc=None,
            pages=[{"source_url": "https://a.example.com", "content": "正文"}],
            coverage_snapshot="- 香山公园 MISSING=[景区等级]",
        )
        assert "### Page 1" in prompt
        assert "_source_page" in prompt
