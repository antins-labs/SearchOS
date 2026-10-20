"""保存每轮后台技能生成的进度、入库结果和当次技能正文。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def generation_directory(workspace: Path, generation_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", generation_id):
        raise ValueError("Invalid skill generation ID")
    directory = workspace / "skill_generations" / generation_id
    if not directory.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("Invalid skill generation path")
    return directory


def load_generation(workspace: Path, generation_id: str) -> dict:
    record = json.loads(
        (generation_directory(workspace, generation_id) / "status.json").read_text()
    )
    if record["status"] in {"queued", "running"}:
        try:
            os.kill(record["owner_pid"], 0)
        except ProcessLookupError:
            record["status"] = "interrupted"
        except PermissionError:
            pass  # 另一用户的存活进程仍可能在执行这次生成。
    record.pop("owner_pid", None)
    return record


class TraceSkillGeneration:
    """在搜索结束时创建记录；生成失败不改变搜索回答的完成状态。"""

    def __init__(self, workspace: Path, query: str, *, trace_offset: int = 0):
        self.id = uuid4().hex
        self.directory = generation_directory(workspace, self.id)
        self.directory.mkdir(parents=True)
        # 固定本轮观察，后续追问即使复用 workspace，也不会串入生成输入。
        with (workspace / "trajectory.jsonl").open("rb") as source:
            source.seek(trace_offset)
            (self.directory / "trace.jsonl").write_bytes(source.read())
        self.record = {
            "id": self.id,
            "query": query,
            "status": "queued",
            "stage": "intent",
            "created_at": _now(),
            "updated_at": _now(),
            "items": [],
            "error": "",
            "owner_pid": os.getpid(),
        }
        self._save()

    def _save(self) -> None:
        self.record["updated_at"] = _now()
        temporary = self.directory / "status.tmp"
        temporary.write_text(json.dumps(self.record, ensure_ascii=False, indent=2))
        temporary.replace(self.directory / "status.json")

    def _snapshot_skill(self, item: dict, report: dict, library: Path) -> None:
        from searchos.skills.core.schema import find_skill_entry, parse_skill_file

        try:
            package = Path(report["path"]).resolve()
            if not package.is_relative_to(library.resolve()):
                raise ValueError("Installed skill is outside the library")
            entry = find_skill_entry(package)
            if not entry.resolve().is_relative_to(package) or entry.stat().st_size > 262144:
                raise ValueError("Skill entry cannot be previewed")
            skill = parse_skill_file(entry)
            item["description"] = skill.meta.description or item.get("description", "")
            item["body"] = skill.body
        except Exception:
            # 入库成功与预览可用是两个状态，不能把读取失败说成生成失败。
            logger.warning("Cannot snapshot generated skill %s", item.get("name"), exc_info=True)

    async def run(self, *, library_path: Path, model=None, max_requests=None) -> None:
        from searchos.skills import generate_from_trace

        async def progress(event):
            stage = event["stage"]
            self.record["stage"] = stage
            if stage == "planned":
                self.record["items"] = [
                    {
                        key: request.get(key, "")
                        for key in ("name", "category", "action", "description", "reason")
                    }
                    | {"status": "pending"}
                    for request in event["requests"]
                ]
            elif stage in {"pipeline", "result"}:
                item = self.record["items"][event["index"]]
                if stage == "pipeline":
                    item["status"] = "running"
                else:
                    report = event["result"]
                    item.update(
                        {
                            key: report[key]
                            for key in ("name", "category", "action", "reason", "status", "error")
                            if key in report
                        }
                    )
                    if report["status"] == "installed":
                        self._snapshot_skill(item, report, library_path)
            self._save()

        try:
            self.record["status"] = "running"
            self._save()
            await generate_from_trace(
                self.directory / "trace.jsonl",
                library_path=library_path,
                model=model,
                max_requests=max_requests,
                on_progress=progress,
            )
            self.record["status"] = "completed"
        except asyncio.CancelledError:
            self.record["status"] = "interrupted"
            raise
        except Exception as exc:
            self.record["status"] = "error"
            self.record["error"] = str(exc)
            logger.warning("Trace skill generation failed", exc_info=True)
        finally:
            for item in self.record["items"]:
                if item["status"] in {"pending", "running"}:
                    item["status"] = "interrupted"
            try:
                self._save()
            except OSError:
                logger.warning("Cannot save trace skill generation status", exc_info=True)
