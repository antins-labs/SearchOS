"""沙箱内 SearchOS SDK：纯标准库，通过宿主桥调用已注册能力。

执行时由 exec 工具以 searchos_sdk.py 写入 package 目录，供用户代码 import。
"""

from __future__ import annotations

import json
import os
import socket

MAX_MESSAGE = 24_000_000


class SkillError(Exception):
    """宿主技能调用失败或返回非零退出码。"""

    def __init__(self, message, *, status=None, error=None, stderr="", exit_code=None):
        super().__init__(message)
        self.status = status
        self.error = error
        self.stderr = stderr
        self.exit_code = exit_code


def call(op: str, **payload) -> dict:
    """调用已注册的宿主能力，返回桥接层原始响应。"""
    if not isinstance(op, str) or not op:
        raise ValueError("op must be a nonempty string")
    request = {"op": op, **payload}
    request["token"] = os.environ["SEARCHOS_RUN_TOKEN"]
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(os.environ["SEARCHOS_BRIDGE_SOCKET"])
        connection.sendall(json.dumps(request).encode() + b"\n")
        with connection.makefile("rb") as stream:
            data = stream.readline(MAX_MESSAGE + 1)
    if len(data) > MAX_MESSAGE:
        raise ValueError("host capability output exceeds the result limit; read the saved artifact")
    if not data:
        raise ConnectionError("host capability closed without a response")
    return json.loads(data)


class _SkillHandle:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, **params):
        return self.call(params)

    def call(self, params: dict | None = None, **kwargs):
        """结构化调用：把参数交给技能的标准 run.py，解析 stdout JSON。"""
        if params is not None and kwargs:
            raise ValueError("pass either a params dict or keyword arguments, not both")
        if params is None:
            params = kwargs
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")
        result = call("skill.call", skill=self.name, params=params)
        return _structured_result(result)

    def run(self, argv, stdin: str = "") -> str:
        """原始命令出口：返回 stdout 文本，供非标准脚本使用。"""
        if not isinstance(argv, (list, tuple)) or not argv:
            raise ValueError("argv must be a nonempty list of strings")
        if any(not isinstance(item, str) for item in argv):
            raise ValueError("argv must contain only strings")
        result = call("skill.call", skill=self.name, argv=list(argv), stdin=stdin)
        return _raw_result(result)


def skill(name: str) -> _SkillHandle:
    """返回已加载技能的调用句柄。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("skill name must be a nonempty string")
    return _SkillHandle(name.strip())


def _raise_if_failed(result: dict) -> None:
    status = result.get("status")
    exit_code = result.get("exit_code")
    failed = status not in (None, "completed") or (exit_code is not None and exit_code != 0)
    if not failed:
        return
    error = result.get("error") or status or "skill call failed"
    raise SkillError(
        str(error),
        status=status,
        error=result.get("error"),
        stderr=result.get("stderr", ""),
        exit_code=exit_code,
    )


def _structured_result(result: dict) -> dict:
    _raise_if_failed(result)
    stdout = result.get("stdout", "")
    if not stdout.strip():
        raise SkillError(
            "skill returned empty stdout",
            status=result.get("status"),
            error=result.get("error"),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code"),
        )
    try:
        payload = json.loads(stdout)
    except ValueError as exc:
        raise SkillError(
            "skill stdout is not valid JSON",
            status=result.get("status"),
            error=str(exc),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code"),
        ) from exc
    if not isinstance(payload, dict):
        raise SkillError(
            "skill stdout must be a JSON object",
            status=result.get("status"),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code"),
        )
    return payload


def _raw_result(result: dict) -> str:
    _raise_if_failed(result)
    return result.get("stdout", "")
