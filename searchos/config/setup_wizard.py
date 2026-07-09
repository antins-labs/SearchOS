"""首次运行交互式配置向导 — 命令行引导建 provider 连接、模型卡、角色绑定（写入
web_settings.json overlay，与 web 设置页 Models 区对等），key 值与搜索后端写入 .env。

必须在 ``searchos.config.settings`` 首次 import **之前**运行（settings 单例在
import 时从环境变量构造），因此本模块只依赖 stdlib + rich + providers.py。

触发逻辑（见 ``searchos/cli.py``）::

    配置可用？ ──是──> 直接运行
        │否
    stdin 是 TTY？ ──否──> 报错并指向 .env.example / docs/providers.md
        │是
    运行向导 → 写 .env + 更新 os.environ → 继续运行
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from searchos.config.env_file import (
    apply_env_updates,
    find_env_path,
    remove_env_keys,
    update_env_file,
)
from searchos.config.providers import PRESET_GROUPS, PRESETS, ProviderPreset, resolve_preset

# 搜索后端选项 — 与 searchos/tools/simple_browser/search/__init__.py 的
# SEARCH_PROVIDER_INFO 保持同步（不直接 import：那条链会提前构造 settings 单例）。
_SEARCH_BACKENDS: list[tuple[str, str, str]] = [
    # (SF_SEARCH_PROVIDER 值, 说明, key 环境变量；空 = 无需 key)
    ("serper", "Serper.dev（Google 结果，推荐；serper.dev 注册）", "SERPER_API_KEY"),
    ("tavily", "Tavily（tavily.com；需 pip install 'searchos[tavily]'）", "TAVILY_API_KEY"),
    ("ragflow", "RagFlow（蚂蚁内网接口，外部不可用）", "RAGFLOW_USER_ID"),
]

# 分组数据在 providers.PRESET_GROUPS；这里只保留向导表格的中文组名。
_GROUP_LABELS: dict[str, str] = {
    "coding_plan": "厂商 Coding Plan（Anthropic 协议订阅，性价比高）",
    "pay_as_you_go": "按量 API",
    "local": "本地部署",
}


def _overlay_config_ready() -> bool:
    """web_settings.json overlay 是否已配好可用模型：至少一个被角色绑定的 profile
    ——新建的 custom 卡，或对既有 profile 的 override（改绑 provider_ref，常见于
    "不新建卡，直接把老角色改连到新 provider" 的配置路径）——指向的 key 环境变量
    有值（不 import settings、不发请求）。"""
    from searchos.config.web_overlay import WebSettings, overlay_path

    path = overlay_path()
    if not path.exists():
        return False
    try:
        ov = WebSettings.model_validate_json(path.read_text())
    except Exception:
        return False
    conns = ov.models.provider_connections
    configured = set(ov.models.custom_profiles) | set(ov.models.profile_overrides)
    bound = {c for c in ov.models.roles.values() if c in configured}
    if not bound:
        return False
    for cname in bound:
        cp = ov.models.custom_profiles.get(cname)
        pov = ov.models.profile_overrides.get(cname)
        provider_ref = (cp and cp.provider_ref) or (pov and pov.provider_ref)
        api_key_env = (cp and cp.api_key_env) or (pov and pov.api_key_env)
        conn = conns.get(provider_ref) if provider_ref else None
        key_env = conn.resolve_key_env(api_key_env) if conn else api_key_env
        if not key_env or not os.environ.get(key_env):
            return False
    return True


def _env_config_ready() -> bool:
    """env/预设路径是否足以构造模型（不 import settings，不发请求）。"""
    provider = os.environ.get("SF_PROVIDER", "").strip()
    if not provider:
        # 未选预设 → 走 settings.py 内置网关默认值，主模型依赖 OPENAI_API_KEY。
        return bool(os.environ.get("OPENAI_API_KEY"))
    try:
        preset = resolve_preset(provider)
    except ValueError:
        return False
    if not (os.environ.get("SF_MODEL", "").strip() or preset.main_model):
        return False  # ollama/vllm 未指定模型
    key_env = os.environ.get("SF_API_KEY_ENV", "").strip() or preset.api_key_env
    return bool(os.environ.get(key_env) or preset.api_key_fallback)


def model_config_ready() -> bool:
    """配置是否足以构造模型：web overlay 配好，或 env/预设配好。"""
    return _overlay_config_ready() or _env_config_ready()


def _choose_preset(console) -> tuple[str, ProviderPreset]:
    from rich.prompt import Prompt
    from rich.table import Table

    table = Table(title="选择模型 Provider", show_lines=False, title_justify="left")
    table.add_column("#", justify="right", style="bold cyan")
    table.add_column("预设")
    table.add_column("说明")
    table.add_column("默认模型", style="dim")
    table.add_column("API Key 环境变量", style="dim")

    index: list[str] = []
    for group, names in PRESET_GROUPS:
        table.add_section()
        table.add_row("", f"[bold yellow]{_GROUP_LABELS.get(group, group)}[/]", "", "", "")
        for name in names:
            preset = PRESETS[name]
            index.append(name)
            table.add_row(
                str(len(index)), name, preset.label,
                preset.main_model or "（需手动指定）", preset.api_key_env,
            )
    console.print(table)

    choice = Prompt.ask(
        "输入编号", choices=[str(i) for i in range(1, len(index) + 1)],
        show_choices=False,
    )
    name = index[int(choice) - 1]
    return name, PRESETS[name]


def run_setup_wizard(env_path: Path | None = None) -> bool:
    """交互式配置，与 web 设置页 Models 区对等：建 provider 连接、模型卡、角色
    绑定写入 web_settings.json overlay；key 值与搜索后端写入 .env。成功返回 True。
    """
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    from searchos.config.profiles import ROLE_NAMES
    from searchos.config.web_overlay import (
        MIGRATABLE_ENV_KEYS,
        CustomProfile,
        ProviderConnection,
        load_overlay_file,
        migrate_legacy_env_into_overlay,
        overlay_path,
        save_overlay,
        store,
    )

    console = Console()
    env_path = env_path or find_env_path()
    load_overlay_file()  # 增量编辑已有 overlay，不覆盖别处配好的连接/卡

    console.print(
        "\n[bold cyan]✻ SearchOS 首次配置[/] [dim]— 建 provider 连接、模型卡、角色绑定；"
        "之后可在 web 设置页或重跑 `searchos --setup` 调整[/]\n"
    )

    env_updates: dict[str, str] = {}

    # ===== ① Provider 连接（协议 + 端点 + 一个或多个 API key）=====
    console.print("[bold]① Provider 连接[/]")
    tmpl_name, preset = _choose_preset(console)
    conn_name = (Prompt.ask("连接名（英数与 . _ -）", default=tmpl_name).strip() or tmpl_name)
    api_base = Prompt.ask(
        "API 端点（回车用默认）", default=preset.api_base or "官方默认", show_default=True,
    ).strip()
    api_base = "" if api_base in ("", "官方默认") else api_base

    key_envs: list[str] = []
    default_env = preset.api_key_env
    while True:
        kenv = Prompt.ask("API key 环境变量", default=default_env or "OPENAI_API_KEY").strip().upper()
        if kenv and kenv not in key_envs:
            key_envs.append(kenv)
        if preset.api_key_fallback:
            console.print(f"[dim]{preset.label} 无需 API key（自动占位）。[/]")
        else:
            if preset.doc_url and len(key_envs) == 1:
                console.print(f"[dim]Key 获取 / 文档：{preset.doc_url}[/]")
            kval = Prompt.ask(f"请输入 {kenv} 的值（回车跳过，稍后填）", password=True).strip()
            if kval:
                env_updates[kenv] = kval
        if not Confirm.ask("再加一个 key（同一 provider 多把）？", default=False):
            break
        default_env = ""
    if not key_envs:
        key_envs = [preset.api_key_env or "OPENAI_API_KEY"]

    store.models.provider_connections[conn_name] = ProviderConnection(
        protocol=preset.provider, api_base=api_base, api_key_envs=key_envs,
        thinking_style=preset.thinking_style, label=preset.label,
    )

    # ===== ② 模型卡（引用上面的连接，填 model id 与采样）=====
    console.print("\n[bold]② 模型卡[/]")
    cards: list[str] = []
    default_card, default_model = "main", preset.main_model
    while True:
        cname = (Prompt.ask("模型卡名", default=default_card).strip() or default_card)
        while True:
            model_id = (Prompt.ask(
                "模型 id" + ("" if default_model else "（本地部署必填，如 qwen3:32b）"),
                default=default_model or None,
            ) or "").strip()
            if model_id:
                break
            console.print("[red]模型 id 不能为空。[/]")
        traw = Prompt.ask(
            "temperature（空=省略该参数）", default="0.7" if preset.temperature_ok else "",
        ).strip()
        temp: float | None = None
        if traw:
            try:
                temp = float(traw)
            except ValueError:
                console.print("[yellow]temperature 非数字，按省略处理。[/]")
        thinking = False
        if preset.thinking_style != "none" and preset.provider != "anthropic":
            thinking = Confirm.ask("启用 thinking？", default=False)
        card_key = key_envs[0]
        if len(key_envs) > 1:
            card_key = Prompt.ask("使用哪个 key", choices=key_envs, default=key_envs[0])
        store.models.custom_profiles[cname] = CustomProfile(
            model=model_id, provider_ref=conn_name, api_key_env=card_key,
            temperature=temp, enable_thinking=thinking,
        )
        cards.append(cname)
        default_card, default_model = "fast", (preset.fast_model or "")
        if not Confirm.ask("再建一张模型卡？", default=False):
            break

    # ===== ③ 角色绑定 =====
    console.print("\n[bold]③ 角色绑定[/]")
    main_card = cards[0]
    if len(cards) == 1 or Confirm.ask(
        f"把全部 {len(ROLE_NAMES)} 个角色绑到 [cyan]{main_card}[/]？", default=True
    ):
        for role in ROLE_NAMES:
            store.models.roles[role] = main_card
    else:
        console.print(f"[dim]逐角色选择（回车用 {main_card}）：[/]")
        for role in ROLE_NAMES:
            store.models.roles[role] = Prompt.ask(f"  {role}", choices=cards, default=main_card)

    # ===== ④ 搜索后端（Web 搜索 API，与模型厂商无关）=====
    # 后端选择写入 overlay（models.search_provider，与 web 设置页一致，CLI/TUI
    # 也会读它）；只有 key 值这类 secret 才写 .env。
    has_search_key = any(os.environ.get(env) for _, _, env in _SEARCH_BACKENDS if env)
    console.print("\n[bold]④ 搜索后端[/]：")
    for i, (sname, label, key_env) in enumerate(_SEARCH_BACKENDS, 1):
        suffix = f" [dim]· {key_env}[/]" if key_env else ""
        console.print(f"  [bold cyan]{i}[/] {sname} — {label}{suffix}")
    console.print("  [bold cyan]0[/] 跳过（默认按已有 key 自动推断）")
    search_choice = Prompt.ask(
        "输入编号", choices=[str(i) for i in range(len(_SEARCH_BACKENDS) + 1)],
        default="0" if has_search_key else "1", show_choices=False,
    )
    if search_choice != "0":
        sname, _, key_env = _SEARCH_BACKENDS[int(search_choice) - 1]
        store.models.search_provider = sname
        if key_env and not os.environ.get(key_env):
            while True:
                skey = Prompt.ask(f"请输入 {key_env}", password=True).strip()
                if skey:
                    break
                console.print("[red]API key 不能为空。[/]")
            env_updates[key_env] = skey

    # ===== 写入 overlay + .env =====
    save_overlay()
    if env_updates:
        apply_env_updates(env_path, env_updates)

    console.print(f"\n[green]✓ 模型配置已写入 {overlay_path()}[/]")
    console.print(
        f"  [dim]连接 {conn_name}（{preset.provider}）· 模型卡 {', '.join(cards)} · "
        f"{len(ROLE_NAMES)} 个角色已绑定[/]"
    )
    if env_updates:
        console.print(f"  [dim].env 写入：{', '.join(env_updates)}[/]")

    # ===== 清理 .env 里已迁移到 overlay 的非密钥旧开关 =====
    # 先非破坏性地把遗留 env 并入 overlay，再提示删除 .env 里对应的旧行——
    # .env 从此回归纯密钥。只针对**文件里真实存在**的赋值行（环境里存在但不在
    # 文件里的没有可删项，也不打扰用户）。
    migrate_legacy_env_into_overlay()
    file_keys: set[str] = set()
    if env_path.exists():
        file_keys = {
            ln.split("=", 1)[0].strip()
            for ln in env_path.read_text().splitlines()
            if "=" in ln and not ln.strip().startswith("#")
        }
    present = [k for k in MIGRATABLE_ENV_KEYS if k in file_keys]
    if present:
        console.print(
            f"\n[yellow]检测到 .env 里有已迁移到设置文件的旧配置：{', '.join(present)}[/]"
        )
        if Confirm.ask("从 .env 移除它们（值已进 overlay，.env 只留密钥）？", default=True):
            removed = remove_env_keys(env_path, present)
            if removed:
                console.print(f"  [dim]已从 .env 移除：{', '.join(removed)}[/]")

    console.print(
        "[dim]更精细的调整（单角色换卡、限速、多 key 选用）见 web 设置页 → Models，"
        "或在 TUI 里用 /config、/search[/]\n"
    )
    return True


def ensure_model_config(force: bool = False) -> None:
    """CLI 启动检查：配置缺失时在 TTY 里拉起向导，否则给出可操作的报错。

    ``force=True``（``searchos --setup``）无条件运行向导——用户显式要求，
    不做 TTY 检查（rich 的 Prompt 也能消费管道输入）。
    """
    if force:
        run_setup_wizard()
        return
    if model_config_ready():
        return
    if sys.stdin.isatty() and sys.stdout.isatty():
        run_setup_wizard()
        return
    raise SystemExit(
        "未检测到可用的模型配置（非交互环境，无法启动配置向导）。\n"
        "请复制 .env.example 为 .env 并设置 SF_PROVIDER + 对应 API key，"
        "或参考 docs/providers.md。"
    )


__all__ = [
    "ensure_model_config",
    "model_config_ready",
    "run_setup_wizard",
    "update_env_file",
]
