"""仓库根 .env 的读写 — TUI 配置向导与 web 设置 API 共用的单一写入点。

只依赖 stdlib（配置向导必须在 ``searchos.config.settings`` 首次 import 之前
可用）。本模块无锁、无状态：并发控制由调用方负责——web 侧统一在
``settings_store`` 的 asyncio.Lock 内调用，TUI 向导是单线程交互。跨进程
（TUI 与 web 同时写）为 last-writer-wins，单用户本地部署可接受。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

_ENV_HEADER = "# SearchOS 配置 — 由配置向导/Web 设置生成，可手动编辑；参考 .env.example"

_MAX_VALUE_LEN = 1024
# 可见 ASCII（无空白/控制字符）；引号/#/反斜杠单独拒绝，避免 dotenv 解析歧义。
_VISIBLE_ASCII_RE = re.compile(r"^[\x21-\x7e]*$")
_BAD_VALUE_CHARS = set("#'\"`\\")


def find_env_path(start: Path | None = None) -> Path:
    """定位 .env：start(或 cwd) 及包上级目录中已存在者优先，否则 start/.env。"""
    base = start or Path.cwd()
    for parent in [base, *Path(__file__).resolve().parents]:
        env = parent / ".env"
        if env.exists():
            return env
    return base / ".env"


def validate_env_value(value: str) -> None:
    """拒绝会破坏 .env 单行 KEY=VALUE 语义的值；空串合法（= 清除该键）。

    换行是行注入向量（``x\\nSF_Y=evil``）；``#`` 在未加引号时被 dotenv 视为
    注释起点；引号/反斜杠会引入解析歧义——一律拒绝而非转义。
    """
    if len(value) > _MAX_VALUE_LEN:
        raise ValueError(f"Value too long ({len(value)} > {_MAX_VALUE_LEN} chars)")
    if not _VISIBLE_ASCII_RE.fullmatch(value):
        raise ValueError("Value must be printable ASCII without whitespace or control characters")
    bad = _BAD_VALUE_CHARS & set(value)
    if bad:
        raise ValueError(f"Value must not contain: {' '.join(sorted(bad))}")


def update_env_file(path: Path, updates: Mapping[str, str]) -> None:
    """把键值写入 .env：已有键原位替换、新键追加；原子写（tmp + os.replace）。

    保留既有注释与行顺序；path 不存在时以一行 header 注释新建。
    """
    lines = path.read_text().splitlines() if path.exists() else [_ENV_HEADER]
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        key = None
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# --- SearchOS 配置向导生成 ---")
        out.extend(f"{k}={v}" for k, v in remaining.items())

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, path)


def apply_env_updates(path: Path, updates: Mapping[str, str]) -> None:
    """写入 .env 并同步 os.environ（空串值 → 从 os.environ 移除）。"""
    update_env_file(path, updates)
    for key, value in updates.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def remove_env_keys(path: Path, keys: Iterable[str]) -> list[str]:
    """从 .env 物理删除指定键的赋值行（保留注释与其余行顺序，原子写）。

    返回实际删除的键名列表；path 不存在或无匹配时返回空列表、不写盘。
    删除后若产生连续空行会折叠为一行，避免留下大片空白。
    """
    if not path.exists():
        return []
    targets = {k for k in keys}
    lines = path.read_text().splitlines()
    out: list[str] = []
    removed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in targets:
                removed.append(key)
                continue
        # 折叠因删除产生的连续空行。
        if not stripped and out and not out[-1].strip():
            continue
        out.append(line)
    if not removed:
        return []
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, path)
    return removed


__all__ = [
    "apply_env_updates",
    "find_env_path",
    "remove_env_keys",
    "update_env_file",
    "validate_env_value",
]
