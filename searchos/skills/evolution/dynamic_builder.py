"""LLM-assisted builder for dynamic access skills.

This module is used when the normal static-page baker cannot see useful
content, usually because the site is a JavaScript app. The builder gives an
LLM three small tools:

* run Python probes from a scratch skill directory
* write files inside that skill directory
* read files inside that skill directory

The LLM is responsible for discovering the site's HTTP API and writing the
standard access-skill files: ``executor.py``, ``manifest.yaml``, and
``skill.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "GLM-5"
MAX_TURNS = 25

SYSTEM_PROMPT = """\
You build SearchOS access skills for dynamic websites.

Goal:
- Discover the site's real HTTP API.
- Prefer direct aiohttp/httpx calls over browser automation in the final skill.
- Write a complete access skill in the workspace: executor.py, manifest.yaml, skill.md.
- Verify the generated executor by importing and calling its execute() function.

Tools:
- run_python: run probe or verification code from the skill directory.
- write_file: write a file under the skill directory.
- read_file: inspect a file under the skill directory.

Recommended workflow:
1. Use Playwright in run_python to open the probe URLs and log XHR/fetch
   requests, response bodies, request payloads, and headers.
2. Identify API endpoints, required cookies, session-init calls, and custom
   headers that control JSON/binary response modes.
3. Reproduce the API with aiohttp/httpx.
4. Generate executor.py, manifest.yaml, and skill.md.
5. Test every public function through execute().

Final executor contract:
- expose async execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]
  ``ctx`` is a SearchOS SkillContext (fields: query, skill_dir, browser,
  judge_model). It is NOT a Playwright object — never call ctx.new_page() /
  ctx.goto(), and never pass ctx into a helper typed as a Playwright
  BrowserContext. If the skill needs Playwright, launch and manage your OWN
  browser/context inside the executor (and close it before returning).
- dispatch on params["function"] (always present — see manifest below)
- return structured dicts with explicit error fields instead of raising for
  normal user/input/API errors

manifest.yaml contract — write EXACTLY these two top-level keys, nothing else
(no name/invocation/host/functions/examples/notes):

    description: >-
      One line: what this skill fetches and from which site.
    params_schema:
      function:                      # REQUIRED dispatcher param
        type: string
        required: true
        description: |
          要调用的功能名。可用值:
            - <fn_a>   <what it does; which other params it needs>
            - <fn_b>   ...
      <param>:                        # one entry per argument execute() reads
        type: string|integer|number|boolean|array|object
        required: true|false
        description: <one line; note which function uses it>
        # default: <optional>

Rules: params_schema is a FLAT dict keyed by parameter name (never a list,
never nested under functions). Every argument execute() reads must appear,
including ``function``. skill.md is free-form human docs — no frontmatter.
"""


def _skill_dir_name(host: str) -> str:
    return host.replace(".", "_").replace("-", "_")


def _user_prompt(host: str, probe_urls: list[str], notes: str = "") -> str:
    urls = "\n".join(f"- {url}" for url in probe_urls)
    message = f"""Build a SearchOS access skill for:

Host: {host}
Probe URLs:
{urls}
"""
    if notes:
        message += f"\nNotes:\n{notes}\n"
    return message


class BuilderWorkspace:
    """Filesystem and subprocess tools exposed to the builder agent."""

    # OpenAI Chat Completions tool format (the builder runs against any
    # OpenAI-compatible endpoint).
    TOOL_DEFINITIONS = [
        {
            "type": "function",
            "function": {
                "name": "run_python",
                "description": (
                    "Run Python code from the skill output directory. Use this "
                    "for Playwright probes, HTTP API tests, and executor "
                    "verification."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "timeout": {"type": "number", "default": 120},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Write a UTF-8 text file under the skill directory. Use "
                    "paths like executor.py, manifest.yaml, or skill.md."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a UTF-8 text file under the skill directory.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
    ]

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run_python(self, code: str, timeout: float = 120.0) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            script_path = Path(f.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.output_dir),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=max(1.0, float(timeout or 120.0)),
            )
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:8000],
                "stderr": stderr.decode("utf-8", errors="replace")[:4000],
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"execution timed out after {timeout}s",
            }
        finally:
            script_path.unlink(missing_ok=True)

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        target = self._resolve_inside(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": str(target), "size": len(content)}

    async def read_file(self, path: str) -> dict[str, Any]:
        target = self._resolve_inside(path)
        if not target.exists():
            return {"error": f"file not found: {path}"}
        return {"content": target.read_text(encoding="utf-8")}

    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name == "run_python":
            return await self.run_python(
                str(tool_input["code"]),
                timeout=float(tool_input.get("timeout") or 120.0),
            )
        if tool_name == "write_file":
            return await self.write_file(str(tool_input["path"]), str(tool_input["content"]))
        if tool_name == "read_file":
            return await self.read_file(str(tool_input["path"]))
        return {"error": f"unknown tool: {tool_name}"}

    def _resolve_inside(self, path: str) -> Path:
        target = (self.output_dir / path).resolve()
        try:
            target.relative_to(self.output_dir)
        except ValueError as exc:
            raise ValueError(f"path escapes skill directory: {path}") from exc
        return target


def _promote_staging(staging: Path, final_dir: Path) -> None:
    """Atomically move a fully-built staging skill into its library slot.

    Moving any existing version aside first keeps the swap atomic from the
    registry's view — the slot is never seen partially populated.
    """
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        backup = final_dir.parent / f".old_{final_dir.name}_{os.getpid()}"
        shutil.rmtree(backup, ignore_errors=True)
        final_dir.rename(backup)
        try:
            staging.rename(final_dir)
        finally:
            shutil.rmtree(backup, ignore_errors=True)
    else:
        staging.rename(final_dir)


async def build_skill(
    host: str,
    probe_urls: list[str],
    *,
    notes: str = "",
    output_dir: Path | None = None,
    model: str | None = None,
    max_turns: int = MAX_TURNS,
) -> Path | None:
    """Build one access skill and return its directory on success."""
    import openai

    base_url = os.environ.get("DYNAMIC_BUILDER_BASE_URL", "")
    if not base_url:
        logger.error(
            "DYNAMIC_BUILDER_BASE_URL is not set — the dynamic skill builder "
            "needs an OpenAI-compatible endpoint (e.g. https://api.openai.com/v1). "
            "Skipping skill generation for %s.", host,
        )
        return None

    final_dir = output_dir or Path("searchos/skills/library/access") / _skill_dir_name(host)
    # Build in a hidden sibling staging dir so a half-written skill is never
    # visible to the registry mid-generation; promote it into the library
    # atomically only after the smoke gate passes (same parent => same
    # filesystem => the rename is atomic).
    staging = final_dir.parent / f".staging_{final_dir.name}_{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    workspace = BuilderWorkspace(staging)

    model_id = model or os.environ.get("DYNAMIC_BUILDER_MODEL", DEFAULT_MODEL)
    client = openai.AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=base_url,
    )

    logger.info("dynamic builder: host=%s output=%s", host, final_dir)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(host, probe_urls, notes)},
    ]

    for turn in range(max_turns):
        logger.info("dynamic builder: turn %s/%s", turn + 1, max_turns)
        response = await client.chat.completions.create(
            model=model_id,
            max_tokens=8192,
            tools=BuilderWorkspace.TOOL_DEFINITIONS,
            messages=messages,
        )

        choice = response.choices[0]
        msg = choice.message
        tool_calls = msg.tool_calls or []
        # Echo the assistant turn back verbatim (content + any tool_calls).
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            **({"tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name,
                                 "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]} if tool_calls else {}),
        })

        if not tool_calls:
            break

        for tc in tool_calls:
            messages.append(await _run_tool(workspace, tc))
    else:
        logger.warning("dynamic builder reached max turns for %s", host)

    if not _skill_is_complete(workspace.output_dir):
        logger.warning("dynamic builder did not produce a complete skill for %s", host)
        shutil.rmtree(staging, ignore_errors=True)
        return None
    if not await _skill_smoke_passes(workspace.output_dir):
        logger.warning(
            "built skill for %s fails its functional smoke test "
            "(every function network/access-errors) — not installing", host,
        )
        shutil.rmtree(staging, ignore_errors=True)
        return None
    _promote_staging(staging, final_dir)
    return final_dir


def _executor_param_keys(executor_src: str) -> set[str]:
    """Every key the executor pulls out of ``params`` — ``params.get("k")``,
    ``params.get('k', ...)``, and ``params["k"]`` / ``params['k']``.

    Used to assert the manifest's ``params_schema`` covers what the executor
    actually reads; otherwise the typed-tool schema omits real args and the
    agent can never pass them.
    """
    import re

    keys: set[str] = set()
    # ``params.get("k")`` / ``params.get('k', default)`` — agent-input reads.
    # ``(?<!\w)`` so a local dict like ``query_params.get(...)`` /
    # ``search_params.get(...)`` doesn't match ``params.get`` by substring.
    for m in re.finditer(r"""(?<!\w)params\.get\(\s*["']([^"']+)["']""", executor_src):
        keys.add(m.group(1))
    # ``params["k"]`` subscript reads — but NOT assignment targets
    # ``params["k"] = ...``, which build a local HTTP query dict that happens to
    # also be named ``params`` (a common pattern in these executors).
    for m in re.finditer(r"""(?<!\w)params\[\s*["']([^"']+)["']\s*\]""", executor_src):
        if re.match(r"\s*=(?!=)", executor_src[m.end():]):
            continue  # assignment, not a read of agent input
        keys.add(m.group(1))
    return keys


def _skill_is_complete(output_dir: Path) -> bool:
    """A skill is complete only with executor.py AND a canonical manifest
    (parses + carries a non-empty ``params_schema``) whose schema covers every
    argument executor.py reads. Guards against the LLM emitting a file that
    exists but doesn't match the manifest contract."""
    import yaml

    executor = output_dir / "executor.py"
    if not executor.exists():
        return False
    manifest = output_dir / "manifest.yaml"
    if not manifest.exists():
        return False
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("built manifest.yaml is not valid YAML: %s", manifest)
        return False
    ps = data.get("params_schema") if isinstance(data, dict) else None
    if not isinstance(ps, dict) or not ps:
        logger.warning("built manifest.yaml lacks a params_schema: %s", manifest)
        return False

    # Cross-check: every param the executor reads must be declared in the
    # manifest, or the typed tool can't expose it to the agent.
    try:
        read_keys = _executor_param_keys(executor.read_text(encoding="utf-8"))
    except Exception:
        read_keys = set()
    missing = read_keys - set(ps.keys())
    if missing:
        logger.warning(
            "built manifest.yaml params_schema is missing keys the executor "
            "reads %s: %s — the agent could never pass them",
            sorted(missing), manifest,
        )
        return False
    return True


# Error substrings that mean the executor never reached usable data (site
# unreachable or blocking) — a bespoke extractor for it is dead on arrival.
_NETWORK_FAIL_MARKERS = (
    "403", "401", "forbidden", "unauthorized", "captcha", "cloudflare",
    "timeout", "timed out", "connection", "refused", "blocked", "ssl",
    "getaddrinfo", "name resolution", "proxy",
)

# Error substrings that mean the executor's OWN code is broken (not a missing
# arg, not the site) — such a skill fails every call regardless of args, so
# hard-fail and don't ship it.
_CODE_BUG_MARKERS = (
    "has no attribute", "not callable", "not subscriptable",
    "unexpected keyword argument", "positional argument",
    "is not defined", "nonetype",
)


def _manifest_functions(output_dir: Path) -> list[str]:
    """Function names listed in the canonical manifest's ``function`` param."""
    import re

    import yaml
    try:
        data = yaml.safe_load((output_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    desc = str(((data.get("params_schema") or {}).get("function") or {}).get("description") or "")
    return re.findall(r"^\s*-\s*([A-Za-z_]\w*)", desc, re.M)


async def _skill_smoke_passes(output_dir: Path, *, max_funcs: int = 6) -> bool:
    """Call ``execute()`` on the listed functions and judge whether the skill
    actually works against its site.

    Pass if any function returns a clean, data-bearing result. Block install
    only when we positively see a network/access failure (403, timeout, …) and
    never get clean data — a skill whose every call is blocked is useless.
    Functions that merely error on missing params get the benefit of the doubt
    (the executor ran; it just needs arguments).
    """
    import re

    import yaml
    from searchos.skills.runtime.executor_runtime import run_executor

    funcs = _manifest_functions(output_dir)
    if not funcs:
        return True  # nothing to probe — file/schema gate already passed
    try:
        data = yaml.safe_load((output_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
        schema_keys = set((data.get("params_schema") or {}).keys())
    except Exception:
        schema_keys = set()
    saw_network_fail = False
    for name in funcs[:max_funcs]:
        try:
            res = await run_executor(output_dir, {"function": name}, {})
        except Exception:
            saw_network_fail = True
            continue
        if not isinstance(res, dict):
            continue
        err = res.get("error")
        if not err and res.get("success") is not False:
            return True  # clean, data-bearing result → skill works
        if err:
            err_l = str(err).lower()
            # A "missing required parameter 'X'" where X isn't even declared in
            # the manifest is a manifest↔executor contract gap, not a benign
            # needs-args result: the agent could never supply X. Hard-fail.
            m = re.search(r"required parameter[:\s]+['\"]?([a-z_]\w*)", err_l)
            if m and m.group(1) not in {k.lower() for k in schema_keys}:
                logger.warning(
                    "smoke test: %s reports missing param %r absent from "
                    "params_schema — manifest/executor contract gap",
                    name, m.group(1),
                )
                return False
            if any(mk in err_l for mk in _CODE_BUG_MARKERS):
                logger.warning(
                    "smoke test: %s errored with a code-level bug (%r) — "
                    "executor is broken regardless of args",
                    name, str(err)[:200],
                )
                return False
            if any(mk in err_l for mk in _NETWORK_FAIL_MARKERS):
                saw_network_fail = True
    return not saw_network_fail


async def _run_tool(workspace: BuilderWorkspace, tool_call: Any) -> dict[str, Any]:
    try:
        args = json.loads(tool_call.function.arguments or "{}")
        result = await workspace.dispatch(tool_call.function.name, args)
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if len(payload) > 10000:
        payload = f"{payload[:10000]}...[truncated]"
    return {"role": "tool", "tool_call_id": tool_call.id, "content": payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a SearchOS access skill for a dynamic website.",
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--urls", required=True, nargs="+")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    result = asyncio.run(build_skill(
        host=args.host,
        probe_urls=args.urls,
        notes=args.notes,
        output_dir=Path(args.output) if args.output else None,
        model=args.model,
        max_turns=args.max_turns,
    ))
    if result:
        print(f"skill created at: {result}")
        return 0
    print("failed to create skill", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
