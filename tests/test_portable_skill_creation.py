from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from searchos.skills.intent.trace import _existing_skill_dir
from searchos.skills.pipeline.access.tools import BuilderWorkspace
from searchos.skills.pipeline.access.valid import package_is_complete as _portable_skill_is_complete, validate_examples

EXAMPLE = Path(__file__).resolve().parents[1] / "searchos/skills/library/access/arxiv-search"


def test_portable_package_and_source_discovery(tmp_path):
    assert _portable_skill_is_complete(EXAMPLE, "arxiv-search")
    assert _existing_skill_dir(EXAMPLE.parent, "arxiv.org") == EXAMPLE
    hidden = tmp_path / ".staging_example-com"
    hidden.mkdir()
    (hidden / "SKILL.md").write_text("---\nname: example-com\nmetadata:\n  host: example.com\n---\n")
    assert _existing_skill_dir(tmp_path, "example.com") is None
    legacy = tmp_path / "example_com"
    legacy.mkdir()
    (legacy / "manifest.yaml").write_text("description: Legacy\n")
    assert _existing_skill_dir(tmp_path, "example.com") == legacy


def test_example_cli_runs_without_searchos_or_network(tmp_path):
    script = EXAMPLE / "scripts/search.py"
    output = tmp_path / "result.json"
    result = subprocess.run(
        [sys.executable, "-I", str(script), "--input", str(EXAMPLE / "references/example.atom"),
         "--output", str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text())
    assert data["input_mode"] == "fixture"
    assert data["records"][0]["title"] == "Synthetic retrieval example"
    assert data["records"][0]["source_url"].startswith("https://arxiv.org/")
    failure = subprocess.run(
        [sys.executable, "-I", str(script), "--query", "test", "--limit", "0"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert failure.returncode != 0
    assert "--limit" in failure.stderr


@pytest.mark.asyncio
async def test_example_registration_rejects_output_escape(tmp_path):
    workspace = BuilderWorkspace(tmp_path)
    with pytest.raises(ValueError):
        await workspace.dispatch("register_example", {
            "argv": ["python", "scripts/search.py"], "output": "../escape.json", "records_key": "records",
        })
    assert workspace.examples == []


@pytest.mark.asyncio
async def test_portable_gate_requires_data_and_uses_command_runtime(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime
    calls = []
    payload = {"records": [{"source_url": "https://example.com/item", "title": "Actual record"}]}

    async def fake_run(skill_dir, argv, **kwargs):
        calls.append((skill_dir, argv, kwargs))
        return {"exit_code": 0, "stdout": json.dumps(payload)}

    monkeypatch.setattr(command_runtime, "run_command", fake_run)
    examples = [{"argv": ["python", "scripts/search.py", "--query", "example"],
                 "output": "", "records_key": "records"}]
    assert not (await validate_examples(tmp_path, []))["valid"]
    assert (await validate_examples(tmp_path, examples))["valid"]
    assert calls[0][0] == tmp_path
    assert calls[0][1][-1] == "--help"
    assert calls[0][2]["network"] is False
    assert calls[1][2]["network"] is True
    payload["records"] = []
    assert not (await validate_examples(tmp_path, examples))["valid"]
    payload["records"] = [{"title": "Unattributed"}]
    assert not (await validate_examples(tmp_path, examples))["valid"]


@pytest.mark.asyncio
async def test_portable_gate_rejects_execution_failure(tmp_path, monkeypatch):
    from searchos.skills.runtime import command_runtime

    async def fake_run(*args, **kwargs):
        return {"exit_code": 1, "stdout": '{"records":[{"url":"https://example.com","title":"x"}]}'}

    monkeypatch.setattr(command_runtime, "run_command", fake_run)
    assert not (await validate_examples(tmp_path, [{
        "argv": ["python", "scripts/search.py"], "output": "", "records_key": "records",
    }]))["valid"]


@pytest.mark.asyncio
async def test_builder_installs_standard_package_after_valid_example(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage
    from searchos.skills.pipeline.access.run import build_skill
    from searchos.skills.runtime import command_runtime

    class Model:
        count = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.count += 1
            if self.count > 1:
                return AIMessage(content="Done")
            return AIMessage(content="", tool_calls=[
                {"id": "1", "name": "write_file", "args": {"path": "SKILL.md", "content":
                    "---\nname: example-com\ndescription: Retrieve example records.\nmetadata:\n  searchos-category: access\n  host: example.com\n---\nRun scripts/search.py.\n"}},
                {"id": "2", "name": "write_file", "args": {"path": "scripts/search.py", "content": "print('example')\n"}},
                {"id": "3", "name": "register_example", "args": {"argv": ["python", "scripts/search.py"], "output": "", "records_key": "records"}},
            ])

    async def fake_run(*args, **kwargs):
        return {"exit_code": 0, "stdout": '{"records":[{"url":"https://example.com/item","title":"Record"}]}'}

    monkeypatch.setattr(command_runtime, "run_command", fake_run)
    target = tmp_path / "example-com"
    assert await build_skill("example.com", ["https://example.com"], output_dir=target, builder_model=Model()) == target
    assert (target / "SKILL.md").is_file()
    assert not (target / "manifest.yaml").exists()
    assert not list(tmp_path.glob(".staging*"))
