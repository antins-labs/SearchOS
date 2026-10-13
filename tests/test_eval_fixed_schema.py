"""固定 schema 消融配置与安装路径的回归测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.benchmarks.widesearch import load_samples
from eval.build_extended_schema_config import SPECS, build_config
from eval.fixed_schema import (
    install_fixed_schema,
    load_fixed_schema_variant,
    validate_fixed_schema,
)
from searchos.socm import SearchState

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "eval/configs/widesearch_fixed_schemas_pilot.json"
EXTENDED_CONFIG = ROOT / "eval/configs/widesearch_fixed_schemas_extended.json"
PILOT_IDS = [
    "ws_en_001",
    "ws_en_013",
    "ws_en_017",
    "ws_en_040",
    "ws_en_048",
    "ws_zh_018",
    "ws_zh_019",
    "ws_zh_028",
    "ws_zh_035",
    "ws_zh_045",
]


def test_pilot_config_has_both_variants_without_seed_entities() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert sorted(payload["samples"]) == sorted(PILOT_IDS)
    for sample in payload["samples"].values():
        assert set(sample) == {"single", "multi"}
        assert len(sample["single"]["tables"]) == 1
        assert len(sample["multi"]["tables"]) >= 2
        for variant in sample.values():
            for table in variant["tables"]:
                assert not table.get("seed_entities")


def test_pilot_variants_cover_every_scored_column() -> None:
    samples = load_samples(
        ROOT / "datasets/widesearch/widesearch.jsonl",
        ROOT / "datasets/widesearch/widesearch_gold",
        ids=PILOT_IDS,
    )
    assert {sample.id for sample in samples} == set(PILOT_IDS)
    for variant in ("single", "multi"):
        specs = load_fixed_schema_variant(CONFIG, variant, sample_ids=PILOT_IDS)
        for sample in samples:
            validate_fixed_schema(
                specs[sample.id], required_columns=sample.required_columns or ()
            )


def test_install_fixed_schema_builds_relations_but_no_rows() -> None:
    spec = load_fixed_schema_variant(
        CONFIG, "multi", sample_ids=["ws_zh_018"]
    )["ws_zh_018"]
    state = SearchState(intent="test")

    summary = install_fixed_schema(
        state,
        spec,
        required_columns=["医疗机构名称", "机构地址", "医疗机构等级", "联系电话", "准入技术"],
    )

    assert summary["variant"] == "multi"
    assert summary["table_count"] == 2
    assert summary["relation_count"] == 1
    assert not state.coverage_map.cells
    assert all(not table.entities for table in state.coverage_map.tables.values())


def test_fixed_schema_rejects_answer_bearing_seeds() -> None:
    spec = {
        "tables": [{
            "table_id": "items",
            "attributes": ["name", "value"],
            "primary_key": ["name"],
            "seed_entities": ["gold answer"],
        }],
        "relations": [],
    }
    with pytest.raises(ValueError, match="forbids answer-bearing row seeds"):
        validate_fixed_schema(spec)


def test_extended_config_is_reproducible_and_covers_scored_columns() -> None:
    generated = build_config(ROOT / "datasets/widesearch/widesearch.jsonl")
    persisted = json.loads(EXTENDED_CONFIG.read_text(encoding="utf-8"))
    assert generated == persisted
    assert set(generated["samples"]) == set(SPECS)

    samples = load_samples(
        ROOT / "datasets/widesearch/widesearch.jsonl",
        ROOT / "datasets/widesearch/widesearch_gold",
        ids=SPECS,
    )
    assert {sample.id for sample in samples} == set(SPECS)
    for variant in ("single", "multi"):
        specs = load_fixed_schema_variant(
            EXTENDED_CONFIG,
            variant,
            sample_ids=SPECS,
        )
        for sample in samples:
            validate_fixed_schema(
                specs[sample.id],
                required_columns=sample.required_columns or (),
            )
