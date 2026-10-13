"""移除 Blueprint 后的配置读取与会话覆盖。"""

import asyncio
from pathlib import Path

import pytest

from searchos.config.settings import settings
from searchos.harness.session import SearchSession
from searchos.skills.catalog.registry import SkillRegistry


@pytest.mark.parametrize("override, expected", [(None, 321), (0, 0), (45, 45)])
def test_session_budget_uses_current_settings_or_explicit_override(
    monkeypatch, tmp_path, override, expected,
):
    from searchos.config import models
    from searchos.harness.middleware.sensor.core import models as budget

    monkeypatch.setattr(models, "get_model_for", lambda role: object())
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "skill_library_path", str(tmp_path / "skills"))
    monkeypatch.setattr(settings, "default_max_time_s", 100)
    session = SearchSession(
        max_time_s=override,
        skill_registry=SkillRegistry(),
        workspace_root=str(tmp_path / "workspaces"),
    )
    assert session._skill_library_path == str(tmp_path / "skills")
    monkeypatch.setattr(settings, "default_max_time_s", 321)

    class BudgetCaptured(Exception):
        pass

    def capture_budget(**kwargs):
        assert kwargs["max_time_s"] == expected
        raise BudgetCaptured

    monkeypatch.setattr(budget, "BudgetState", capture_budget)
    with pytest.raises(BudgetCaptured):
        asyncio.run(session.run("test configuration", session_id="settings-test"))
    assert settings.default_max_time_s == 321


@pytest.mark.parametrize(
    "requested, stored, expected", [(0, 60, 0), (None, 0, 0), (None, None, 321), (45, 60, 45)],
)
def test_web_budget_override_preserves_zero(monkeypatch, requested, stored, expected):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes import search

    from searchos.harness import session as session_module

    captured = {}

    class Session:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run(self, *args, **kwargs):
            return None

    monkeypatch.setattr(session_module, "SearchSession", Session)
    monkeypatch.setattr(search, "sessions", {})
    monkeypatch.setattr(search.skills_catalog, "effective_skill_kwargs", lambda _: {})
    monkeypatch.setattr(search.settings_store.store.run_defaults, "max_time_s", stored)
    monkeypatch.setattr(settings, "default_max_time_s", 321)

    async def run():
        await search._launch_search(
            req=search.SearchRequest(query="test", max_time=requested),
            session_id="budget-test", state=None, context_preamble=None,
            follow_up=False, query="test",
        )
        await search.sessions["budget-test"]["task"]

    asyncio.run(run())
    assert captured["max_time_s"] == expected
    assert settings.default_max_time_s == 321


def test_workspace_names_sort_by_local_time_and_keep_legacy_ids(tmp_path, monkeypatch):
    from datetime import datetime

    from searchos.socm import workspace

    class Clock:
        @staticmethod
        def now():
            return datetime(2026, 9, 13, 14, 19, 2)

    monkeypatch.setattr(workspace, "datetime", Clock)
    first = workspace.WorkspaceManager(tmp_path)
    second = workspace.WorkspaceManager(tmp_path)
    assert first.session_id.startswith("20260913_141902_")
    assert first.session_id != second.session_id
    legacy = workspace.WorkspaceManager(tmp_path, "9383abbc1319")
    legacy.create()
    assert legacy.path == tmp_path / "9383abbc1319"


@pytest.mark.asyncio
async def test_timestamp_directory_remains_accessible_by_old_id(tmp_path, monkeypatch):
    import json

    from api.routes import history, search
    from api.routes import workspace as workspace_api

    from searchos.socm.workspace import WorkspaceManager

    old_id = "0b7daafb688c"
    new_id = "20260913_172557_" + old_id
    ws = WorkspaceManager(tmp_path, new_id)
    ws.create()
    from searchos.socm import SearchState
    ws.save_state(SearchState(intent="Preserved question"))
    ws.write_output("result.json", json.dumps({"query": "Preserved question", "answer": "Preserved answer"}))
    for module in [history, search, workspace_api]:
        monkeypatch.setattr(module, "WORKSPACE_ROOT", str(tmp_path))
    restored = WorkspaceManager(tmp_path, old_id)
    assert restored.path == ws.path
    assert restored.session_id == new_id
    assert search._load_prior_state(old_id).intent == "Preserved question"
    loaded = await history.load_history(old_id)
    assert loaded["session_id"] == new_id
    file = await workspace_api.get_file_content(old_id, "output/result.json")
    assert "Preserved answer" in file["content"]
    listed = await history.list_history()
    assert [item["session_id"] for item in listed] == [new_id]

    async def launch(**kwargs):
        assert kwargs["session_id"] == new_id
        return search.SearchResponse(session_id=kwargs["session_id"], status="running")

    monkeypatch.setattr(search, "_launch_search", launch)
    monkeypatch.setattr(search, "init_search_provider", lambda *args: None)
    resumed = await search.create_search(search.SearchRequest(query="Follow up", follow_up_to=old_id))
    assert resumed.session_id == new_id
    assert not (tmp_path / old_id).exists()


def test_session_path_rejects_ambiguous_legacy_ids_and_traversal(tmp_path):
    from searchos.socm.workspace import resolve_session_path

    for stamp in ["20260913_172557", "20260913_172558"]:
        (tmp_path / f"{stamp}_0b7daafb688c").mkdir()
    with pytest.raises(ValueError):
        resolve_session_path(tmp_path, "0b7daafb688c")
    with pytest.raises(ValueError):
        resolve_session_path(tmp_path, "../escape")
