"""设置接口的 Skill Availability 字段回归测试。"""

import os
from pathlib import Path

import pytest


@pytest.mark.parametrize("metadata", [{"availability": "enabled"}, {"status": "seed"}])
def test_settings_serializes_skill_availability(monkeypatch, metadata):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from fastapi.testclient import TestClient

    from api import skills_catalog
    from api.main import app
    from searchos.skills.core.models import Skill, SkillMeta

    skill = Skill(meta=SkillMeta(name="sample", **metadata), body="",
                  package_format="portable", package_hash="abc123")
    monkeypatch.setattr(
        skills_catalog, "skill_catalog",
        lambda: {"strategy": [skill], "access": [], "orchestrator": []},
    )
    monkeypatch.setattr(skills_catalog, "skill_enabled", lambda category, name: True)
    # 只测试读取路由，不启动会加载用户配置的 lifespan。
    client = TestClient(app)
    try:
        response = client.get("/api/settings")
    finally:
        client.close()
    assert response.status_code == 200
    item = response.json()["skills"]["categories"]["strategy"][0]
    assert item["name"] == "sample"
    assert item["status"] == "enabled"
    assert item["enabled"] is True
    assert item["package_format"] == "portable"
    assert item["package_hash"] == "abc123"
