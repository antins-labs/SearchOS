"""SearchOS CLI：默认启动交互式 TUI，也支持单次查询输出报告。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _load_env() -> None:
    # Settings are constructed from env vars at import time, so .env must be
    # loaded before the first searchos import.
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    for parent in [Path.cwd(), *Path(__file__).resolve().parents]:
        env = parent / ".env"
        if env.exists():
            load_dotenv(env)
            return


def _setup_provider(no_search: bool) -> None:
    if no_search:
        return
    # searchos binds search + page-fetch onto one shared provider.
    # 后端优先取 web_settings.json overlay 的 models.search_provider（与 web 一致，
    # main() 已在此前 load_and_apply）；overlay 未配时回落 SF_SEARCH_PROVIDER，
    # 再按已有 key 推断（serper → tavily），最后回落内部 ragflow。
    from searchos.config.web_overlay import store
    from searchos.tools.simple_browser.search import build_search_provider
    from searchos.tools.simple_browser.state import set_browser_provider
    set_browser_provider(build_search_provider(store.models.search_provider or ""))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="searchos",
        description="SearchOS — the agentic search collaboration system",
        epilog="通用技能管理：searchos skills {validate,install,export} --help",
    )
    p.add_argument("query", nargs="?", default=None,
                   help="Research query for one-shot mode; omit to launch the interactive TUI")
    p.add_argument("--workspace", default=None, help="Harness workspace root")
    p.add_argument("--no-search", action="store_true",
                   help="Skip provider setup (offline/debug)")
    p.add_argument("--setup", action="store_true",
                   help="运行交互式模型配置向导（选厂商、填 key，写入 .env）")
    return p


async def _run(args: argparse.Namespace) -> int:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    from searchos.config.settings import settings
    from searchos.harness.session import (
        SearchSession,
        close_browser_service,
        wait_for_all_evolutions,
    )

    console = Console()
    _setup_provider(args.no_search)

    harness = SearchSession(
        workspace_root=args.workspace or settings.workspace_root,
        skill_library_path=settings.skill_library_path,
    )

    console.print("\n[bold cyan]✻ SearchOS[/] [dim]— the agentic search collaboration system[/]")
    console.print(f"Query: {args.query}\n")

    try:
        result = await harness.run(args.query)
    finally:
        # Drain background skill generation and close the browser before exit.
        await wait_for_all_evolutions(timeout=None)
        await close_browser_service()

    report = Path(result.workspace_path) / "output" / "report.md"
    answer = report.read_text() if report.exists() else ""
    console.print()
    if answer:
        console.print(Panel(Markdown(answer), title="[bold blue]Answer",
                            border_style="blue"))
    else:
        console.print(Panel("[yellow]未生成答案（证据不足）。[/]",
                            title="[bold blue]Answer", border_style="yellow"))

    verdict_color = "green" if result.eval_verdict in ("PASS", "COMPLETE") else "yellow"
    tokens = result.token_usage.get("total_tokens", 0)
    calls = result.token_usage.get("llm_calls", 0)
    token_text = f" · {tokens:,} tok/{calls} calls" if tokens else ""
    console.print(
        f"[dim]覆盖 {result.coverage_score:.0%} · 证据 {result.evidence_count} · "
        f"步数 {result.total_steps} · {result.elapsed_s:.1f}s · [/]"
        f"[{verdict_color}]{result.eval_verdict}[/][dim]{token_text}[/]"
    )
    if report.exists():
        console.print(f"[dim]报告 {report}[/]")
    return 0


def _launch_tui(args: argparse.Namespace) -> None:
    from searchos.config.settings import settings
    from searchos.harness.session import SearchSession
    from searchos.tui import run_tui

    _setup_provider(args.no_search)

    def factory():
        return SearchSession(
            workspace_root=args.workspace or settings.workspace_root,
            skill_library_path=settings.skill_library_path,
        )

    run_tui(factory, no_search=args.no_search)


def _skills_command(argv: list[str]) -> int:
    """Manage local packages without loading model or search configuration."""
    from searchos.skills.packaging import export_package, install_package, validate_package

    parser = argparse.ArgumentParser(prog="searchos skills", description="校验、安装或导出通用技能包")
    commands = parser.add_subparsers(dest="operation", required=True)
    validate = commands.add_parser("validate", help="校验本地标准技能包")
    validate.add_argument("source", type=Path, help="含 SKILL.md 的技能目录")
    install = commands.add_parser("install", help="安装到指定技能库，不覆盖现有包")
    install.add_argument("source", type=Path)
    install.add_argument("--library", type=Path, required=True, help="目标技能库目录")
    export = commands.add_parser("export", help="导出独立技能包，不覆盖现有包")
    export.add_argument("source", type=Path)
    export.add_argument("--output", type=Path, required=True, help="目标包目录，末级目录名须与技能名一致")
    args = parser.parse_args(argv)
    try:
        skill = validate_package(args.source)
        result = {"name": skill.meta.name, "package_format": skill.package_format,
                  "package_hash": skill.package_hash, "resources": skill.resources}
        if args.operation == "install":
            # Normalize parent aliases such as macOS /tmp, retaining the final
            # destination component for the package API's no-overwrite checks.
            result["path"] = str(install_package(args.source, args.library.resolve()))
        elif args.operation == "export":
            output = args.output.parent.resolve() / args.output.name
            result["path"] = str(export_package(args.source, output))
        else:
            result["path"] = str(args.source.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"技能包操作失败：{exc}", file=sys.stderr)
        return 1


def main() -> None:
    if sys.argv[1:2] == ["skills"]:
        sys.exit(_skills_command(sys.argv[2:]))
    _load_env()
    args = _build_parser().parse_args()
    # 首次运行（或 --setup）：settings 单例尚未 import，此刻拉起配置向导还来得及
    # 改环境变量；缺配置且非 TTY 时直接给出可操作的报错。
    from searchos.config.setup_wizard import ensure_model_config
    ensure_model_config(force=args.setup)
    if args.setup and not args.query:
        return
    # Apply the web Settings-page overlay (provider connections, model cards,
    # role bindings) onto the settings singleton so the CLI/TUI shares one
    # config with the web app. No-op when web_settings.json is absent.
    from searchos.config.web_overlay import load_and_apply
    load_and_apply()
    if args.query:
        sys.exit(asyncio.run(_run(args)))
    _launch_tui(args)


if __name__ == "__main__":
    main()
