"""Bounded, versioned byte snapshots. Callers own any decoded mutable objects."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class FileSnapshot:
    revision: str
    content: bytes


def _revision(stat: os.stat_result) -> str:
    values = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    return "-".join(f"{value:x}" for value in values)


_cache: OrderedDict[Path, FileSnapshot] = OrderedDict()
_lock = RLock()
_MAX_ENTRIES = 16
_MAX_BYTES = 32 * 1024 * 1024


def read_snapshot(path: Path) -> FileSnapshot:
    """Validate the file version every time; replacements invalidate all processes' caches."""
    path = path.absolute()
    revision = _revision(path.stat())
    with _lock:
        cached = _cache.get(path)
        if cached is not None and cached.revision == revision:
            _cache.move_to_end(path)
            return cached
    # fstat and bytes come from the same descriptor even if an atomic replace races us.
    with path.open("rb") as stream:
        snapshot = FileSnapshot(_revision(os.fstat(stream.fileno())), stream.read())
    with _lock:
        _cache[path] = snapshot
        _cache.move_to_end(path)
        while (
            len(_cache) > _MAX_ENTRIES
            or sum(len(item.content) for item in _cache.values()) > _MAX_BYTES
        ):
            _cache.popitem(last=False)
    return snapshot
