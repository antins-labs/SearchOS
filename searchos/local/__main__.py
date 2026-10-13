"""Command-line entry point for processing one local document."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for parent in [Path.cwd(), *Path(__file__).resolve().parents]:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return


def _configure_models(*, allow_remote: bool) -> None:
    """Load the same user-owned model cards and role bindings as SearchOS."""
    if not allow_remote:
        return
    from searchos.config.setup_wizard import ensure_model_config

    ensure_model_config()
    from searchos.config.web_overlay import load_and_apply

    load_and_apply()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成本地文档的原文映射、解析表示与 Recap")
    parser.add_argument(
        "source",
        nargs="?",
        help="待处理的 Markdown、文本、PDF、Office、表格、JSON、HTML 或图片文件",
    )
    parser.add_argument("--output-root", default="local-index/default")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--document-id", default=None)
    parser.add_argument(
        "--pdf-mode",
        choices=("auto", "text_only", "vision_all"),
        default="auto",
    )
    parser.add_argument(
        "--pptx-mode",
        choices=("auto", "text_only", "vision_all"),
        default="auto",
    )
    remote = parser.add_mutually_exclusive_group()
    remote.add_argument(
        "--allow-remote",
        dest="allow_remote",
        action="store_true",
        help="启用远程模型（默认）",
    )
    remote.add_argument(
        "--local-only",
        dest="allow_remote",
        action="store_false",
        help="只解析正文，不调用远程模型",
    )
    parser.set_defaults(allow_remote=True)
    parser.add_argument(
        "--no-catalog",
        dest="build_catalog",
        action="store_false",
        help="不更新 INDEX.md 和 subindex",
    )
    parser.set_defaults(build_catalog=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="列出支持格式、定位类型和可选视觉能力后退出",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    from searchos.local.models import (
        PdfMode,
        PipelineOptions,
        PptxMode,
        ProcessingStatus,
    )
    from searchos.local.pipeline import DocumentRecapPipeline, build_parser_registry

    if args.list_formats:
        for capability in build_parser_registry().capabilities():
            extensions = ", ".join(capability.extensions)
            locators = ", ".join(capability.locator_kinds)
            visual = "；可选视觉" if capability.visual else ""
            print(f"{capability.kind.value}: {extensions}；位置 {locators}{visual}")
        return 0
    if not args.source:
        raise SystemExit("请提供 source，或使用 --list-formats")

    result = await DocumentRecapPipeline(output_root=args.output_root).process(
        args.source,
        source_root=args.source_root,
        document_id=args.document_id,
        options=PipelineOptions(
            pdf_mode=PdfMode(args.pdf_mode),
            pptx_mode=PptxMode(args.pptx_mode),
            allow_remote=args.allow_remote,
            build_catalog=args.build_catalog,
            force=args.force,
        ),
    )
    cache_note = "（缓存命中）" if result.cached else ""
    print(f"状态：{result.status.value}{cache_note}")
    print(f"正文：{result.text_path}")
    print(f"索引：{result.document_path}")
    for path in result.catalog_paths:
        print(f"目录：{path}")
    for warning in result.warnings:
        print(f"告警：{warning}")
    return 1 if result.status == ProcessingStatus.FAILED else 0


def main() -> None:
    _load_env()
    args = _parser().parse_args()
    _configure_models(allow_remote=args.allow_remote)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
