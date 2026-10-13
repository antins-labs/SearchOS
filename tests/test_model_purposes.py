"""模型用途迁移与会话依赖回归。"""

from types import SimpleNamespace


def test_retired_binding_is_ignored_in_env_and_overlay(monkeypatch):
    from searchos.config.settings import Settings
    from searchos.config.web_overlay import ModelsOverlay

    monkeypatch.setenv("SF_ROLES__SKILL_RUNTIME", "removed-profile")
    assert "skill_runtime" not in Settings(_env_file=None).roles
    overlay = ModelsOverlay.model_validate(
        {
            "roles": {
                "skill_runtime": "removed-profile",
                "judge": "custom-profile",
            }
        }
    )
    assert overlay.roles == {"judge": "custom-profile"}


def test_session_does_not_resolve_removed_skill_model(monkeypatch):
    import searchos.config.models as models
    from searchos.harness.session import SearchSession

    resolved = []

    def resolve(role):
        assert role != "skill_runtime"
        resolved.append(role)
        return SimpleNamespace(model_name="test-model")

    monkeypatch.setattr(models, "get_model_for", resolve)
    session = SearchSession()
    assert {"orchestrator", "judge", "extraction", "sub_agent"} <= set(resolved)
    assert "skill_runtime" not in session._model_distribution
