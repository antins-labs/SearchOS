from __future__ import annotations

import json

import pytest

from eval.preprocess import (
    CleanedQuery,
    PreprocessCache,
    build_preprocess_cache_from_run,
    clean_query,
    generate_schema_hints,
)


@pytest.mark.asyncio
async def test_clean_query_uses_cache_without_model(tmp_path, monkeypatch) -> None:
    query = "Please output a table with columns: A, B."
    cache_path = tmp_path / "preprocess_cache.json"
    cache = PreprocessCache(cache_path)
    cache.put_clean_query(
        "gisa:1",
        query,
        CleanedQuery(
            original=query,
            cleaned="Find the relevant records.",
            columns=["A", "B"],
            column_formats={"A": "integer"},
            filters=["top 5"],
            sort="A desc",
            used_fallback=False,
        ),
    )

    def fail_model_import(*_args, **_kwargs):
        raise AssertionError("cache hit should not import/call model")

    monkeypatch.setattr("searchos.config.models.get_model_for", fail_model_import)

    out = await clean_query(query, cache=PreprocessCache(cache_path), cache_key="gisa:1")

    assert out.cleaned == "Find the relevant records."
    assert out.columns == ["A", "B"]
    assert out.column_formats == {"A": "integer"}
    assert out.filters == ["top 5"]
    assert out.sort == "A desc"
    assert not out.used_fallback


@pytest.mark.asyncio
async def test_generate_schema_hints_uses_legacy_cache_without_model(
    tmp_path, monkeypatch
) -> None:
    query = "Original question"
    gold = tmp_path / "gold.csv"
    gold.write_text("A,B\n1,2\n", encoding="utf-8")
    cache_path = tmp_path / "preprocess_cache.json"
    payload = {
        "version": 1,
        "entries": {
            "gisa:1": {
                "query": query,
                "query_sha256": __import__("hashlib")
                .sha256(query.encode("utf-8"))
                .hexdigest(),
                "schema_hints": {
                    "legacy_default": {"A": "integer identifier"},
                },
            }
        },
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    def fail_model_import(*_args, **_kwargs):
        raise AssertionError("cache hit should not import/call model")

    monkeypatch.setattr("searchos.config.models.get_model_for", fail_model_import)

    hints = await generate_schema_hints(
        query,
        str(gold),
        answer_type="table",
        cache=PreprocessCache(cache_path),
        cache_key="gisa:1",
    )

    assert hints == {"A": "integer identifier"}


def test_build_preprocess_cache_from_combined_run(tmp_path) -> None:
    run_dir = tmp_path / "combined"
    case_dir = run_dir / "42"
    case_dir.mkdir(parents=True)
    (case_dir / "eval_result.json").write_text(
        json.dumps(
            {
                "id": "42",
                "benchmark": "gisa",
                "question": "Q",
                "preprocess": {
                    "cleaned_query": "CQ",
                    "columns": ["Name"],
                    "column_formats": {"Name": "full name"},
                    "filters": ["only active"],
                    "sort": "",
                    "used_fallback": False,
                    "schema_hints": {"Name": "canonical full name"},
                },
            }
        ),
        encoding="utf-8",
    )

    cache = build_preprocess_cache_from_run(run_dir, tmp_path / "cache.json")

    out = cache.get_clean_query("gisa:42", "Q")
    assert out is not None
    assert out.cleaned == "CQ"
    assert cache.get_legacy_schema_hints("gisa:42", "Q") == {
        "Name": "canonical full name"
    }
