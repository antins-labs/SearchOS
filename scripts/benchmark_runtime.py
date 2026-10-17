"""本地运行性能基准：只读取指定工作区，全部测试写入临时目录。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from api.state_stream import StateStream

from searchos.harness.telemetry.conversation import ConversationLogger, read_conversation
from searchos.harness.telemetry.trajectory import ConversationMessage
from searchos.socm.state import SearchState
from searchos.socm.storage.workspace import WorkspaceManager


def measure(fn, repeats=9):
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        fn()
        samples.append((perf_counter() - started) * 1000)
    return round(median(samples), 3)


async def recap_benchmark():
    from types import SimpleNamespace

    from searchos.local.models import LineRangeLocator, ParsedSegment
    from searchos.local.recap.service import RecapService

    class Client:
        async def summarize_segment(self, segment):
            await asyncio.sleep(0.03)
            return {"title": segment.title, "summary": "summary"}

        async def summarize_document(self, sections):
            return "summary"

    document = SimpleNamespace(
        primary_segments=[
            ParsedSegment(
                id=str(i),
                title=str(i),
                text="x" * 1500,
                source_locators=[LineRangeLocator(start_line=i + 1, end_line=i + 1)],
            )
            for i in range(6)
        ]
    )
    results = {}
    for concurrency in (1, 3):
        start = perf_counter()
        recap = await RecapService(Client(), concurrency=concurrency).generate(
            document, max_chars=2000
        )
        assert len(recap.sections) == 6
        results[f"recap_simulated_{concurrency}_workers_ms"] = round(
            (perf_counter() - start) * 1000, 3
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("searchos_workspace"))
    args = parser.parse_args()
    states = list(args.workspace.glob("*/search_state.json"))
    if not states:
        parser.error("指定工作区中没有 search_state.json")
    source = max(states, key=lambda path: path.stat().st_size)
    raw = source.read_bytes()
    state = SearchState.model_validate_json(raw)
    with TemporaryDirectory() as directory:
        ws = WorkspaceManager(directory, "sample")
        ws.path.mkdir()
        ws.save_state(state)

        def legacy_update():
            value = SearchState.model_validate(json.loads(source.read_bytes()))
            # Same old serialize/write operations, never mutate the source session.
            (ws.path / "legacy.json").write_text(
                json.dumps(value.model_dump(), ensure_ascii=False, indent=2, default=str)
            )

        def legacy_poll():
            value = json.loads(source.read_bytes())
            json.dumps(
                value.get("coverage_map", {}).get("cells", {}), sort_keys=True, ensure_ascii=False
            )

        stream = StateStream()
        stream.event(ws.path / "search_state.json")
        report = {
            "source_mib": round(len(raw) / 1024**2, 3),
            "compact_mib": round((ws.path / "search_state.json").stat().st_size / 1024**2, 3),
            "legacy_load_ms": measure(
                lambda: SearchState.model_validate(json.loads(source.read_bytes()))
            ),
            "snapshot_load_ms": measure(ws.load_state),
            "legacy_update_ms": measure(legacy_update),
            "noop_update_ms": measure(lambda: ws.atomic_update_state(lambda value: value)),
            "legacy_poll_ms": measure(legacy_poll),
            "unchanged_poll_ms": measure(lambda: stream.event(ws.path / "search_state.json")),
        }

        def changed_update():
            def update(value):
                value.intent += "."
                return value

            ws.atomic_update_state(update)

        report["changed_update_ms"] = measure(changed_update)
        event = stream.event(ws.path / "search_state.json")
        report["small_delta_bytes"] = len(json.dumps(event, ensure_ascii=False).encode())
        conversations = list(args.workspace.glob("*/conversations/snapshots/*.json"))
        if conversations:
            path = max(conversations, key=lambda path: path.stat().st_size)
            record = read_conversation(path)
            name = record.get("agent_name", "orchestrator")
            logger = ConversationLogger(ws.path / "conversation.json")
            logger._agents[name] = record
            logger._flush_per_agent(name)

            def old_log():
                with (ws.path / "old_conversation.json").open("w") as target:
                    json.dump(record, target, ensure_ascii=False, indent=2, default=str)

            report["legacy_log_ms"] = measure(old_log)
            started = perf_counter()
            for _ in range(64):
                logger.log(ConversationMessage(agent_name=name, content="benchmark"))
            logger.flush()
            report["journal_amortized_ms"] = round((perf_counter() - started) * 1000 / 64, 3)
        report.update(asyncio.run(recap_benchmark()))
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
