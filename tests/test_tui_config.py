"""searchos/tui/config_modal.py — 设置面板 item 构建器的 setter/校验逻辑。

Item 的 get/set 是纯闭包（持久化在闭包内完成），无需运行 Textual 即可单测。
overlay 与 settings 都是模块级单例：重定向落盘到 tmp、结束时还原。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from searchos.tui import config_modal as cm


@pytest.fixture()
def clean_overlay(tmp_path, monkeypatch):
    from searchos.config import web_overlay as wo
    from searchos.config.settings import reload_settings_in_place

    monkeypatch.setenv("SF_WEB_SETTINGS_PATH", str(tmp_path / "web_settings.json"))
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "SERPER_API_KEY", "TAVILY_API_KEY",
                "MY_KEY", "A_KEY", "B_KEY"):
        monkeypatch.delenv(var, raising=False)
    env_snapshot = dict(os.environ)

    wo._replace_store(wo.WebSettings())
    yield wo

    os.environ.clear()
    os.environ.update(env_snapshot)
    wo._replace_store(wo.WebSettings())
    reload_settings_in_place()


@pytest.fixture()
def app():
    """最小 app 桩：不重建搜索 provider、effort 应用记录调用即可。"""
    calls: list[str] = []
    stub = SimpleNamespace(_no_search=True,
                           _apply_effort=lambda lvl: calls.append(lvl))
    stub.effort_calls = calls
    return stub


def _items(builder):
    _title, items = builder()
    return items


def _item(items, label):
    hit = next((i for i in items if i.label == label), None)
    if hit is None:
        hit = next(i for i in items if i.label.startswith(label))
    return hit


# ---------------------------------------------------------------------------
# Search / Browse / Budget / Runtime knobs
# ---------------------------------------------------------------------------

def test_search_backend_guard_and_set(clean_overlay, app, monkeypatch):
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "serper_api_key", "", raising=False)
    item = _item(cm._search_section_items(app), "搜索后端")

    err = item.set("serper")
    assert err and "SERPER_API_KEY" in err          # 无 key 拒绝
    assert clean_overlay.store.models.search_provider is None

    monkeypatch.setenv("SERPER_API_KEY", "sk-x")
    assert item.set("serper") is None
    assert clean_overlay.store.models.search_provider == "serper"
    assert item.get() == "serper"

    assert item.set("auto") is None                 # auto = 清除显式配置
    assert clean_overlay.store.models.search_provider is None


def test_proxy_and_results_and_cache(clean_overlay, app):
    from searchos.config.settings import settings

    search = cm._search_section_items(app)
    proxy = _item(search, "代理 (HTTP/HTTPS)")
    assert proxy.set("http://127.0.0.1:7890") is None
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert proxy.set("") is None                    # 空串 = 强制无代理
    assert "HTTP_PROXY" not in os.environ
    assert clean_overlay.store.advanced.https_proxy == ""

    results = _item(search, "每查询结果数")
    assert results.set(0) and clean_overlay.store.run_defaults.search_max_results is None
    assert results.set(5) is None
    assert settings.search_max_results == 5

    cache = _item(cm._browse_section_items(app), "页面缓存目录")
    assert cache.set("/tmp/sos-cache") is None
    assert settings.browser_disk_cache_dir == "/tmp/sos-cache"
    assert clean_overlay.store.advanced.browser_disk_cache_dir == "/tmp/sos-cache"


def test_budget_and_runtime_knobs(clean_overlay, app):
    from searchos.config.settings import settings

    budget = cm._budget_section_items(app)
    retries = _item(budget, "LLM 重试")
    assert retries.set(99) and clean_overlay.store.advanced.llm_max_retries is None
    assert retries.set(7) is None
    assert settings.llm_max_retries == 7
    base = None
    assert retries.set(base) is None                # 留空 = 清除覆盖
    assert clean_overlay.store.advanced.llm_max_retries is None

    effort = _item(budget, "effort 档位")
    assert effort.set("high") is None
    assert app.effort_calls == ["high"]             # 交给 app._apply_effort 持久化

    skills = _item(cm._runtime_section_items(app), "技能系统")
    assert skills.set(False) is None
    assert settings.enable_skills is False
    assert clean_overlay.store.run_defaults.enable_skills is False


def test_browser_backend_choice(clean_overlay, app):
    from searchos.config.settings import settings

    backend = _item(cm._browse_section_items(app), "浏览后端")
    assert backend.set("aiohttp") is None
    assert settings.browser_backend == "aiohttp"
    assert clean_overlay.store.models.browser_backend == "aiohttp"


# ---------------------------------------------------------------------------
# Model 区：连接 / 模型卡 / 角色绑定 生命周期
# ---------------------------------------------------------------------------

def test_connection_and_profile_lifecycle(clean_overlay, app):
    from searchos.config.settings import settings

    # 新建连接（校验 + 落 store）
    assert "字母数字" in cm._create_connection({"name": "bad name", "key_env": "K_E"})
    assert cm._create_connection(
        {"name": "conn1", "protocol": "openai_compatible",
         "api_base": "http://localhost:8000/v1", "key_env": "MY_KEY"}) is None
    assert "conn1" in clean_overlay.store.models.provider_connections
    assert "已存在" in cm._create_connection({"name": "conn1", "key_env": "MY_KEY"})

    # 新建模型卡（保留名 / 缺 ref / 成功）
    assert "保留名" in cm._create_profile(
        {"name": "main", "model": "m", "provider_ref": "conn1"})
    assert "连接" in cm._create_profile({"name": "card1", "model": "m1",
                                         "provider_ref": None})
    assert cm._create_profile(
        {"name": "card1", "model": "m1", "provider_ref": "conn1"}) is None
    assert settings.profiles["card1"].model == "m1"
    assert settings.profiles["card1"].api_key_env == "MY_KEY"

    # 卡字段编辑（自定义卡就地改）
    assert cm._set_profile_field("card1", "temperature", 0.3) is None
    assert settings.profiles["card1"].temperature == 0.3
    assert cm._set_profile_field("card1", "model", "") == "model id 不能为空"

    # 角色绑定（key 未设 → 应用但带 ⚠ 警告）
    prev = settings.roles["orchestrator"]
    warn = cm._set_role("orchestrator", "card1")
    assert warn is not None and warn.startswith("⚠")
    assert settings.roles["orchestrator"] == "card1"
    assert cm._set_role("orchestrator", "nope")     # 未知卡拒绝
    assert settings.roles["orchestrator"] == "card1"

    # 被绑定的卡不能删；解绑后可删
    assert "角色" in cm._delete_profile("card1")
    rebind = cm._set_role("orchestrator", prev)
    assert rebind is None or rebind.startswith("⚠")
    assert cm._delete_profile("card1") is None
    assert "card1" not in settings.profiles
    assert "card1" not in clean_overlay.store.models.custom_profiles

    # 连接被引用时不能删；无引用后可删
    assert cm._create_profile(
        {"name": "card2", "model": "m2", "provider_ref": "conn1"}) is None
    assert "引用" in cm._delete_connection("conn1")
    assert cm._delete_profile("card2") is None
    assert cm._delete_connection("conn1") is None
    assert "conn1" not in clean_overlay.store.models.provider_connections


def test_base_profile_override_roundtrip(clean_overlay, app):
    from searchos.config.settings import settings

    base = next(n for n in settings.profiles
                if n not in clean_overlay.store.models.custom_profiles)
    original = settings.profiles[base].model

    assert cm._set_profile_field(base, "model", "override-model") is None
    assert settings.profiles[base].model == "override-model"
    assert clean_overlay.store.models.profile_overrides[base].model == "override-model"

    assert cm._set_profile_field(base, "model", "") is None  # 清除覆盖
    assert base not in clean_overlay.store.models.profile_overrides
    assert settings.profiles[base].model == original


def test_conn_key_envs_validation(clean_overlay, app):
    assert cm._create_connection(
        {"name": "c2", "api_base": "", "key_env": "A_KEY"}) is None
    assert "AN_ENV_VAR_NAME" in cm._set_conn_key_envs("c2", "bad-name")
    assert "至少" in cm._set_conn_key_envs("c2", "  ")
    assert cm._set_conn_key_envs("c2", "A_KEY, B_KEY") is None
    conn = clean_overlay.store.models.provider_connections["c2"]
    assert conn.api_key_envs == ["A_KEY", "B_KEY"]


# ---------------------------------------------------------------------------
# 密钥值 → .env（原子写 + 同步 os.environ，绝不回显）
# ---------------------------------------------------------------------------

def test_secret_write_and_clear(clean_overlay, app, tmp_path, monkeypatch):
    import searchos.config.env_file as ef

    env = tmp_path / ".env"
    monkeypatch.setattr(ef, "find_env_path", lambda start=None: env)

    assert cm._set_key("SERPER_API_KEY", "bad value")   # 空格拒绝
    assert not env.exists()

    assert cm._set_key("SERPER_API_KEY", "sk-abc") is None
    assert "SERPER_API_KEY=sk-abc" in env.read_text()
    assert os.environ["SERPER_API_KEY"] == "sk-abc"

    item = cm._secret_item("Serper key", "SERPER_API_KEY")
    assert item.get() is True
    assert item.set("") is None                          # 清除
    assert os.environ.get("SERPER_API_KEY") is None
    assert item.get() is False


# ---------------------------------------------------------------------------
# Textual 冒烟：按键驱动一遍 开关切换 / 内联编辑 / 子菜单 / Esc 关闭
# ---------------------------------------------------------------------------

async def test_modal_smoke_keyboard_flow(clean_overlay, app):
    from textual.app import App
    from textual.widgets import Input, OptionList

    from searchos.config.settings import settings

    dismissed: list = []

    class Host(App):
        def on_mount(self):
            self.push_screen(cm.ConfigModal(cm.build_root_menu(app)),
                             dismissed.append)

    host = Host()
    async with host.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        modal = host.screen
        assert isinstance(modal, cm.ConfigModal)
        ol = modal.query_one("#cfg-list", OptionList)

        def goto(label: str):
            idx = next(i for i, it in enumerate(modal._items)
                       if it.label == label)
            ol.highlighted = idx

        # bool：回车切换
        goto("技能系统")
        await pilot.press("enter")
        assert clean_overlay.store.run_defaults.enable_skills is False

        # int：回车打开内联编辑，输入后回车保存
        goto("LLM 重试")
        await pilot.press("enter")
        assert str(modal.query_one("#cfg-edit", Input).styles.display) == "block"
        await pilot.press("7", "enter")
        assert settings.llm_max_retries == 7

        # submenu：进入「角色绑定」，Esc 逐级返回
        goto("角色绑定")
        await pilot.press("enter")
        assert len(modal._stack) == 2
        await pilot.press("escape")
        assert len(modal._stack) == 1

        # 根层 Esc 关闭，返回变更计数
        await pilot.press("escape")
        await pilot.pause()

    assert dismissed == [2]
