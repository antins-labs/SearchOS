"""Claude-Code-style interactive settings panel for the TUI.

One generic ``ConfigModal``（可滚动列表 + ↑↓ 导航 + Enter 编辑/切换 + Esc 逐级
返回）drives every section, mirroring the web Settings page: Model（角色绑定 /
模型卡 / Provider 连接）、Search、Browse、Budget、Experimental、Runtime。All edits persist
IMMEDIATELY to the shared ``web_settings.json`` overlay（overlay 写入 +
``apply_to_runtime()`` + ``save_overlay()``，与 web 的「PUT 即持久」语义一致）；
API-key VALUES go to ``.env`` via the same atomic writer the web/wizard use and
are never echoed back（只显示 ●已设置/○未设置）。

The item tree is data, not widgets: each row is an :class:`Item` whose
``get``/``set`` closures own the persistence, so builders are unit-testable
without a running Textual app. Interaction conventions follow Claude Code:
Enter toggles bools / cycles enums / opens an inline editor for text, ←→ also
cycle enums, destructive actions need a second Enter to confirm.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from searchos.tui.dashboard import ACCENT, C_AGENTS, DANGER, FAINT, MUTED, WARN

# 与 web/api/routes/models.py 的校验保持一致（searchos 不能反向依赖 web 包，
# 故常量在此复刻；改动时两处同步）。
_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RESERVED_PROFILE_NAMES = {"main", "judge", "fast", "synthesis", "reformat"}

_PROTOCOLS = ("openai_compatible", "openai", "anthropic")
_THINKING_STYLES = ("none", "chat_template_kwargs", "enable_thinking")
_BROWSER_BACKENDS = ("jina", "aiohttp", "crawl4ai", "search_engine")

_ROLE_HELP = {
    "orchestrator": "主编排 ReAct 循环",
    "sub_agent": "搜索/探索子代理循环",
    "synthesis": "写作代理 + 最终答案",
    "skill_evolver": "access 技能生成评审",
    "post_mortem": "FailureMemory 蒸馏",
    "judge": "sensor / 分层上下文评审",
    "extraction": "证据抽取中间件",
    "alias_resolver": "孤儿证据行列绑定",
    "skill_runtime": "T2/T3 access 技能执行器",
    "reformat": "评测答案重排",
    "skill_router": "技能目录 top-k 预筛",
}


# --------------------------------------------------------------------------
# Item model — a row in the panel. ``set`` returns None on success, a "⚠ …"
# string for applied-with-warning, or any other string as a rejection reason
# (the value was NOT applied).
# --------------------------------------------------------------------------

@dataclass
class Item:
    kind: str                       # header|bool|choice|text|int|float|secret|submenu|action
    label: str
    get: Callable[[], Any] | None = None
    set: Callable[[Any], str | None] | None = None
    choices: Callable[[], list[str]] | None = None
    submenu: Callable[[], tuple[str, list[Item]]] | None = None
    help: str | Callable[[], str] = ""
    placeholder: str = ""
    confirm: str = ""               # non-empty → double-Enter action
    pop_after: bool = False         # pop one level after the action succeeds
    disabled: Callable[[], str] | None = None  # reason string when disabled
    counts: bool = True             # False = draft-only edit, not a persisted change
    extra: dict = field(default_factory=dict)


MenuBuilder = Callable[[], tuple[str, list[Item]]]


# --------------------------------------------------------------------------
# Shared persistence helpers（懒 import，避免模块加载即构造 settings 单例）
# --------------------------------------------------------------------------

def _settings():
    from searchos.config.settings import settings
    return settings


def _store():
    from searchos.config.web_overlay import store
    return store


def _sync(reload: bool = False) -> None:
    """Persist the overlay and push it onto the runtime settings.

    ``reload=True`` first rebuilds the settings singleton from env — required
    whenever an overlay override is CLEARED or a connection edit must re-flow
    into cards（same reason web's settings_store.update(reload=True) exists：
    plain replay can't un-mutate a field）.
    """
    from searchos.config.web_overlay import apply_to_runtime, save_overlay
    if reload:
        from searchos.config.settings import reload_settings_in_place
        reload_settings_in_place()
    apply_to_runtime()
    save_overlay()


def _key_set(env: str, fallback: str = "") -> bool:
    return bool(os.environ.get(env) or fallback)


def _set_key(env: str, value: str) -> str | None:
    """Write one API-key VALUE to .env（原子写 + 同步 os.environ；"" 清除）。"""
    from searchos.config.env_file import (
        apply_env_updates,
        find_env_path,
        validate_env_value,
    )
    try:
        validate_env_value(value)
    except ValueError as e:
        return str(e)
    apply_env_updates(find_env_path(), {env: value})
    return None


def _secret_item(label: str, env: str, fallback: str = "", help: str = "") -> Item:
    return Item(
        "secret", label,
        get=lambda: _key_set(env, fallback),
        set=lambda v: _set_key(env, v),
        help=help or f"值写入 .env 的 {env}（回车输入，留空=清除）",
        placeholder=env,
    )


# --------------------------------------------------------------------------
# Model 区 — 角色绑定 / 模型卡 / Provider 连接
# --------------------------------------------------------------------------

def _set_role(role: str, profile: str) -> str | None:
    s = _settings()
    if profile not in s.profiles:
        return f"未知模型卡 {profile!r}"
    _store().models.roles[role] = profile
    _sync()
    p = s.profiles[profile]
    if not _key_set(p.api_key_env, getattr(p, "api_key_fallback", "")):
        return f"⚠ 模型卡 {profile} 需要 {p.api_key_env}，当前未设置"
    return None


def _roles_menu(app) -> MenuBuilder:
    def build():
        from searchos.config.settings import ROLE_NAMES
        items = [
            Item(
                "choice", role,
                get=lambda r=role: _settings().roles.get(r, ""),
                set=lambda v, r=role: _set_role(r, v),
                choices=lambda: list(_settings().profiles),
                help=_ROLE_HELP.get(role, ""),
            )
            for role in ROLE_NAMES
        ]
        return "角色绑定", items
    return build


def _override_for(name: str):
    """Get-or-create the sparse override record for a base profile."""
    from searchos.config.web_overlay import ProfileOverride
    st = _store()
    ov = st.models.profile_overrides.get(name)
    if ov is None:
        ov = ProfileOverride()
        st.models.profile_overrides[name] = ov
    return ov


def _prune_override(name: str) -> None:
    from searchos.config.web_overlay import ProfileOverride
    st = _store()
    ov = st.models.profile_overrides.get(name)
    if ov is not None and all(
        getattr(ov, f) is None for f in ProfileOverride.model_fields
    ):
        st.models.profile_overrides.pop(name)


def _set_profile_field(name: str, fld: str, value) -> str | None:
    """Edit one card field. Custom cards edit in place; base cards write a
    sparse override（空值 = 清除该覆盖、还原 env 基础值）。"""
    cp = _store().models.custom_profiles.get(name)
    if cp is not None:
        if fld == "model":
            if not (value or "").strip():
                return "model id 不能为空"
            cp.model = value.strip()
        elif fld == "api_base":
            cp.api_base = (value or "").strip()
        elif fld == "api_key_env":
            if not value:
                return "api_key_env 不能为空"
            cp.api_key_env = value
        elif fld == "provider_ref":
            cp.provider_ref = value or None
        elif fld == "temperature":
            cp.temperature = value  # None = 不传该参数
        elif fld == "enable_thinking":
            cp.enable_thinking = bool(value)
        else:
            return f"未知字段 {fld!r}"
        _sync(reload=True)
        return None
    ov = _override_for(name)
    setattr(ov, fld, value if value not in ("", None) else None)
    _prune_override(name)
    _sync(reload=True)
    return None


def _delete_profile(name: str) -> str | None:
    st = _store()
    if name not in st.models.custom_profiles:
        return "只能删除自定义模型卡"
    bound = sorted(r for r, p in _settings().roles.items() if p == name)
    if bound:
        return f"该卡绑定在角色 {', '.join(bound)} 上——先改绑再删"
    st.models.custom_profiles.pop(name, None)
    st.models.profile_overrides.pop(name, None)
    st.models.roles = {r: p for r, p in st.models.roles.items() if p != name}
    _sync(reload=True)
    return None


_NO_REF = "（无）"


def _profile_editor(app, name: str) -> MenuBuilder:
    def build():
        s, st = _settings(), _store()
        p = s.profiles.get(name)
        if p is None:  # deleted underneath us
            return f"模型卡 {name}", [Item("header", "（此卡已不存在，Esc 返回）")]
        cp = st.models.custom_profiles.get(name)
        is_custom = cp is not None
        ov = st.models.profile_overrides.get(name)
        conns = st.models.provider_connections
        ref = cp.provider_ref if is_custom else (ov.provider_ref if ov else None)
        conn = conns.get(ref) if ref else None

        clear_hint = "" if is_custom else "（留空=清除覆盖、还原默认）"
        items: list[Item] = [
            Item("text", "model id",
                 get=lambda: p.model,
                 set=lambda v: _set_profile_field(name, "model", v),
                 help=f"发给该 provider 的模型标识{clear_hint}"),
            Item("choice", "Provider 连接",
                 get=lambda: ref or _NO_REF,
                 set=lambda v: _set_profile_field(
                     name, "provider_ref", None if v == _NO_REF else v),
                 choices=lambda: [_NO_REF, *conns],
                 help="指向连接后，协议/endpoint/key/思考风格全部继承自连接"),
        ]
        if conn is not None and len(conn.api_key_envs) > 1:
            cur_env = (cp.api_key_env if is_custom else (ov.api_key_env if ov else None))
            items.append(Item(
                "choice", "API key",
                get=lambda: conn.resolve_key_env(cur_env),
                set=lambda v: _set_profile_field(name, "api_key_env", v),
                choices=lambda: list(conn.api_key_envs),
                help="连接带多把 key 时，这张卡用哪一把"))
        if conn is None:
            items += [
                Item("text", "api_base",
                     get=lambda: p.api_base,
                     set=lambda v: _set_profile_field(name, "api_base", v),
                     help=f"无连接时的内联 endpoint{clear_hint}"),
                Item("text", "api_key_env",
                     get=lambda: p.api_key_env,
                     set=lambda v: (
                         "需形如 AN_ENV_VAR_NAME" if v and not _ENV_NAME_RE.fullmatch(v)
                         else _set_profile_field(name, "api_key_env", v)),
                     help=f"无连接时的内联 key 环境变量名{clear_hint}"),
            ]
        items.append(Item(
            "float", "temperature",
            get=lambda: p.temperature,
            set=lambda v: _set_profile_field(name, "temperature", v),
            help="留空=不传该参数（部分网关会拒绝显式 temperature）"))
        if is_custom:
            def _set_max_tokens(v):
                if v is None or v < 1:
                    return "需要 ≥1 的整数"
                cp.max_tokens = v
                _sync(reload=True)
                return None
            items.append(Item("int", "max_tokens",
                              get=lambda: cp.max_tokens, set=_set_max_tokens))
        style = conn.thinking_style if conn else p.thinking_style

        def _set_thinking(v):
            if is_custom:
                cp.enable_thinking = bool(v)
            else:
                _override_for(name).enable_thinking = bool(v)
            _sync(reload=True)
            return None

        items.append(Item(
            "bool", "思考模式 (thinking)",
            get=lambda: p.enable_thinking,
            set=_set_thinking,
            disabled=lambda: (
                "连接 thinking_style=none 时不可用" if style == "none" else ""),
            help="随请求下发思考开关；具体字段拼法由连接的 thinking_style 决定"))
        if is_custom:
            items.append(Item(
                "action", "🗑 删除此卡",
                set=lambda _v: _delete_profile(name),
                confirm="删除自定义模型卡", pop_after=True))
        return f"模型卡 {name}", items
    return build


def _create_profile(draft: dict) -> str | None:
    s, st = _settings(), _store()
    name = (draft.get("name") or "").strip()
    model = (draft.get("model") or "").strip()
    ref = draft.get("provider_ref")
    if not _PROFILE_NAME_RE.fullmatch(name):
        return "名称需为字母数字加 . _ -（≤64 字符）"
    if name in _RESERVED_PROFILE_NAMES:
        return f"{name!r} 是预设保留名"
    if name in s.profiles or name in st.models.custom_profiles:
        return f"模型卡 {name!r} 已存在"
    if not model:
        return "model id 不能为空"
    if not ref or ref not in st.models.provider_connections:
        return "先选择一个 Provider 连接（没有就先去「Provider 连接」新建）"
    from searchos.config.web_overlay import CustomProfile
    conn = st.models.provider_connections[ref]
    st.models.custom_profiles[name] = CustomProfile(
        model=model, provider_ref=ref,
        api_key_env=conn.primary_key_env,
        temperature=draft.get("temperature"),
    )
    _sync()
    return None


def _new_profile_menu(app) -> MenuBuilder:
    draft: dict = {"name": "", "model": "", "provider_ref": None, "temperature": None}

    def build():
        conns = list(_store().models.provider_connections)
        if draft["provider_ref"] is None and conns:
            draft["provider_ref"] = conns[0]
        items = [
            Item("text", "名称", get=lambda: draft["name"],
                 set=lambda v: draft.__setitem__("name", v), counts=False,
                 help="卡名（main/judge/fast/synthesis/reformat 为保留名）",
                 placeholder="my-card"),
            Item("text", "model id", get=lambda: draft["model"],
                 set=lambda v: draft.__setitem__("model", v), counts=False,
                 placeholder="glm-5 / qwen3:32b …"),
            Item("choice", "Provider 连接",
                 get=lambda: draft["provider_ref"] or _NO_REF,
                 set=lambda v: draft.__setitem__(
                     "provider_ref", None if v == _NO_REF else v),
                 choices=lambda: [*conns] if conns else [_NO_REF], counts=False),
            Item("float", "temperature", get=lambda: draft["temperature"],
                 set=lambda v: draft.__setitem__("temperature", v), counts=False,
                 help="留空=不传该参数"),
            Item("action", "✚ 创建",
                 set=lambda _v: _create_profile(draft), pop_after=True,
                 help="创建后回上级列表；在「角色绑定」里把角色指到新卡"),
        ]
        return "新建模型卡", items
    return build


def _profiles_menu(app) -> MenuBuilder:
    def build():
        st = _store()
        items: list[Item] = []
        for name in _settings().profiles:
            tag = " · 自定义" if name in st.models.custom_profiles else ""
            ovd = " *" if name in st.models.profile_overrides else ""
            items.append(Item(
                "submenu", f"{name}{tag}{ovd}",
                get=lambda n=name: _settings().profiles[n].model,
                submenu=_profile_editor(app, name),
                help="* = 有字段覆盖；回车进入编辑"))
        items.append(Item("submenu", "✚ 新建模型卡", submenu=_new_profile_menu(app)))
        return "模型卡", items
    return build


def _set_conn_field(name: str, fld: str, value) -> str | None:
    conn = _store().models.provider_connections.get(name)
    if conn is None:
        return "连接已不存在"
    setattr(conn, fld, value)
    _sync(reload=True)  # 引用此连接的卡需要按新字段重建
    return None


def _set_conn_key_envs(name: str, raw: str) -> str | None:
    conn = _store().models.provider_connections.get(name)
    if conn is None:
        return "连接已不存在"
    envs: list[str] = []
    for tok in raw.replace(",", " ").split():
        if not _ENV_NAME_RE.fullmatch(tok):
            return f"{tok!r} 需形如 AN_ENV_VAR_NAME"
        if tok not in envs:
            envs.append(tok)
    if not envs:
        return "至少需要一个 key 环境变量名"
    conn.api_key_envs = envs
    _sync(reload=True)
    return None


def _delete_connection(name: str) -> str | None:
    st = _store()
    if name not in st.models.provider_connections:
        return "连接已不存在"
    used = sorted(
        p for p, cp in st.models.custom_profiles.items() if cp.provider_ref == name
    ) + sorted(
        p for p, ov in st.models.profile_overrides.items() if ov.provider_ref == name
    )
    if used:
        return f"连接被模型卡 {', '.join(used)} 引用——先改指向再删"
    st.models.provider_connections.pop(name)
    _sync(reload=True)
    return None


def _connection_editor(app, name: str) -> MenuBuilder:
    def build():
        conn = _store().models.provider_connections.get(name)
        if conn is None:
            return f"连接 {name}", [Item("header", "（此连接已不存在，Esc 返回）")]
        items: list[Item] = [
            Item("choice", "协议",
                 get=lambda: conn.protocol,
                 set=lambda v: _set_conn_field(name, "protocol", v),
                 choices=lambda: list(_PROTOCOLS)),
            Item("text", "api_base",
                 get=lambda: conn.api_base,
                 set=lambda v: _set_conn_field(name, "api_base", v.strip()),
                 placeholder="https://…/v1"),
            Item("choice", "思考风格",
                 get=lambda: conn.thinking_style,
                 set=lambda v: _set_conn_field(name, "thinking_style", v),
                 choices=lambda: list(_THINKING_STYLES),
                 help="thinking 开关在请求里的拼法；none = 该端点不支持思考"),
            Item("text", "备注 label",
                 get=lambda: conn.label,
                 set=lambda v: _set_conn_field(name, "label", v.strip())),
            Item("header", "API keys（值写入 .env，不回显）"),
        ]
        for i, env in enumerate(conn.api_key_envs):
            suffix = "（默认）" if i == 0 else ""
            items.append(_secret_item(f"{env}{suffix}", env))
        items.append(Item(
            "text", "key env 列表",
            get=lambda: ", ".join(conn.api_key_envs),
            set=lambda v: _set_conn_key_envs(name, v),
            help="逗号/空格分隔的环境变量名；第一个为默认 key"))
        items.append(Item(
            "action", "🗑 删除连接",
            set=lambda _v: _delete_connection(name),
            confirm="删除 Provider 连接", pop_after=True))
        return f"连接 {name}", items
    return build


def _create_connection(draft: dict) -> str | None:
    st = _store()
    name = (draft.get("name") or "").strip()
    key_env = (draft.get("key_env") or "").strip()
    if not _PROFILE_NAME_RE.fullmatch(name):
        return "名称需为字母数字加 . _ -（≤64 字符）"
    if name in st.models.provider_connections:
        return f"连接 {name!r} 已存在"
    if not _ENV_NAME_RE.fullmatch(key_env):
        return "key env 需形如 AN_ENV_VAR_NAME"
    from searchos.config.web_overlay import ProviderConnection
    st.models.provider_connections[name] = ProviderConnection(
        protocol=draft.get("protocol") or "openai_compatible",
        api_base=(draft.get("api_base") or "").strip(),
        api_key_envs=[key_env],
        thinking_style=draft.get("thinking_style") or "none",
    )
    _sync(reload=True)
    return None


def _new_connection_menu(app) -> MenuBuilder:
    draft: dict = {"name": "", "protocol": "openai_compatible", "api_base": "",
                   "key_env": "OPENAI_API_KEY", "thinking_style": "none"}

    def build():
        items = [
            Item("text", "名称", get=lambda: draft["name"],
                 set=lambda v: draft.__setitem__("name", v), counts=False,
                 placeholder="my-provider"),
            Item("choice", "协议", get=lambda: draft["protocol"],
                 set=lambda v: draft.__setitem__("protocol", v), counts=False,
                 choices=lambda: list(_PROTOCOLS)),
            Item("text", "api_base", get=lambda: draft["api_base"],
                 set=lambda v: draft.__setitem__("api_base", v), counts=False,
                 placeholder="https://…/v1"),
            Item("text", "key env", get=lambda: draft["key_env"],
                 set=lambda v: draft.__setitem__("key_env", v), counts=False,
                 help="装 API key 值的环境变量名（值稍后在连接详情里填）"),
            Item("choice", "思考风格", get=lambda: draft["thinking_style"],
                 set=lambda v: draft.__setitem__("thinking_style", v), counts=False,
                 choices=lambda: list(_THINKING_STYLES)),
            Item("action", "✚ 创建",
                 set=lambda _v: _create_connection(draft), pop_after=True),
        ]
        return "新建连接", items
    return build


def _connections_menu(app) -> MenuBuilder:
    def build():
        conns = _store().models.provider_connections
        items: list[Item] = []
        for name, c in conns.items():
            def _summary(c=c):
                dot = "●" if any(_key_set(e) for e in c.api_key_envs) else "○"
                return f"{dot} {c.api_base or c.protocol}"
            items.append(Item("submenu", name, get=_summary,
                              submenu=_connection_editor(app, name),
                              help=c.label or ""))
        items.append(Item("submenu", "✚ 新建连接", submenu=_new_connection_menu(app)))
        return "Provider 连接", items
    return build


def _model_section_items(app) -> list[Item]:
    return [
        Item("submenu", "角色绑定",
             get=lambda: f"orchestrator={_settings().roles.get('orchestrator', '?')}",
             submenu=_roles_menu(app), help="每个 agent 角色用哪张模型卡"),
        Item("submenu", "模型卡",
             get=lambda: f"{len(_settings().profiles)} 张",
             submenu=_profiles_menu(app), help="model id / 采样 / 思考开关，可新建自定义卡"),
        Item("submenu", "Provider 连接",
             get=lambda: f"{len(_store().models.provider_connections)} 个",
             submenu=_connections_menu(app), help="协议 / endpoint / API key（多 key 支持）"),
    ]


# --------------------------------------------------------------------------
# Search / Browse / Budget / Experimental / Runtime 区
# --------------------------------------------------------------------------

def _set_search_backend(app, v: str) -> str | None:
    from searchos.tools.simple_browser.search import SEARCH_PROVIDER_INFO
    name = None if v == "auto" else v
    if name in ("serper", "tavily"):
        env = SEARCH_PROVIDER_INFO[name]["api_key_env"]
        fallback = getattr(_settings(), f"{name}_api_key", "")
        if not _key_set(env, fallback):
            return f"{env} 未设置——先在下方填 key 再切换"
    _store().models.search_provider = name
    _sync()
    if not getattr(app, "_no_search", False):
        try:
            from searchos.tools.simple_browser.search import build_search_provider
            from searchos.tools.simple_browser.state import set_browser_provider
            set_browser_provider(build_search_provider(name or ""))
        except Exception as e:  # noqa: BLE001 — surface a bad key/backend inline
            return f"⚠ 已写入配置，但重建 provider 失败：{e}"
    return None


def _search_section_items(app) -> list[Item]:
    from searchos.tools.simple_browser.search import resolve_search_provider_name

    def _get_backend():
        return _store().models.search_provider or "auto"

    def _get_results():
        return _settings().search_max_results

    def _set_results(v):
        if v is None:
            _store().run_defaults.search_max_results = None
            _sync(reload=True)
            return None
        if v < 1:
            return "需要 ≥1 的整数"
        _store().run_defaults.search_max_results = v
        _sync()
        return None

    def _get_proxy():
        adv = _store().advanced
        if adv.https_proxy is not None:
            return adv.https_proxy or "（强制无代理）"
        return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""

    def _set_proxy(v):
        _store().advanced.https_proxy = v  # "" = 强制无代理（清空 env 变量）
        _sync()
        return None

    def _resolved():
        try:
            return resolve_search_provider_name(_store().models.search_provider or "")
        except ValueError:
            return "?"

    return [
        Item("choice", "搜索后端",
             get=_get_backend,
             set=lambda v: _set_search_backend(app, v),
             choices=lambda: ["auto", "serper", "tavily", "ragflow"],
             help=lambda: f"auto = 按已有 key 推断（当前生效：{_resolved()}）"),
        _secret_item("Serper key", "SERPER_API_KEY"),
        _secret_item("Tavily key", "TAVILY_API_KEY"),
        Item("int", "每查询结果数",
             get=_get_results, set=_set_results,
             help="每次搜索取多少条结果（留空=恢复默认）"),
        Item("text", "代理 (HTTP/HTTPS)",
             get=_get_proxy, set=_set_proxy,
             help="导出到 HTTP_PROXY/HTTPS_PROXY；留空提交=强制无代理",
             placeholder="http://127.0.0.1:7890"),
    ]


def _browse_section_items(app) -> list[Item]:
    def _set_backend(v):
        _store().models.browser_backend = v
        _sync()
        return None

    def _set_cache(v):
        _store().advanced.browser_disk_cache_dir = v or None
        _sync(reload=not v)
        return None

    def _jina_set():
        return (_key_set("JINA_API_KEY")
                or _key_set("SF_JINA_API_KEY", _settings().jina_api_key))

    return [
        Item("choice", "浏览后端",
             get=lambda: _settings().browser_backend, set=_set_backend,
             choices=lambda: list(_BROWSER_BACKENDS),
             help="jina = Reader API 渲染；aiohttp = 直接抓取"),
        Item("secret", "Jina key",
             get=_jina_set, set=lambda v: _set_key("SF_JINA_API_KEY", v),
             help="值写入 .env 的 SF_JINA_API_KEY（留空=清除）",
             placeholder="SF_JINA_API_KEY"),
        Item("text", "页面缓存目录",
             get=lambda: _settings().browser_disk_cache_dir, set=_set_cache,
             help="浏览页面的磁盘缓存位置（留空=恢复默认）"),
    ]


def _budget_section_items(app) -> list[Item]:
    from searchos.config.effort import EFFORT_LEVELS

    def _set_effort(v):
        apply = getattr(app, "_apply_effort", None)
        if apply is not None:
            apply(v)  # app 侧负责写 overlay + 应用 + 清空逐 knob 覆盖
        return None

    def _get_maxtime():
        rd = _store().run_defaults
        return rd.max_time_s if rd.max_time_s is not None else _settings().default_max_time_s

    def _set_maxtime(v):
        if v is not None and v < 1:
            return "需要 ≥1 的整数（秒）"
        _store().run_defaults.max_time_s = v
        _sync()
        return None

    def _set_retries(v):
        if v is None:
            _store().advanced.llm_max_retries = None
            _sync(reload=True)
            return None
        if not (0 <= v <= 20):
            return "范围 0–20"
        _store().advanced.llm_max_retries = v
        _sync()
        return None

    return [
        Item("choice", "effort 档位",
             get=lambda: _store().effort.level or "medium", set=_set_effort,
             choices=lambda: list(EFFORT_LEVELS),
             help="并发/迭代/搜索数/墙钟整组切换；切档会清空逐 knob 覆盖"),
        Item("int", "墙钟上限 (s)",
             get=_get_maxtime, set=_set_maxtime,
             help="单轮最长运行秒数（留空=跟随 effort 档位）"),
        Item("int", "LLM 重试",
             get=lambda: _settings().llm_max_retries, set=_set_retries,
             help="每次 LLM 调用的最大重试次数 0–20（留空=恢复默认）"),
    ]


def _experimental_section_items(app) -> list[Item]:
    def _set_coverage_stall_rounds(v):
        if v is None:
            _store().advanced.orch_coverage_stall_rounds = None
            _sync(reload=True)
            return None
        if not (0 <= v <= 100):
            return "范围 0–100"
        _store().advanced.orch_coverage_stall_rounds = v
        _sync()
        return None

    return [
        Item("int", "Coverage 停滞轮数",
             get=lambda: _settings().orch_coverage_stall_rounds,
             set=_set_coverage_stall_rounds,
             help="连续多少个搜索代理返回批次无新增行/填充值后结束；0=关闭，留空=恢复默认"),
    ]


def _runtime_section_items(app) -> list[Item]:
    def _set_skills(v):
        _store().run_defaults.enable_skills = bool(v)
        _sync()
        return None

    return [
        Item("bool", "技能系统",
             get=lambda: _settings().enable_skills, set=_set_skills,
             help="总开关；具体技能勾选用 /skill"),
    ]


# --------------------------------------------------------------------------
# Root menus
# --------------------------------------------------------------------------

def build_root_menu(app) -> MenuBuilder:
    def build():
        items: list[Item] = [Item("header", "Model 模型")]
        items += _model_section_items(app)
        items.append(Item("header", "Search 搜索"))
        items += _search_section_items(app)
        items.append(Item("header", "Browse 浏览"))
        items += _browse_section_items(app)
        items.append(Item("header", "Budget 预算"))
        items += _budget_section_items(app)
        items.append(Item("header", "Experimental 实验"))
        items += _experimental_section_items(app)
        items.append(Item("header", "Runtime 运行"))
        items += _runtime_section_items(app)
        return "设置", items
    return build


def build_model_menu(app) -> MenuBuilder:
    def build():
        return "模型设置", _model_section_items(app)
    return build


# --------------------------------------------------------------------------
# The modal
# --------------------------------------------------------------------------

_LABEL_WIDTH = 26


class ConfigModal(ModalScreen):
    """Claude-Code-style settings panel: one scrollable list per level, an
    internal menu stack for submenus. Every edit persists immediately;
    ``dismiss`` returns the number of applied changes."""

    DEFAULT_CSS = """
    ConfigModal { align: center middle; }
    #cfg-box {
        width: 84; height: 80%; padding: 1 2;
        background: $surface; border: round #22d3ee;
    }
    #cfg-title { text-style: bold; color: #22d3ee; padding-bottom: 1; }
    #cfg-list  { height: 1fr; background: $surface; }
    #cfg-edit  { height: 1; border: none; padding: 0; margin-top: 1;
                 background: $boost; display: none; }
    #cfg-msg   { height: auto; min-height: 1; padding-top: 1; color: #6e7681; }
    #cfg-hint  { color: #6e7681; }
    """

    BINDINGS = [
        ("escape", "back", "返回"),
        ("left", "cycle_prev", ""),
        ("right", "cycle_next", ""),
        ("space", "activate", ""),
    ]

    def __init__(self, root: MenuBuilder) -> None:
        super().__init__()
        self._stack: list[MenuBuilder] = [root]
        self._titles: list[str] = [""]
        self._items: list[Item] = []
        self._editing: Item | None = None
        self._pending: Item | None = None  # confirm-armed action
        self._changes = 0

    # ----- layout -----

    def compose(self) -> ComposeResult:
        with Vertical(id="cfg-box"):
            yield Static("", id="cfg-title")
            yield OptionList(id="cfg-list")
            yield Input(id="cfg-edit")
            yield Static("", id="cfg-msg")
            yield Static("", id="cfg-hint")

    def on_mount(self) -> None:
        self._rebuild()
        self.query_one("#cfg-list", OptionList).focus()

    # ----- rendering -----

    @staticmethod
    def _fmt_value(item: Item) -> Text:
        val = item.get() if item.get else None
        if item.kind == "bool":
            return (Text("✓ on", style=C_AGENTS) if val
                    else Text("○ off", style=FAINT))
        if item.kind == "secret":
            return (Text("● 已设置", style=C_AGENTS) if val
                    else Text("○ 未设置", style=FAINT))
        if item.kind in ("choice", "text", "int", "float", "submenu"):
            if val is None or val == "":
                return Text("（未设置）", style=FAINT)
            return Text(str(val), style=ACCENT)
        return Text("")

    def _row(self, item: Item) -> Text:
        if item.kind == "header":
            return Text(f"── {item.label} ", style=f"bold {ACCENT}")
        t = Text("  ")
        prefix = "▸ " if item.kind == "submenu" else "  "
        reason = item.disabled() if item.disabled else ""
        label_style = FAINT if reason else (
            ACCENT if item.kind == "action" else "")
        t.append(prefix, style=ACCENT if item.kind == "submenu" else "")
        t.append(item.label, style=label_style)
        pad = max(1, _LABEL_WIDTH - cell_len(item.label))
        t.append(" " * pad)
        if reason:
            t.append(f"✗ {reason}", style=FAINT)
        else:
            t.append_text(self._fmt_value(item))
        return t

    def _rebuild(self, keep_highlight: bool = True) -> None:
        title, items = self._stack[-1]()
        self._titles[-1] = title
        self._items = items
        ol = self.query_one("#cfg-list", OptionList)
        prev = ol.highlighted if keep_highlight else None
        ol.clear_options()
        ol.add_options([
            Option(self._row(it), id=str(i),
                   disabled=(it.kind == "header"
                             or bool(it.disabled and it.disabled())))
            for i, it in enumerate(items)
        ])
        if items:
            if prev is not None:
                ol.highlighted = min(prev, len(items) - 1)
            else:
                # First selectable row (skip the leading section header).
                ol.highlighted = next(
                    (i for i, it in enumerate(items) if it.kind != "header"), 0)
        self.query_one("#cfg-title", Static).update(
            "⚙ " + " › ".join(t for t in self._titles if t))
        self._show_help()
        self._update_hint()

    def _highlighted_item(self) -> Item | None:
        ol = self.query_one("#cfg-list", OptionList)
        idx = ol.highlighted
        if idx is None or not self._items:
            return None
        opt = ol.get_option_at_index(idx)
        return self._items[int(opt.id)] if opt.id is not None else None

    def _show_help(self, message: str = "", style: str = "") -> None:
        msg = self.query_one("#cfg-msg", Static)
        if message:
            msg.update(Text(message, style=style or MUTED))
            return
        item = self._highlighted_item()
        text = ""
        if item is not None:
            h = item.help
            text = h() if callable(h) else h
        msg.update(Text(text or "", style=MUTED))

    def _update_hint(self) -> None:
        if self._editing is not None:
            hint = "回车 保存 · Esc 取消 · 留空提交=清除/恢复默认"
        else:
            back = "返回上级" if len(self._stack) > 1 else "关闭"
            hint = f"↑↓ 选择 · 回车 编辑/切换/进入 · ←→ 切换值 · Esc {back}"
        self.query_one("#cfg-hint", Static).update(Text(hint, style=FAINT))

    # ----- interaction -----

    def on_option_list_option_highlighted(
            self, event: OptionList.OptionHighlighted) -> None:
        self._pending = None
        self._show_help()

    def on_option_list_option_selected(
            self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if event.option.id is not None:
            self._activate(self._items[int(event.option.id)])

    def action_activate(self) -> None:
        ol = self.query_one("#cfg-list", OptionList)
        if not ol.has_focus:
            return
        item = self._highlighted_item()
        if item is not None:
            self._activate(item)

    def _activate(self, item: Item) -> None:
        if item.disabled and item.disabled():
            self._show_help(f"✗ {item.disabled()}", WARN)
            return
        if item.kind == "submenu" and item.submenu is not None:
            self._stack.append(item.submenu)
            self._titles.append("")
            self._pending = None
            self._rebuild(keep_highlight=False)
            return
        if item.kind == "bool":
            self._apply(item, not item.get())
            return
        if item.kind == "choice":
            self._cycle(item, +1)
            return
        if item.kind in ("text", "int", "float", "secret"):
            self._open_editor(item)
            return
        if item.kind == "action":
            if item.confirm and self._pending is not item:
                self._pending = item
                self._show_help(f"⚠ 再按一次回车确认：{item.confirm}", WARN)
                return
            self._pending = None
            self._apply(item, None, pop_after=item.pop_after)

    def _cycle(self, item: Item, delta: int) -> None:
        if item.choices is None:
            return
        vals = item.choices()
        if not vals:
            return
        cur = item.get() if item.get else None
        try:
            idx = vals.index(cur)
        except ValueError:
            idx = 0 if delta > 0 else -1
            self._apply(item, vals[idx])
            return
        self._apply(item, vals[(idx + delta) % len(vals)])

    def action_cycle_next(self) -> None:
        self._cycle_focused(+1)

    def action_cycle_prev(self) -> None:
        self._cycle_focused(-1)

    def _cycle_focused(self, delta: int) -> None:
        ol = self.query_one("#cfg-list", OptionList)
        if not ol.has_focus:
            return
        item = self._highlighted_item()
        if item is not None and item.kind == "choice" \
                and not (item.disabled and item.disabled()):
            self._cycle(item, delta)

    def _apply(self, item: Item, value, pop_after: bool = False) -> bool:
        if item.set is None:
            return False
        err = item.set(value)
        if err and not err.startswith("⚠"):
            self._show_help(f"✗ {err}", DANGER)
            return False
        if item.counts:
            self._changes += 1
        if pop_after and len(self._stack) > 1:
            self._stack.pop()
            self._titles.pop()
            self._rebuild(keep_highlight=False)
        else:
            self._rebuild()
        if err:  # applied with warning
            self._show_help(err, WARN)
        return True

    # ----- inline editor -----

    def _open_editor(self, item: Item) -> None:
        self._editing = item
        inp = self.query_one("#cfg-edit", Input)
        inp.password = item.kind == "secret"
        cur = item.get() if item.get and item.kind != "secret" else None
        inp.value = "" if cur is None else str(cur)
        inp.placeholder = item.placeholder or item.label
        inp.styles.display = "block"
        inp.focus()
        self._update_hint()
        self._show_help()

    def _close_editor(self) -> None:
        self._editing = None
        inp = self.query_one("#cfg-edit", Input)
        inp.value = ""
        inp.styles.display = "none"
        self.query_one("#cfg-list", OptionList).focus()
        self._update_hint()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()  # keep the App's slash-command colouring out of this box

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        item = self._editing
        if item is None:
            return
        raw = event.value.strip()
        value: Any = raw
        if item.kind == "int":
            if raw == "":
                value = None
            else:
                try:
                    value = int(raw)
                except ValueError:
                    self._show_help("✗ 需要整数", DANGER)
                    return
        elif item.kind == "float":
            if raw == "":
                value = None
            else:
                try:
                    value = float(raw)
                except ValueError:
                    self._show_help("✗ 需要数字", DANGER)
                    return
        if self._apply(item, value, pop_after=item.pop_after):
            self._close_editor()

    # ----- navigation -----

    def action_back(self) -> None:
        if self._editing is not None:
            self._close_editor()
            self._show_help()
            return
        if len(self._stack) > 1:
            self._stack.pop()
            self._titles.pop()
            self._pending = None
            self._rebuild(keep_highlight=False)
            return
        self.dismiss(self._changes)
