"""SearchOS CLI — minimal single-query entry point.

``python -m searchos "<query>"`` runs one search session and prints the
synthesized report. The full interactive prompt_toolkit TUI is a later phase;
this is the minimal runnable entry so the package can be driven from the shell.
"""

from __future__ import annotations

import argparse
import asyncio
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
    # 后端由 SF_SEARCH_PROVIDER 指定；未指定时按已有 key 推断（serper → tavily），
    # 都没有则回落内部 ragflow（向后兼容）。
    from searchos.tools.simple_browser.search import build_search_provider
    from searchos.tools.simple_browser.state import set_browser_provider
    set_browser_provider(build_search_provider())


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="searchos",
        description="SearchOS — the agentic search collaboration system",
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


def main() -> None:
    _load_env()
    args = _build_parser().parse_args()
    # 首次运行（或 --setup）：settings 单例尚未 import，此刻拉起配置向导还来得及
    # 改环境变量；缺配置且非 TTY 时直接给出可操作的报错。
    from searchos.config.setup_wizard import ensure_model_config
    ensure_model_config(force=args.setup)
    if args.setup and not args.query:
        return
    if args.query:
        sys.exit(asyncio.run(_run(args)))
    _launch_tui(args)


if __name__ == "__main__":
    main()
