"""独立 Python 执行与携带原始来源的 edit。"""

import json
from types import SimpleNamespace

import pytest

from searchos.socm import CellStatus, SearchState
from searchos.socm.views.trace import resolve_cell_provenance
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import python_execution, schema


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = WorkspaceManager(tmp_path, "python-tools")
    ws.create()
    state = SearchState(source_scope={"mode": "hybrid", "documents": []})
    state.coverage_map.initialize(entities=["alpha"], attributes=["name", "value"],
                                  primary_key=["name"], table_id="items")
    ws.save_state(state)
    monkeypatch.setattr(schema, "_orch_ctx", lambda: SimpleNamespace(workspace=ws))
    return ws


async def edit(**fields):
    return await schema.edit_entities.ainvoke({
        "table_id": "items", "edits_json": json.dumps([
            {"entity": "alpha", "set": {"value": "25.0"}, **fields}
        ])})


@pytest.mark.asyncio
async def test_edit_keeps_original_source_without_requiring_python_receipt(workspace):
    source = "https://example.org/data"
    excerpt = "The total is 80 and the selected amount is 20."
    assert "Set 1" in await edit(source=source, source_excerpt=excerpt)
    state = workspace.load_state()
    cell = state.coverage_map.cells["items/alpha.value"]
    assert cell.status == CellStatus.FILLED and cell.display_hint == "25.0"
    node = state.evidence_graph.get_node(cell.primary_evidence_id)
    assert node.source == source and node.source_excerpt == excerpt
    assert not node.page_id and node.span is None  # no fabricated extraction anchor
    trace = resolve_cell_provenance(state, cell="items/alpha.value")[0]
    assert trace["source_url"] == source and trace["snippet"] == excerpt
    # Repeating an identical edit deduplicates its evidence.
    await edit(source=source, source_excerpt=excerpt)
    assert len(workspace.load_state().evidence_graph.nodes) == 1


@pytest.mark.asyncio
async def test_edit_distinguishes_sources_and_preserves_existing_scope_checks(workspace):
    for host in ("one", "two"):
        assert "Set 1" in await edit(source=f"https://{host}.example/data")
    state = workspace.load_state()
    assert {node.source for node in state.evidence_graph.nodes} == {
        "https://one.example/data", "https://two.example/data"}
    # Ordinary unsourced hybrid edits are still rejected.
    assert "Errors:" in await edit()
    assert "Errors:" in await edit(source="file:///private/key")
    assert "Errors:" in await edit(source="agent://made-up")
    # A local-only scope cannot be bypassed by supplying a Web source.
    state.source_scope = {"mode": "local", "documents": []}
    workspace.save_state(state)
    assert "Errors:" in await edit(source="https://three.example/data")


@pytest.mark.asyncio
async def test_python_rejects_empty_code_before_execution(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("invalid request launched a process")
    monkeypatch.setattr(python_execution, "run_command", unexpected)
    assert json.loads(await python_execution.python.ainvoke({"code": " "}))["status"] == "blocked"


@pytest.mark.asyncio
async def test_python_needs_no_workspace_and_cleans_temporary_files(monkeypatch):
    paths = []

    async def execute(script, argv, **kwargs):
        paths.append(script.parent)
        assert (script / "main.py").read_text() == "print(2 + 3)"
        assert kwargs["network"] is False
        return {"status": "completed", "stdout": "5\n", "stderr": "", "exit_code": 0,
                "execution_id": "internal", "artifacts": [{"path": "unused"}]}

    monkeypatch.setattr(python_execution, "run_command", execute)
    output = json.loads(await python_execution.python.ainvoke({"code": "print(2 + 3)"}))
    assert output == {"status": "completed", "stdout": "5\n", "stderr": "", "exit_code": 0}
    assert all(not path.exists() for path in paths)


@pytest.mark.asyncio
async def test_python_and_edit_real_execution(workspace):
    before = workspace.load_state().model_dump()
    output = json.loads(await python_execution.python.ainvoke({
        "code": "import json\nfrom decimal import Decimal\nprint(json.dumps({'value': str(Decimal('20') / Decimal('80') * 100)}))"}))
    if output["status"] == "blocked":
        pytest.skip("OS sandbox unavailable: " + output.get("error", ""))
    assert output["status"] == "completed", output
    assert output["exit_code"] == 0
    value = json.loads(output["stdout"])["value"]
    assert value == "25.00"
    assert workspace.load_state().model_dump() == before  # Python has no SOCM side effects
    response = await schema.edit_entities.ainvoke({"table_id": "items", "edits_json": json.dumps([
        {"entity": "alpha", "set": {"value": value}, "source": "https://example.org/data",
         "source_excerpt": "Selected: 20. Total: 80."}
    ])})
    assert "Set 1" in response
    assert workspace.load_state().coverage_map.cells["items/alpha.value"].display_hint == value
    assert not (workspace.path / "python").exists()
    assert "execution_id" not in output and "artifacts" not in output
    failed = json.loads(await python_execution.python.ainvoke({"code": "print(1 / 0)"}))
    assert failed["status"] == "failed" and "ZeroDivisionError" in failed["stderr"]


def test_tool_surface_and_general_calculation_guidance():
    from searchos.agents.orchestrator import get_orchestrator_tools
    from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
    from searchos.harness.middleware.pipelines import ORCHESTRATOR_DRAIN_TOOLS

    for mode in ("web", "hybrid"):
        assert "python" in {tool.name for tool in get_orchestrator_tools(source_mode=mode)}
        prompt = build_orchestrator_prompt("agents", "skills", source_mode=mode)
        assert "write Python code with those inputs" in prompt
        assert "original `source` and `source_excerpt`" in prompt
    assert "python" in ORCHESTRATOR_DRAIN_TOOLS
    assert set(python_execution.python.args) == {"code", "timeout_s"}
