"""
CLI entry point for the simple search agent baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .agent import SearchAgent
from .config import AgentConfig


def create_llm(config: AgentConfig):
    """Create the appropriate LLM instance based on config."""
    if config.llm_provider == "claude":
        from .llm.claude_llm import ClaudeLLM
        return ClaudeLLM(model=config.model_name, api_key=config.api_key)
    else:
        from .llm.openai_llm import OpenAILLM
        return OpenAILLM(model=config.model_name, api_key=config.api_key)


async def async_main(query: str, config: AgentConfig, save_dir: str | None = None) -> str:
    """Run the search agent asynchronously."""
    llm = create_llm(config)
    agent = SearchAgent(llm=llm, config=config)
    answer = await agent.run(query)
    if save_dir:
        path = agent.save_result(save_dir)
        print(f"Result saved to: {path}", file=sys.stderr)
    return answer


async def async_batch(args, config: AgentConfig):
    """Run batch inference."""
    from .batch import BatchRunner

    runner = BatchRunner(
        config=config,
        concurrency=args.concurrency,
        query_field=args.query_field,
        id_field=args.id_field,
        save_messages=args.save_dir is not None,
    )

    # Default output path: input stem + _predictions.jsonl
    output_path = args.output
    if output_path is None:
        stem = args.input.rsplit(".", 1)[0]
        output_path = f"{stem}_predictions.jsonl"

    stats = await runner.run(
        input_path=args.input,
        output_path=output_path,
        limit=args.limit,
        overwrite=args.overwrite,
    )
    return stats


def _add_shared_args(parser: argparse.ArgumentParser):
    """Add arguments shared between query and batch subcommands."""
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        choices=["openai", "claude"],
        help="LLM provider to use",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: auto-select based on provider)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Maximum number of agent loop iterations",
    )
    parser.add_argument(
        "--view-tokens",
        type=int,
        default=2048,
        help="Token budget for page display window",
    )
    parser.add_argument(
        "--search-page-size",
        type=int,
        default=10,
        help="Number of search results to retrieve",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show intermediate reasoning and tool calls",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default=None,
        help="Directory to save agent results (answer + messages). If not set, results are not saved.",
    )


def main():
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Simple Search Agent Baseline - GPT-OSS style search/browse agent",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # ---- Subcommand: query (single query) ----
    query_parser = subparsers.add_parser(
        "query",
        help="Run a single search query",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    query_parser.add_argument("query", type=str, help="The search question to answer")
    _add_shared_args(query_parser)

    # ---- Subcommand: batch (dataset inference) ----
    batch_parser = subparsers.add_parser(
        "batch",
        help="Run batch inference on a JSONL dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    batch_parser.add_argument("input", type=str, help="Input JSONL file path")
    batch_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output JSONL path (default: <input>_predictions.jsonl)",
    )
    batch_parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=5,
        help="Number of concurrent agent tasks",
    )
    batch_parser.add_argument(
        "--query-field",
        type=str,
        default=None,
        help="Field name for the query (default: auto-detect 'question' or 'query')",
    )
    batch_parser.add_argument(
        "--id-field",
        type=str,
        default=None,
        help="Field name for unique row ID (default: auto-detect or use line number)",
    )
    batch_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N rows",
    )
    batch_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output (disable resume)",
    )
    _add_shared_args(batch_parser)

    # ---- Parse ----
    # Backward compatibility: if first arg isn't a subcommand, prepend "query"
    _SUBCOMMANDS = {"query", "batch"}
    argv = sys.argv[1:]
    if argv and argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["query"] + argv

    args = parser.parse_args(argv)

    # Configure logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    config = AgentConfig(
        llm_provider=args.provider,
        llm_model=args.model,
        max_iterations=args.max_iterations,
        view_tokens=args.view_tokens,
        search_page_size=args.search_page_size,
        verbose=args.verbose,
    )

    try:
        if args.command == "batch":
            asyncio.run(async_batch(args, config))
        else:
            answer = asyncio.run(async_main(args.query, config, save_dir=args.save_dir))
            if not args.verbose:
                print(answer)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
