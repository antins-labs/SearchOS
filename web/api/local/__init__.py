"""Shared helpers for WebUI local background jobs."""

from __future__ import annotations

import asyncio
from weakref import WeakKeyDictionary

from searchos.config.settings import settings

_job_semaphores: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    WeakKeyDictionary()
)


def local_job_semaphore() -> asyncio.Semaphore:
    """Return a per-event-loop semaphore capping concurrent background jobs."""
    loop = asyncio.get_running_loop()
    semaphore = _job_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(max(1, settings.local_job_concurrency))
        _job_semaphores[loop] = semaphore
    return semaphore
