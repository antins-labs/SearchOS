"""
Batch inference runner — run the search agent on a JSONL dataset with concurrency control.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field

from .agent import SearchAgent
from .config import AgentConfig

logger = logging.getLogger(__name__)

QUERY_FIELD_CANDIDATES = ["question", "query", "input", "prompt"]
ID_FIELD_CANDIDATES = ["instance_id", "id", "task_id", "question_id"]


def _detect_field(row: dict, candidates: list[str]) -> str | None:
    """Return the first candidate key that exists in the row."""
    for key in candidates:
        if key in row:
            return key
    return None


def _create_llm(config: AgentConfig):
    """Create an LLM instance (import here to avoid top-level heavy imports)."""
    if config.llm_provider == "claude":
        from .llm.claude_llm import ClaudeLLM
        return ClaudeLLM(model=config.model_name, api_key=config.api_key)
    else:
        from .llm.openai_llm import OpenAILLM
        return OpenAILLM(model=config.model_name, api_key=config.api_key)


@dataclass
class BatchStats:
    """Track batch progress."""
    total: int = 0
    completed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: float = field(default_factory=time.time)

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def rate(self) -> float:
        elapsed = self.elapsed()
        return self.completed / elapsed if elapsed > 0 else 0.0


class BatchRunner:
    """Run the search agent on a JSONL dataset with concurrency control."""

    def __init__(
        self,
        config: AgentConfig,
        concurrency: int = 5,
        query_field: str | None = None,
        id_field: str | None = None,
        save_messages: bool = False,
    ):
        self.config = config
        self.concurrency = concurrency
        self.query_field_override = query_field
        self.id_field_override = id_field
        self.save_messages = save_messages
        self._semaphore = asyncio.Semaphore(concurrency)
        self._write_lock = asyncio.Lock()
        self._stats = BatchStats()
        self._query_field: str = ""
        self._id_field: str | None = None

    async def run(
        self,
        input_path: str,
        output_path: str,
        limit: int | None = None,
        overwrite: bool = False,
    ) -> BatchStats:
        """Run batch inference.

        Args:
            input_path: Path to input JSONL file.
            output_path: Path to output JSONL file.
            limit: Only process the first N rows.
            overwrite: If True, ignore existing output and restart from scratch.

        Returns:
            BatchStats with final counts.
        """
        # Load dataset
        rows = self._load_dataset(input_path, limit)
        if not rows:
            self._log("No rows to process.")
            return self._stats

        # Detect fields from first row
        self._query_field = self._resolve_query_field(rows[0])
        self._id_field = self._resolve_id_field(rows[0])

        self._log(f"Dataset: {len(rows)} rows, query_field='{self._query_field}', "
                   f"id_field='{self._id_field or '(line_number)'}', concurrency={self.concurrency}")

        # Handle resume
        completed_ids: set[str] = set()
        if not overwrite and os.path.exists(output_path):
            completed_ids = self._load_completed_ids(output_path)
            if completed_ids:
                self._log(f"Resuming: {len(completed_ids)} already completed, skipping.")
        elif overwrite and os.path.exists(output_path):
            os.remove(output_path)

        # Filter pending rows
        pending = []
        for idx, row in enumerate(rows):
            row_id = self._get_row_id(row, idx)
            if row_id in completed_ids:
                continue
            pending.append((idx, row))

        self._stats = BatchStats(
            total=len(rows),
            skipped=len(rows) - len(pending),
            completed=len(rows) - len(pending),
        )

        if not pending:
            self._log("All rows already completed.")
            return self._stats

        self._log(f"Processing {len(pending)} pending rows...")

        # Launch concurrent tasks
        tasks = [
            self._process_one(idx, row, output_path)
            for idx, row in pending
        ]
        await asyncio.gather(*tasks)

        # Summary
        elapsed = self._stats.elapsed()
        self._log(
            f"\nDone: {self._stats.succeeded} succeeded, {self._stats.failed} failed, "
            f"{self._stats.skipped} skipped | {elapsed:.1f}s total ({self._stats.rate():.2f} rows/s)"
        )
        return self._stats

    async def _process_one(self, idx: int, row: dict, output_path: str):
        """Process a single row with semaphore-controlled concurrency."""
        row_id = self._get_row_id(row, idx)
        query = row.get(self._query_field, "")
        query_preview = query[:60] + "..." if len(query) > 60 else query

        async with self._semaphore:
            self._log_progress(f"Starting: [{row_id}] {query_preview}")

            llm = _create_llm(self.config)
            agent = SearchAgent(llm=llm, config=self.config)

            try:
                answer = await agent.run(query)
                is_error = False
            except Exception as e:
                logger.error("Error processing row %s: %s", row_id, e)
                answer = f"ERROR: {e}"
                is_error = True

            # Build result: original row + prediction + metadata
            result = {**row, "prediction": answer}
            if self.save_messages:
                from .agent import SYSTEM_PROMPT
                result["system_prompt"] = SYSTEM_PROMPT
                result["tools"] = agent.last_tools
                result["messages"] = agent.last_messages
            if self._id_field is None:
                result["_line_idx"] = idx

            # Append to output file
            async with self._write_lock:
                with open(output_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result, ensure_ascii=False) + "\n")

            # Update stats
            self._stats.completed += 1
            if is_error:
                self._stats.failed += 1
            else:
                self._stats.succeeded += 1

            status = "FAIL" if is_error else "OK"
            self._log_progress(
                f"[{self._stats.completed}/{self._stats.total}] "
                f"({100 * self._stats.completed / self._stats.total:.1f}%) "
                f"{status}: [{row_id}] {query_preview}"
            )

    # ---- Data loading ----

    def _load_dataset(self, path: str, limit: int | None = None) -> list[dict]:
        """Load JSONL file into a list of dicts."""
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if limit is not None and i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("Skipping malformed line %d: %s", i, e)
        return rows

    def _load_completed_ids(self, output_path: str) -> set[str]:
        """Load IDs of already-completed rows from the output file."""
        ids = set()
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        row_id = self._get_row_id(row, row.get("_line_idx", i))
                        ids.add(row_id)
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
        return ids

    # ---- Field resolution ----

    def _resolve_query_field(self, sample_row: dict) -> str:
        """Determine which field contains the query."""
        if self.query_field_override:
            if self.query_field_override not in sample_row:
                raise ValueError(
                    f"Specified query field '{self.query_field_override}' not found in data. "
                    f"Available fields: {list(sample_row.keys())}"
                )
            return self.query_field_override

        detected = _detect_field(sample_row, QUERY_FIELD_CANDIDATES)
        if detected is None:
            raise ValueError(
                f"Cannot auto-detect query field. Available fields: {list(sample_row.keys())}. "
                f"Use --query-field to specify explicitly."
            )
        return detected

    def _resolve_id_field(self, sample_row: dict) -> str | None:
        """Determine which field to use as unique ID (None = use line index)."""
        if self.id_field_override:
            if self.id_field_override not in sample_row:
                raise ValueError(
                    f"Specified ID field '{self.id_field_override}' not found in data. "
                    f"Available fields: {list(sample_row.keys())}"
                )
            return self.id_field_override
        return _detect_field(sample_row, ID_FIELD_CANDIDATES)

    def _get_row_id(self, row: dict, idx: int) -> str:
        """Get a unique identifier for a row."""
        if self._id_field and self._id_field in row:
            return str(row[self._id_field])
        return str(idx)

    # ---- Logging ----

    def _log(self, msg: str):
        """Print status to stderr."""
        print(msg, file=sys.stderr)

    def _log_progress(self, msg: str):
        """Print progress line to stderr."""
        print(f"  {msg}", file=sys.stderr)
