"""Orchestrator 澄清：阻塞等待、会话持久化，以及进程退出后的续跑。"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ClarifyClosed(Exception):
    """当前问题已结束或不存在。"""


class ClarifyInvalid(ValueError):
    """问题或回答不符合 AskUserQuestion 的结构。"""


def load_clarify(path: Path) -> dict[str, Any] | None:
    """读取会话目录中的澄清记录；文件缺失或损坏时返回 None。"""
    file = path / "clarify.json" if path.is_dir() else path
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def normalize_questions(questions: list[Any]) -> list[dict[str, Any]]:
    """对齐 JobSeeker：1–3 题，每题唯一 id、题干、2–5 个选项。"""
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
        raise ClarifyInvalid("questions must contain 1 to 3 items")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(questions):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if not isinstance(raw, dict):
            raise ClarifyInvalid(f"questions[{index}] must be an object")
        qid = str(raw.get("id") or "").strip()[:60]
        prompt = str(raw.get("prompt") or "").strip()[:240]
        options = raw.get("options")
        if not isinstance(options, list):
            raise ClarifyInvalid(f"questions[{index}].options must be a list")
        cleaned: list[str] = []
        for option in options:
            text = str(option).strip()[:200]
            if text and text not in cleaned:
                cleaned.append(text)
        allow = raw.get("allowMultiple")
        if not isinstance(allow, bool):
            raise ClarifyInvalid(f"questions[{index}].allowMultiple must be a boolean")
        if not qid or not prompt or not 2 <= len(cleaned) <= 5:
            raise ClarifyInvalid(
                f"questions[{index}] needs an id, a prompt, and 2 to 5 options"
            )
        if qid in seen:
            raise ClarifyInvalid(f"duplicate question id {qid}")
        seen.add(qid)
        normalized.append({
            "id": qid, "prompt": prompt, "options": cleaned, "allowMultiple": allow,
        })
    return normalized


def normalize_answers(questions: list[dict[str, Any]], payload: Any) -> list[dict[str, Any]]:
    """只接受选项内的选择；多选取消勾选上限以外的项；自定义文字可单独成答。"""
    if not isinstance(payload, dict):
        raise ClarifyInvalid("回答需使用对象")
    supplied = payload.get("answers", [])
    if not isinstance(supplied, list):
        raise ClarifyInvalid("回答需使用 answers 数组")
    answers: list[dict[str, Any]] = []
    for question in questions:
        item = next(
            (row for row in supplied if isinstance(row, dict) and row.get("id") == question["id"]),
            {},
        )
        selected = item.get("selected", [])
        chosen: list[str] = []
        if isinstance(selected, list):
            allowed = set(question.get("options") or [])
            for value in selected:
                text = str(value).strip()
                if text in allowed and text not in chosen:
                    chosen.append(text)
        if not question.get("allowMultiple"):
            chosen = chosen[:1]
        custom = str(item.get("custom") or "").strip()[:300]
        if not chosen and not custom:
            raise ClarifyInvalid(f"题目 {question['id']} 需要选择或补充文字")
        answer: dict[str, Any] = {"id": question["id"], "selected": chosen}
        if custom:
            answer["custom"] = custom
        answers.append(answer)
    return answers


def answer_value(answer: dict[str, Any]) -> str:
    parts = [str(item) for item in answer.get("selected") or []]
    custom = str(answer.get("custom") or "").strip()
    if custom:
        parts.append(custom)
    return "、".join(parts)


def supplement_query(
    query: str, questions: list[dict[str, Any]], answers: list[dict[str, Any]],
) -> str:
    """进程已退出时，用原问题加补充条件续跑同一会话。"""
    by_id = {item["id"]: item for item in answers}
    lines = [
        f"{question['prompt']}：{answer_value(by_id.get(question['id'], {}))}"
        for question in questions
    ]
    return f"{query.rstrip()}\n\n补充条件：\n" + "\n".join(lines)


def guidance_text(result: dict[str, Any]) -> str:
    return "用户已回答：" + json.dumps(result, ensure_ascii=False)


def parse_tui_selection(text: str, questions: list[dict[str, Any]]) -> dict[str, Any]:
    """交互 TUI：单题直接输入；多题用分号分隔。编号从 1 开始，`|` 后是补充文字。"""
    parts = [text.strip()] if len(questions) == 1 else [part.strip() for part in text.split(";")]
    if len(parts) != len(questions):
        raise ClarifyInvalid("每题一段，用分号分隔")
    supplied = []
    for question, part in zip(questions, parts):
        choice, _, custom = part.partition("|")
        selected: list[str] = []
        for token in choice.replace("，", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if token.isdigit():
                index = int(token) - 1
                if 0 <= index < len(question["options"]):
                    selected.append(question["options"][index])
            elif token in question["options"]:
                selected.append(token)
        supplied.append({"id": question["id"], "selected": selected, "custom": custom.strip()})
    return {"answers": normalize_answers(questions, {"answers": supplied})}


def cold_resume_payload(
    session_id: str,
    record: dict[str, Any],
    answers: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """组装续跑请求：同一会话、原问题，以及「补充条件」摘要。"""
    questions = record["pending_question"]["questions"]
    payload = dict(record.get("launch") or {})
    payload["query"] = supplement_query(
        str(record.get("query") or payload.get("query") or ""), questions, answers,
    )
    payload["follow_up_to"] = session_id
    if history is not None:
        payload["history"] = history
    return payload


class ClarifyGate:
    """一次研究运行内的 AskUserQuestion 等待点。

    在途子 Agent 继续做完当前批次；这里暂停 Orchestrator 的新派发和墙钟预算。
    活进程用 Future 交卷。进程退出后，澄清文件仍可供冷恢复。
    """

    def __init__(
        self,
        *,
        query: str = "",
        launch: dict[str, Any] | None = None,
        on_status=None,
        on_asked=None,
    ) -> None:
        self.query = query
        self.launch = launch
        self.on_status = on_status
        self.on_asked = on_asked
        self.workspace = None
        self.trajectory_logger = None
        self.budget = None
        self.scheduler = None
        self.pending: dict[str, Any] | None = None
        self.future: asyncio.Future | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.guidance: list[str] = []
        self._held = False
        self._lock = threading.Lock()

    def bind(self, *, workspace, trajectory_logger, budget, scheduler) -> None:
        self.workspace = workspace
        self.trajectory_logger = trajectory_logger
        self.budget = budget
        self.scheduler = scheduler

    def matches(self, question_id: str) -> bool:
        with self._lock:
            return bool(
                self.pending
                and self.pending.get("id") == question_id
                and self.future is not None
                and not self.future.done()
            )

    def submit(self, question_id: str, payload: Any) -> dict[str, Any]:
        with self._lock:
            if (
                self.pending is None
                or self.pending.get("id") != question_id
                or self.future is None
                or self.future.done()
                or self.loop is None
            ):
                raise ClarifyClosed("当前问题已结束或不存在")
            answers = normalize_answers(self.pending["questions"], payload)
            result = {"answers": answers}
            future, loop = self.future, self.loop

        def deliver() -> None:
            if not future.done():
                future.set_result(result)

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            deliver()
        else:
            loop.call_soon_threadsafe(deliver)
        return {"accepted": True}

    def take_guidance(self) -> list[str]:
        with self._lock:
            items, self.guidance = self.guidance, []
            return items

    async def ask(self, questions: list[Any]) -> dict[str, Any]:
        normalized = normalize_questions(questions)
        pending = {"id": "q_" + uuid.uuid4().hex, "questions": normalized}
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        with self._lock:
            if self.future is not None and not self.future.done():
                raise ClarifyInvalid("a question is already waiting")
            self.pending = pending
            self.future = future
            self.loop = loop
        self._pause_runtime()
        try:
            self._record(status="waiting_user", pending_question=pending)
            self._notify("waiting_user", pending)
            self._emit({
                "type": "question",
                "agent": "orchestrator",
                "question_id": pending["id"],
                "questions": pending["questions"],
                "text": f"等待回答 {len(pending['questions'])} 个问题",
            })
            if self.on_asked is not None:
                try:
                    self.on_asked(dict(pending))
                except Exception:
                    logger.exception("clarify notification failed")
            result = await future
        except asyncio.CancelledError:
            self._record(status="cancelled", pending_question=None)
            self._notify("running", None)
            raise
        else:
            self._record(status="running", pending_question=None)
            self._notify("running", None)
            self._emit({
                "type": "question_answered",
                "agent": "orchestrator",
                "question_id": pending["id"],
                "answers": result["answers"],
            })
            text = guidance_text(result)
            with self._lock:
                self.guidance.append(text)
            return result
        finally:
            self._resume_runtime()
            with self._lock:
                self.pending = None
                self.future = None
                self.loop = None

    def _pause_runtime(self) -> None:
        if self._held:
            return
        self._held = True
        if self.budget is not None:
            self.budget.pause()
        if self.scheduler is not None:
            self.scheduler.pause_dispatch()

    def _resume_runtime(self) -> None:
        if not self._held:
            return
        self._held = False
        if self.scheduler is not None:
            self.scheduler.resume_dispatch()
        if self.budget is not None:
            self.budget.resume()

    def _notify(self, status: str, pending: dict[str, Any] | None) -> None:
        if self.on_status is None:
            return
        try:
            self.on_status(status, pending)
        except Exception:
            logger.exception("clarify status update failed")

    def _emit(self, event: dict[str, Any]) -> None:
        logger_ = self.trajectory_logger
        if logger_ is None:
            return
        logger_._append_raw(event)

    def _record(self, *, status: str, pending_question: dict[str, Any] | None) -> None:
        if self.workspace is None:
            return
        path = Path(self.workspace.path) / "clarify.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": status,
            "pending_question": pending_question,
            "query": self.query,
            "launch": self.launch,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
