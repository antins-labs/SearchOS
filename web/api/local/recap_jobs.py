"""主题摘要后台刷新；pending 状态持久化在资料库目录中。"""

import asyncio
import logging
from pathlib import Path

from api.deps import LOCAL_DATA_ROOT
from searchos.local import messages
from searchos.local.catalog import CatalogMarkdownStore, CatalogService, ModelCatalogClient
from searchos.local.errors import user_message
from searchos.local.library import LocalLibraryService
from searchos.local.storage.files import AsyncAdvisoryLock

logger = logging.getLogger(__name__)
_tasks: dict[str, asyncio.Task] = {}


def schedule_topic_recaps(root: Path, *, retry_failed: bool = False) -> None:
    key = str(root.resolve())

    # Each request queues behind the cross-process recap lock. Later workers
    # read current pending state and exit without model calls if already done.
    async def run():
        await asyncio.sleep(1.2)
        try:
            await CatalogService(root, ModelCatalogClient()).refresh_pending(
                retry_failed=retry_failed
            )
        except Exception as exc:
            logger.exception("local topic recap failed: %s", root)
            async with AsyncAdvisoryLock(root / ".locks" / "catalog-transaction.lock"):
                store = CatalogMarkdownStore(root)
                state = store.read_state()
                for item in state["topics"].values():
                    if item["status"] == "pending":
                        item.update(
                            status="failed",
                            error=user_message(exc, messages.TOPIC_RECAP_FAILED),
                        )
                store.write_state(state)

    task = asyncio.create_task(run())
    task_key = f"{key}:{id(task)}"
    _tasks[task_key] = task
    task.add_done_callback(lambda _: _tasks.pop(task_key, None))


def resume_topic_recaps() -> None:
    for library in LocalLibraryService(LOCAL_DATA_ROOT).list_libraries():
        root = Path(library.index_root)
        if any(
            item["status"] == "pending"
            for item in CatalogMarkdownStore(root).read_state()["topics"].values()
        ):
            schedule_topic_recaps(root)


async def cancel_topic_recaps(root: Path) -> None:
    prefix = f"{root.resolve()}:"
    tasks = [task for key, task in list(_tasks.items()) if key.startswith(prefix)]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def stop_topic_recaps() -> None:
    tasks = list(_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
