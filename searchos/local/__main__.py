"""Command-line entry point for processing one local document."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from searchos.local import messages


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
    from searchos.config.settings_overlay import load_and_apply

    load_and_apply()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=messages.CLI_DESCRIPTION)
    parser.add_argument(
        "source",
        nargs="?",
        help=messages.CLI_SOURCE,
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
        help=messages.CLI_REMOTE,
    )
    remote.add_argument(
        "--local-only",
        dest="allow_remote",
        action="store_false",
        help=messages.CLI_LOCAL_ONLY,
    )
    parser.set_defaults(allow_remote=True)
    parser.add_argument(
        "--no-catalog",
        dest="build_catalog",
        action="store_false",
        help=messages.CLI_NO_CATALOG,
    )
    parser.set_defaults(build_catalog=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help=messages.CLI_LIST_FORMATS,
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    from searchos.local.indexing import DocumentRecapPipeline, build_parser_registry
    from searchos.local.models import (
        PdfMode,
        PipelineOptions,
        PptxMode,
        ProcessingStatus,
    )

    if args.list_formats:
        for capability in build_parser_registry().capabilities():
            extensions = ", ".join(capability.extensions)
            locators = ", ".join(capability.locator_kinds)
            visual = messages.CLI_VISUAL if capability.visual else ""
            print(
                messages.CLI_FORMAT.format(
                    kind=capability.kind.value,
                    extensions=extensions,
                    locators=locators,
                    visual=visual,
                )
            )
        return 0
    if not args.source:
        raise SystemExit(messages.CLI_SOURCE_REQUIRED)

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
    cache_note = messages.CLI_CACHED if result.cached else ""
    print(messages.CLI_STATUS.format(status=result.status.value, cached=cache_note))
    print(messages.CLI_TEXT.format(path=result.text_path))
    print(messages.CLI_DOCUMENT.format(path=result.document_path))
    for path in result.catalog_paths:
        print(messages.CLI_CATALOG.format(path=path))
    for warning in result.warnings:
        print(messages.CLI_WARNING.format(warning=warning))
    return 1 if result.status == ProcessingStatus.FAILED else 0


def main() -> None:
    _load_env()
    args = _parser().parse_args()
    _configure_models(allow_remote=args.allow_remote)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
