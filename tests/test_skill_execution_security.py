"""Skill Execution 的隔离与权限契约。"""

from __future__ import annotations

import ast
import asyncio
import os
import time
from pathlib import Path

import pytest

from searchos.skills.runtime.executor_runtime import ExecutionPolicy, run_executor


def _skill(tmp_path: Path, body: str) -> Path:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "executor.py").write_text(body, encoding="utf-8")
    return skill_dir


def test_browser_automation_permission_is_limited_to_bundled_skills() -> None:
    assert ExecutionPolicy.bundled().allow_browser_automation is True
    assert ExecutionPolicy.generated(("example.com",)).allow_browser_automation is False


@pytest.mark.asyncio
async def test_browser_runtime_path_is_exposed_only_to_bundled_skills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_path = tmp_path / "browser-runtime"
    browser_path.mkdir()
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browser_path))
    skill_dir = _skill(
        tmp_path,
        """
import os

async def execute(params, ctx):
    return {"browser_path": os.getenv("PLAYWRIGHT_BROWSERS_PATH")}
""",
    )

    bundled = await run_executor(skill_dir, {}, policy=ExecutionPolicy.bundled())
    generated = await run_executor(skill_dir, {}, policy=ExecutionPolicy.generated(()))

    assert bundled == {"browser_path": str(browser_path)}
    assert generated == {"browser_path": None}


@pytest.mark.asyncio
async def test_executor_runs_outside_main_process(tmp_path: Path) -> None:
    skill_dir = _skill(
        tmp_path,
        """
import os

async def execute(params, ctx):
    os.environ["SEARCHOS_EXECUTOR_ESCAPE"] = "child"
    return {"pid": os.getpid()}
""",
    )

    os.environ.pop("SEARCHOS_EXECUTOR_ESCAPE", None)
    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result["pid"] != os.getpid()
    assert "SEARCHOS_EXECUTOR_ESCAPE" not in os.environ


@pytest.mark.asyncio
async def test_executor_cannot_read_secrets_or_files_outside_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-secret", encoding="utf-8")
    monkeypatch.setenv("SEARCHOS_TEST_SECRET", "env-secret")
    skill_dir = _skill(
        tmp_path,
        f"""
import os

async def execute(params, ctx):
    return {{
        "env": os.getenv("SEARCHOS_TEST_SECRET"),
        "file": open({str(secret_file)!r}, encoding="utf-8").read(),
    }}
""",
    )

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result["error_type"] == "policy_violation"
    assert "secret.txt" in result["error"]
    assert "env-secret" not in str(result)


@pytest.mark.asyncio
async def test_executor_environment_is_scrubbed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCHOS_TEST_SECRET", "env-secret")
    skill_dir = _skill(
        tmp_path,
        """
import os

async def execute(params, ctx):
    return {"secret": os.getenv("SEARCHOS_TEST_SECRET")}
""",
    )

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result == {"secret": None}


@pytest.mark.asyncio
async def test_proxy_credentials_are_not_exposed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy-user:proxy-pass@127.0.0.1:8080/token")
    skill_dir = _skill(
        tmp_path,
        """
import os

async def execute(params, ctx):
    return {"proxy": os.getenv("HTTPS_PROXY")}
""",
    )

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result == {"proxy": "https://127.0.0.1:8080"}


@pytest.mark.asyncio
async def test_executor_may_read_its_own_skill_files(tmp_path: Path) -> None:
    skill_dir = _skill(
        tmp_path,
        """
async def execute(params, ctx):
    return {"value": (ctx.skill_dir / "fixture.txt").read_text()}
""",
    )
    (skill_dir / "fixture.txt").write_text("allowed", encoding="utf-8")

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result == {"value": "allowed"}


@pytest.mark.asyncio
async def test_executor_cannot_spawn_subprocess(tmp_path: Path) -> None:
    skill_dir = _skill(
        tmp_path,
        """
import subprocess
import sys

async def execute(params, ctx):
    subprocess.run([sys.executable, "-c", "print('escaped')"], check=True)
    return {"escaped": True}
""",
    )

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result["error_type"] == "policy_violation"
    assert "subprocess" in result["error"].lower()


@pytest.mark.asyncio
async def test_executor_cannot_import_native_escape_modules(tmp_path: Path) -> None:
    skill_dir = _skill(
        tmp_path,
        """
async def execute(params, ctx):
    try:
        import ctypes
    except ImportError:
        return {"blocked": True}
    return {"blocked": False}
""",
    )

    result = await run_executor(skill_dir, {}, {}, policy=ExecutionPolicy.bundled())

    assert result == {"blocked": True}


@pytest.mark.asyncio
async def test_generated_executor_cannot_open_arbitrary_network(tmp_path: Path) -> None:
    skill_dir = _skill(
        tmp_path,
        """
import socket

async def execute(params, ctx):
    socket.create_connection(("127.0.0.1", 9), timeout=0.1)
    return {"escaped": True}
""",
    )

    result = await run_executor(
        skill_dir,
        {},
        {},
        policy=ExecutionPolicy.generated(()),
    )

    assert result["error_type"] == "policy_violation"
    assert "network" in result["error"].lower()


@pytest.mark.asyncio
async def test_generated_executor_may_reach_declared_target_host(tmp_path: Path) -> None:
    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(4096)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    try:
        server = await asyncio.start_server(respond, "127.0.0.1", 0)
    except PermissionError:
        pytest.skip("test sandbox does not allow binding a loopback socket")
    port = server.sockets[0].getsockname()[1]
    skill_dir = _skill(
        tmp_path,
        f"""
import urllib.request

async def execute(params, ctx):
    with urllib.request.urlopen("http://127.0.0.1:{port}", timeout=2) as response:
        return {{"body": response.read().decode()}}
""",
    )
    try:
        result = await run_executor(
            skill_dir,
            {},
            {},
            policy=ExecutionPolicy.generated(("127.0.0.1",)),
        )
    finally:
        server.close()
        await server.wait_closed()

    assert result == {"body": "ok"}


@pytest.mark.asyncio
async def test_executor_timeout_kills_isolated_process(tmp_path: Path) -> None:
    marker = tmp_path / "late-write.txt"
    skill_dir = _skill(
        tmp_path,
        f"""
import asyncio
from pathlib import Path

async def execute(params, ctx):
    await asyncio.sleep(2)
    Path({str(marker)!r}).write_text("escaped")
    return {{"ok": True}}
""",
    )
    started = time.monotonic()

    result = await run_executor(
        skill_dir,
        {},
        {},
        policy=ExecutionPolicy.bundled(timeout_s=0.2),
    )
    await asyncio.sleep(0.3)

    assert time.monotonic() - started < 1.5
    assert result["error_type"] == "timeout"
    assert not marker.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expression",
    ["['not-a-dict']", "{'payload': 'x' * 2048}"],
)
async def test_executor_result_contract_is_enforced(
    tmp_path: Path,
    expression: str,
) -> None:
    skill_dir = _skill(
        tmp_path,
        f"""
async def execute(params, ctx):
    return {expression}
""",
    )

    result = await run_executor(
        skill_dir,
        {},
        {},
        policy=ExecutionPolicy.bundled(max_result_bytes=1024),
    )

    assert result["error_type"] == "invalid_result"


def test_bundled_executors_do_not_use_eval_or_subprocess() -> None:
    access_root = Path(__file__).resolve().parents[1] / "searchos/skills/library/access"
    violations: list[str] = []
    for executor in access_root.rglob("executor.py"):
        if "_rejected" in executor.parts:
            continue
        tree = ast.parse(executor.read_text(encoding="utf-8"), filename=str(executor))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "eval":
                    violations.append(f"{executor}: eval")
            if isinstance(node, ast.Import) and any(
                alias.name == "subprocess" for alias in node.names
            ):
                violations.append(f"{executor}: subprocess import")
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                violations.append(f"{executor}: subprocess import")
    assert violations == []


def test_nuxt_jsonp_is_parsed_without_javascript_execution() -> None:
    from searchos.skills.library.access.www_shanghairanking_com.executor import (
        parse_nuxt_payload,
    )

    assert parse_nuxt_payload('__NUXT_JSONP__("/ranking", {"data": [1, 2]});') == {"data": [1, 2]}
    with pytest.raises(ValueError):
        parse_nuxt_payload('__NUXT_JSONP__("/ranking", process.exit());')


@pytest.mark.asyncio
async def test_dynamic_builder_probe_uses_same_execution_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from searchos.skills.evolution.dynamic_builder import BuilderWorkspace

    monkeypatch.setenv("SEARCHOS_TEST_SECRET", "env-secret")
    workspace = BuilderWorkspace(tmp_path / "builder", allowed_hosts=())

    env_result = await workspace.run_python(
        "import os; print(os.getenv('SEARCHOS_TEST_SECRET'))",
        timeout=2,
    )
    file_result = await workspace.run_python(
        f"open({str(tmp_path / 'outside.txt')!r}, 'w').write('escaped')",
        timeout=2,
    )

    assert env_result["exit_code"] == 0
    assert env_result["stdout"].strip() == "None"
    assert file_result["exit_code"] == -1
    assert "policy_violation" in file_result["stderr"]
    assert not (tmp_path / "outside.txt").exists()
