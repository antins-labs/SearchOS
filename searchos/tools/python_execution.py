"""Orchestrator 的 Python 工具；执行与表格编辑相互独立。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.tools import tool

from searchos.skills.runtime.command_runtime import run_command


@tool("python")
async def python(code: str, timeout_s: float = 30) -> str:
    """Run Python code and return stdout, stderr and exit status. Print the results.

    Each call runs independently in an offline sandbox with installed Python packages.
    Include input data in code; this tool does not read or edit tables. Files are temporary.
    timeout_s defaults to 30 seconds (maximum 300).
    """
    if not code.strip() or len(code.encode()) > 100_000:
        return json.dumps({"status": "blocked", "error": "code must contain 1–100000 bytes"})
    with TemporaryDirectory(prefix="searchos-python-") as directory:
        root = Path(directory)
        script = root / "script"
        script.mkdir()
        (script / "main.py").write_text(code)
        result = await run_command(script, ["python3", "main.py"], work_dir=root / "work",
                                   execution_dir=root / "logs", network=False, timeout_s=timeout_s)
    return json.dumps({key: result[key] for key in
                      ("status", "stdout", "stderr", "exit_code", "truncated", "error")
                      if key in result}, ensure_ascii=False)
