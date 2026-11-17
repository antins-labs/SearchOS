"""本地资料的原子文件写入、内容指纹和发布锁。"""

from __future__ import annotations

import asyncio
import fcntl
import functools
import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


def atomic_write_text(path: Path, content: str) -> None:
    """在同目录写入并同步临时文件，替换成功前保留原文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    """分块读取原文件或解析产物，返回内容指纹。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def file_stat_key(path: Path) -> tuple[str, int, int, int, int]:
    resolved = path.resolve()
    stat = resolved.stat()
    return (str(resolved), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


@functools.lru_cache(maxsize=4096)
def _sha256_by_stat(
    resolved_path: str,
    st_dev: int,
    st_ino: int,
    st_size: int,
    st_mtime_ns: int,
) -> str:
    del st_dev, st_ino, st_size, st_mtime_ns
    return file_sha256(Path(resolved_path))


def file_sha256_cached(path: Path) -> str:
    """按路径、设备、inode、大小和纳秒修改时间缓存内容指纹。"""
    return _sha256_by_stat(*file_stat_key(path))


@contextmanager
def advisory_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle: TextIO = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class AsyncAdvisoryLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: TextIO | None = None

    async def __aenter__(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._path.open("a+", encoding="utf-8")
        try:
            while True:
                try:
                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.05)
        except BaseException:
            self._handle.close()
            self._handle = None
            raise

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
