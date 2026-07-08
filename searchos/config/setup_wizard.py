"""首次运行交互式配置向导 — 命令行引导选厂商、填 key，写入 .env。

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

from searchos.config.env_file import apply_env_updates, find_env_path, update_env_file
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


def model_config_ready() -> bool:
    """当前环境变量是否足以构造模型（不 import settings，不发请求）。"""
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
    """交互式配置。写 .env 并同步 os.environ；成功返回 True。"""
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    env_path = env_path or find_env_path()

    console.print(
        "\n[bold cyan]✻ SearchOS 首次配置[/] [dim]— 选一个模型厂商即可跑通全部角色；"
        f"之后可随时编辑 {env_path} 或重跑 `searchos --setup`[/]\n"
    )

    name, preset = _choose_preset(console)
    updates: dict[str, str] = {"SF_PROVIDER": name}

    # --- API key ---
    if preset.api_key_fallback:
        console.print(f"[dim]{preset.label} 无需 API key（自动使用占位符）。[/]")
    else:
        if preset.notes:
            console.print(f"[yellow]注意：[/]{preset.notes}")
        if preset.doc_url:
            console.print(f"[dim]Key 获取 / 文档：{preset.doc_url}[/]")
        while True:
            key = Prompt.ask(f"请输入 {preset.api_key_env}", password=True).strip()
            if key:
                break
            console.print("[red]API key 不能为空。[/]")
        updates[preset.api_key_env] = key

    # --- 模型 ---
    if preset.main_model:
        model = Prompt.ask(
            "主力模型（回车用默认）", default=preset.main_model, show_default=True,
        ).strip()
        if model and model != preset.main_model:
            updates["SF_MODEL"] = model
    else:
        while True:
            model = Prompt.ask(
                "模型名（本地部署必填，如 qwen3:32b / Qwen/Qwen3-32B）"
            ).strip()
            if model:
                break
            console.print("[red]本地部署必须指定模型。[/]")
        updates["SF_MODEL"] = model

    # --- 端点（本地部署常改端口；其余厂商可切国际站）---
    api_base = Prompt.ask(
        "API 端点（回车用默认）", default=preset.api_base or "官方默认",
        show_default=True,
    ).strip()
    if api_base and api_base not in (preset.api_base, "官方默认"):
        updates["SF_API_BASE"] = api_base

    # --- 搜索后端 ---
    has_search_key = any(
        os.environ.get(env) for _, _, env in _SEARCH_BACKENDS if env
    )
    console.print("\n[bold]搜索后端[/]（Web 搜索 API，与模型厂商无关）：")
    for i, (sname, label, key_env) in enumerate(_SEARCH_BACKENDS, 1):
        suffix = f" [dim]· {key_env}[/]" if key_env else ""
        console.print(f"  [bold cyan]{i}[/] {sname} — {label}{suffix}")
    console.print("  [bold cyan]0[/] 跳过（稍后在 .env 里配置 SF_SEARCH_PROVIDER）")
    search_choice = Prompt.ask(
        "输入编号", choices=[str(i) for i in range(len(_SEARCH_BACKENDS) + 1)],
        default="0" if has_search_key else "1", show_choices=False,
    )
    if search_choice != "0":
        sname, _, key_env = _SEARCH_BACKENDS[int(search_choice) - 1]
        updates["SF_SEARCH_PROVIDER"] = sname
        if key_env and not os.environ.get(key_env):
            while True:
                skey = Prompt.ask(f"请输入 {key_env}", password=True).strip()
                if skey:
                    break
                console.print("[red]API key 不能为空。[/]")
            updates[key_env] = skey

    apply_env_updates(env_path, updates)

    shown = {k: ("***" if "KEY" in k or "TOKEN" in k else v) for k, v in updates.items()}
    console.print(f"\n[green]✓ 配置已写入 {env_path}[/]")
    for k, v in shown.items():
        console.print(f"  [dim]{k}={v}[/]")
    console.print(
        "[dim]更多预设与精细覆写（单角色换模型、限速等）见 docs/providers.md[/]\n"
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
