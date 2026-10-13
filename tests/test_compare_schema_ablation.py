from pathlib import Path

import pytest

from eval.compare_schema_ablation import _measure


def _record(tmp_path: Path) -> dict:
    result_path = tmp_path / "ws_test" / "eval_result.json"
    result_path.parent.mkdir()
    return {
        "_result_path": str(result_path),
        "token_usage": {
            "total_tokens": 1_000,
            "llm_calls": 20,
            "by_role": {
                "orchestrator": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "llm_calls": 2,
                },
                "sub_agent": {
                    "prompt_tokens": 300,
                    "completion_tokens": 30,
                    "llm_calls": 6,
                },
                "extraction": {
                    "prompt_tokens": 200,
                    "completion_tokens": 20,
                    "llm_calls": 4,
                },
                "reformat": {
                    "prompt_tokens": 50,
                    "completion_tokens": 5,
                    "llm_calls": 1,
                },
                "skill_router": {
                    "prompt_tokens": 40,
                    "completion_tokens": 4,
                    "llm_calls": 1,
                },
            },
        },
    }


def test_measure_separates_agent_and_extraction_usage(tmp_path: Path) -> None:
    measured = _measure(_record(tmp_path))

    assert measured["agent_tokens"] == 440
    assert measured["agent_llm_calls"] == 8
    assert measured["extraction_tokens"] == 220
    assert measured["extraction_llm_calls"] == 4
    assert "total_tokens" not in measured
    assert "llm_calls" not in measured


def test_measure_rejects_roleless_token_usage(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["token_usage"].pop("by_role")

    with pytest.raises(ValueError, match="missing token_usage.by_role"):
        _measure(record)


def test_measure_rejects_writer_usage_merged_into_sub_agent(
    tmp_path: Path,
) -> None:
    record = _record(tmp_path)
    session_dir = Path(record["_result_path"]).parent / "session"
    session_dir.mkdir()
    (session_dir / "trajectory.jsonl").write_text(
        '{"type":"dispatch","agent":"writer_agent"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="writer_agent usage is merged"):
        _measure(record)
