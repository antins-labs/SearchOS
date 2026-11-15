"""验证核心类的日志恢复、并发追加与写入错误计数。"""

from __future__ import annotations

import json
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from searchos.harness.telemetry.usage import TokenUsage


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _finish(usage: TokenUsage, call_id: str, raw: dict) -> None:
    usage.finish_call(call_id, {
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, **raw},
    })


@pytest.mark.parametrize("prefix", [b"", b'{"saved": 1}\n'])
@pytest.mark.parametrize("tail", [
    b'{"broken":', b'{"broken":"\xe4', b'{"broken":"' + b"x" * 200000,
])
def test_incomplete_tail_is_removed_without_losing_complete_records(tmp_path, prefix, tail):
    path = tmp_path / "usage.jsonl"
    path.write_bytes(prefix + tail)
    _finish(TokenUsage(path), "new", {"new": 2})
    records = _records(path)
    assert records[:-1] == ([{"saved": 1}] if prefix else [])
    assert records[-1]["raw_usage"][0]["usage"]["new"] == 2
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("prefix", [b"", b'{"saved": 1}\n'])
def test_complete_tail_without_newline_is_preserved(tmp_path, prefix):
    path = tmp_path / "usage.jsonl"
    tail = {"last": "原始数据" * 20000}
    encoded = json.dumps(tail, ensure_ascii=False).encode("utf-8")
    path.write_bytes(prefix + encoded)
    _finish(TokenUsage(path), "new", {"new": 2})
    assert path.read_bytes().startswith(prefix + encoded + b"\n")
    records = _records(path)
    assert records[:-1] == ([{"saved": 1}] if prefix else []) + [tail]
    assert records[-1]["raw_usage"][0]["usage"]["new"] == 2


def test_two_tracking_instances_append_large_records_without_tearing(tmp_path):
    path = tmp_path / "nested" / "usage.jsonl"
    trackers = [TokenUsage(path), TokenUsage(path)]
    barrier = Barrier(2)

    def write_records(index):
        barrier.wait(timeout=5)
        for number in range(8):
            payload = {"instance": index, "number": number, "raw": str(index) * 300000}
            _finish(trackers[index], f"{index}-{number}", payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write_records, range(2)))
    records = [record["raw_usage"][0]["usage"] for record in _records(path)]
    assert len(records) == 16
    assert {(r["instance"], r["number"]) for r in records} == {
        (index, number) for index in range(2) for number in range(8)
    }
    assert all(r["raw"] == str(r["instance"]) * 300000 for r in records)


def _append_process(path: str, index: int, barrier) -> None:
    usage = TokenUsage(path)
    barrier.wait(timeout=10)
    for number in range(5):
        _finish(usage, f"{index}-{number}", {
            "instance": index, "number": number, "raw": str(index) * 100000,
        })


def test_separate_processes_share_the_file_lock(tmp_path):
    path = tmp_path / "processes.jsonl"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    workers = [context.Process(target=_append_process, args=(str(path), index, barrier))
               for index in range(2)]
    for worker in workers:
        worker.start()
    try:
        for worker in workers:
            worker.join(timeout=20)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)
    records = [record["raw_usage"][0]["usage"] for record in _records(path)]
    assert len(records) == 10
    assert all(r["raw"] == str(r["instance"]) * 100000 for r in records)


def test_file_open_error_keeps_usage_and_reports_failure(tmp_path):
    usage = TokenUsage(tmp_path)
    _finish(usage, "open-failed", {"new": 2})
    assert usage.llm_calls == usage.usage_recording_errors == 1
    assert usage.total_tokens == 2


def test_file_write_error_keeps_usage_and_reports_failure(tmp_path, monkeypatch):
    original_open = Path.open

    class FailingFile:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, _data):
            raise OSError("disk write failed")

    monkeypatch.setattr(Path, "open", lambda path, *args, **kwargs: FailingFile(
        original_open(path, *args, **kwargs),
    ))
    usage = TokenUsage(tmp_path / "usage.jsonl")
    _finish(usage, "write-failed", {"new": 2})
    assert usage.llm_calls == usage.usage_recording_errors == 1
    assert usage.total_tokens == 2
