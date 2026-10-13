from __future__ import annotations

import asyncio
import multiprocessing
from pathlib import Path

import pytest

from searchos.config.settings import settings
from searchos.tools.simple_browser.backend.base import BrowserService, FetchResult


class _CountingBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(
        self,
        url: str,
        *,
        query: str = "",
        timeout: float = 20.0,
    ) -> FetchResult:
        self.calls += 1
        await asyncio.sleep(0.05)
        return FetchResult(url=url, markdown=f"page:{url}")

    async def fetch_many(
        self,
        urls: list[str],
        *,
        query: str = "",
        timeout: float = 20.0,
    ) -> list[FetchResult]:
        return await asyncio.gather(*(
            self.fetch(url, query=query, timeout=timeout) for url in urls
        ))

    async def close(self) -> None:
        return None


def _process_fetch(
    cache_dir: str,
    counter_path: str,
    start_event,
) -> None:
    from searchos.config.settings import settings as process_settings

    process_settings.browser_disk_cache_enabled = True
    process_settings.browser_disk_cache_dir = cache_dir

    class _FileCountingBackend(_CountingBackend):
        async def fetch(
            self,
            url: str,
            *,
            query: str = "",
            timeout: float = 20.0,
        ) -> FetchResult:
            with Path(counter_path).open("a", encoding="utf-8") as handle:
                handle.write("fetch\n")
            await asyncio.sleep(0.4)
            return FetchResult(url=url, markdown=f"page:{url}")

    async def run() -> None:
        start_event.wait(timeout=10)
        service = BrowserService(_FileCountingBackend())
        await service.fetch("https://example.com/process-shared")

    asyncio.run(run())


@pytest.mark.asyncio
async def test_browser_usage_is_isolated_between_concurrent_tasks(
    tmp_path,
    monkeypatch,
) -> None:
    from searchos.tools.simple_browser.usage import start_tracking

    monkeypatch.setattr(settings, "browser_disk_cache_enabled", True)
    monkeypatch.setattr(settings, "browser_disk_cache_dir", str(tmp_path))
    service = BrowserService(_CountingBackend())

    async def run(url: str) -> dict[str, int]:
        usage = start_tracking()
        await service.fetch(url)
        return usage.to_dict()

    first, second = await asyncio.gather(
        run("https://example.com/a"),
        run("https://example.com/b"),
    )

    assert first == {
        "served": 0,
        "fetched": 1,
        "stored": 1,
        "coalesced": 0,
        "jina_api_calls": 0,
    }
    assert second == {
        "served": 0,
        "fetched": 1,
        "stored": 1,
        "coalesced": 0,
        "jina_api_calls": 0,
    }


@pytest.mark.asyncio
async def test_two_services_coalesce_a_shared_disk_cache_miss(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "browser_disk_cache_enabled", True)
    monkeypatch.setattr(settings, "browser_disk_cache_dir", str(tmp_path))
    backend = _CountingBackend()
    first = BrowserService(backend)
    second = BrowserService(backend)

    left, right = await asyncio.gather(
        first.fetch("https://example.com/shared"),
        second.fetch("https://example.com/shared"),
    )

    assert left.markdown == right.markdown == "page:https://example.com/shared"
    assert backend.calls == 1


@pytest.mark.asyncio
async def test_fetch_many_coalesces_duplicate_urls(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "browser_disk_cache_enabled", True)
    monkeypatch.setattr(settings, "browser_disk_cache_dir", str(tmp_path))
    backend = _CountingBackend()
    service = BrowserService(backend)

    results = await service.fetch_many([
        "https://example.com/shared",
        "https://example.com/shared",
    ])

    assert [result.markdown for result in results] == [
        "page:https://example.com/shared",
        "page:https://example.com/shared",
    ]
    assert backend.calls == 1


@pytest.mark.asyncio
async def test_jina_calls_are_recorded_in_task_local_usage(monkeypatch) -> None:
    from searchos.tools.simple_browser.backend.jina import JinaReaderBackend
    from searchos.tools.simple_browser.usage import start_tracking

    class _Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def text(self, **_kwargs):
            return "# cached test page"

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    usage = start_tracking()
    backend = JinaReaderBackend()

    result = await backend.fetch("https://example.com/jina")

    assert result.ok
    assert backend.api_calls == 1
    assert usage.jina_api_calls == 1


def test_two_processes_coalesce_a_shared_disk_cache_miss(tmp_path) -> None:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    counter_path = tmp_path / "backend_calls.txt"
    processes = [
        context.Process(
            target=_process_fetch,
            args=(str(tmp_path / "cache"), str(counter_path), start_event),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0]
    assert counter_path.read_text(encoding="utf-8").splitlines() == ["fetch"]
