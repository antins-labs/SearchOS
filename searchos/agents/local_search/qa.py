"""WebUI adapter for the existing Local Search Agent and native local tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.utils.json import parse_partial_json

from searchos.agents.local_search import create_qa_graph
from searchos.harness.answer_stream import message_chunk_text
from searchos.harness.middleware.context.utils.messages import model_input_limit
from searchos.local.index.source_registry import SourceRecord
from searchos.local.models import locator_group_label
from searchos.local.reader.references import build_ref_id, parse_ref_id, resolve_reference
from searchos.local.reader.tools import local_open, selected_document_scope

# Prefill eligibility, not a limit on how long the Agent may continue reading.
_PREFILL_MAX_TOKENS = 72_000


def _prefill_calls(blocks, model, budget, task):
    """Only pre-read when all selected primary text fits; never truncate a document."""
    window = model_input_limit(model) or 100_000
    allowance = min(_PREFILL_MAX_TOKENS, int(window * 0.75))
    # Leave room for the agent prompt and native source metadata/tool schemas.
    estimated = estimate_tokens(task.content) + 4000
    calls = []
    seen = set()
    for record, block in blocks:
        ref = build_ref_id(
            library_id=record.library_id, document_id=record.document_id,
            source_revision=record.source_revision, locators=list(block.source_locators),
        )
        if ref in seen:
            # Overlapping source blocks require the normal locator-driven reader.
            return []
        seen.add(ref)
        for offset in range(0, len(block.text), 20_000):
            size = min(20_000, len(block.text) - offset)
            estimated += estimate_tokens(block.text[offset:offset + size]) + 400
            calls.append({"name": "local_open", "args": {
                "ref_id": ref, "loc": offset, "max_chars": size,
            }, "id": f"prefill_{len(calls)}", "type": "tool_call"})
        if estimated > allowance or len(calls) >= budget.tool_calls:
            return []
    return calls


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(char.isascii() for char in text)
    return (ascii_chars + 2) // 3 + (len(text) - ascii_chars) * 2


@dataclass(frozen=True)
class QABudget:
    tool_calls: int = 48


@dataclass
class AgentAnswer:
    answer: str
    observations: list[dict[str, Any]] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    model_calls: int = 0
    input_tokens_estimate: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "answered"


class LocalQAMiddleware(AgentMiddleware):
    """Observe native tools and enforce resources, without a second agent loop."""

    def __init__(self, records, budget, on_tool=None, on_read=None):
        self.records: dict[str, SourceRecord] = records
        self.budget = budget
        self.result = AgentAnswer(answer="")
        self.on_tool = on_tool
        self.on_read = on_read
        self.tool_count = 0
        self._read_nudged = False
        self._tool_lock = asyncio.Lock()

    async def awrap_model_call(self, request, handler):
        text = "\n".join(message_chunk_text(message) for message in request.messages)
        image_count = sum(
            isinstance(block, dict) and block.get("type") in {"image", "image_url"}
            for message in request.messages if isinstance(message.content, list)
            for block in message.content
        )
        system = message_chunk_text(request.system_message) if request.system_message else ""
        schema_chars = sum(len(str(getattr(tool, "args", tool))) for tool in request.tools)
        estimated = estimate_tokens(system + text) + schema_chars // 2 + image_count * 3000 + 64
        if self.tool_count >= self.budget.tool_calls:
            request = request.override(
                tools=[tool for tool in request.tools if tool.name == "local_answer"],
                tool_choice={"type": "function", "function": {"name": "local_answer"}},
                messages=[*request.messages, HumanMessage(content=(
                    "本轮工具预算已用完。请根据已读原文调用 local_answer 回答问题，并说明尚未覆盖的范围。"
                ), additional_kwargs={"sf_synthetic": True})],
            )
            self.result.stop_reason = "budget"
        self.result.model_calls += 1
        self.result.input_tokens_estimate += estimated
        return await handler(request)

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state, runtime):
        last = state["messages"][-1]
        if (self.result.stop_reason == "budget" and isinstance(last, AIMessage)
                and (any(call["name"] != "local_answer" for call in last.tool_calls)
                     or (not last.tool_calls and not message_chunk_text(last).strip()))):
            raise RuntimeError("Local Search Agent 未返回最终答案")
        if (isinstance(last, AIMessage)
                and all(call["name"] == "local_answer" for call in last.tool_calls)
                and not self.result.observations
                and not self.result.tool_counts.get("local_open")
                and self.tool_count < self.budget.tool_calls
                and not self._read_nudged):
            self._read_nudged = True
            return {"messages": [
                *[ToolMessage(content="尚无原文记录，请先读取来源。", tool_call_id=call["id"])
                  for call in last.tool_calls],
                HumanMessage(content=(
                "当前尚无原文阅读记录。请根据问题定位相关章节，使用 local_open 读取原文后作答。"
            ))], "jump_to": "model"}
        return None

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call
        name, arguments = call["name"], call["args"]
        if name == "local_answer":
            result = await handler(request)
            if getattr(result, "status", None) == "error":
                raise RuntimeError("Local Search Agent 未返回最终答案")
            self.result.answer = arguments["answer"]
            return result
        # Serialize local reads so parallel tool batches share one accurate budget.
        async with self._tool_lock:
            if self.tool_count >= self.budget.tool_calls:
                return ToolMessage(content="本轮工具预算已用完，请总结已有支持与缺口。",
                                   tool_call_id=call["id"])
            key = json.dumps([name, arguments], sort_keys=True, ensure_ascii=False)
            self.tool_count += 1
            self.result.tool_counts[name] = self.result.tool_counts.get(name, 0) + 1
            result = await handler(request)
            content = message_chunk_text(result)
            artifact = getattr(result, "artifact", None) or {}
            metadata = artifact.get("local_source_metadata") or {}
            if name == "local_open" and metadata and "[LOCAL_SOURCE]" in content:
                raw_ref = str(metadata["ref_id"])
                record = self.records[parse_ref_id(raw_ref).document_id]
                resolved = resolve_reference(parse_ref_id(raw_ref), record.references,
                                             library_id=record.library_id,
                                             source_revision=record.source_revision)
                canonical = build_ref_id(
                    library_id=record.library_id, document_id=record.document_id,
                    source_revision=record.source_revision, locators=list(resolved.locators),
                )
                self.result.aliases[raw_ref] = canonical
                self.result.aliases[canonical] = canonical
                text = content.split("\n\n", 1)[-1]
                observation = {
                    "window_id": hashlib.sha256((key + content).encode()).hexdigest()[:24],
                    "ref_id": canonical, "document_id": record.document_id,
                    "tool_ref_id": raw_ref,
                    "location_label": locator_group_label(list(resolved.locators)),
                    "file": record.relative_path, "source_revision": record.source_revision,
                    "generation": record.generation,
                    "representation_id": metadata.get("representation_id"),
                    "locators": metadata.get("source_locator"),
                    "range": metadata.get("text_range"),
                    "offset_basis": "referenced_source_representation_characters",
                    "text": text, "tool_content": content,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "view": artifact.get("view"),
                }
                self.result.observations.append(observation)
                if self.on_read:
                    self.on_read(observation)
                content = (
                    f"[资料{len(self.result.observations)}] {record.relative_path} · "
                    f"{observation['location_label']}\n" + content
                )
                result = result.model_copy(update={"content": content})
            if self.on_tool:
                self.on_tool(name, arguments, {"content": content, "metadata": metadata})
            return result


async def run_document_qa(
    *, index_root, records: list[SourceRecord], query: str, history=None, model=None,
    on_tool=None, on_read=None, budget: QABudget | None = None, preload_blocks=None,
    on_delta=None, library_scope: bool = False,
) -> AgentAnswer:
    budget = budget or QABudget()
    scope = {record.document_id: record for record in records}
    with selected_document_scope(index_root, records):
        if model is None:
            from searchos.config.models import get_model_for

            model = get_model_for("sub_agent")
        observer = LocalQAMiddleware(scope, budget, on_tool, on_read)
        graph = create_qa_graph(model, middleware=[observer])
        scope_text = (
            "本轮允许读取整个当前知识库。先根据问题调用 local_catalog(query=...) 检索目录，"
            "再打开相关原文；不要顺序遍历全部文档。"
            if library_scope else
            "本轮只允许读取这些文档：\n" + "\n".join(
                f'{r.relative_path}: catalog_path="documents/{r.document_id}.md"' for r in records
            )
        )
        history_text = json.dumps((history or [])[-3:], ensure_ascii=False)
        if len(history_text) > 6000:
            history_text = history_text[:2000] + "\n[中间历史省略]\n" + history_text[-4000:]
        task = HumanMessage(content=(
            f"问题：{query}\n\n{scope_text}\n\n"
            f"历史只用于理解指代，不是事实依据：\n{history_text}\n\n"
            f"本轮最多调用 {budget.tool_calls} 次本地工具。请完成必要阅读，然后直接回答用户的问题。"
        ))
        messages = [task]
        calls = _prefill_calls(preload_blocks or [], model, budget, task)
        if calls:
            # Native reads keep source/version checks, preview locators and audit
            # events identical to model-requested reads, without an LLM per window.
            messages.append(AIMessage(content="", tool_calls=calls))
            async def read(request):
                return await local_open.ainvoke(request.tool_call)

            complete = True
            last_windows = {}
            for call in calls:
                reply = await observer.awrap_tool_call(
                    ToolCallRequest(tool_call=call, tool=local_open, state={}, runtime=None), read,
                )
                messages.append(reply)
                complete = complete and bool((reply.artifact or {}).get("local_source_metadata"))
                last_windows[call["args"]["ref_id"]] = message_chunk_text(reply)
            complete = complete and all("[END OF SOURCE]" in text for text in last_windows.values())
            messages.append(HumanMessage(content=(
                "所选文档的全部解析正文已通过本地工具读取，见上方原文。直接回答问题；"
                "需要核对图表或定位细节时仍可调用本地工具。"
                if complete else
                "已尝试预读所选文档，部分读取失败。请检查工具结果，按需继续读取后回答。"
            ), additional_kwargs={"sf_synthetic": True}))
        answer_calls = {}
        streamed = ""
        async for mode, payload in graph.astream(
            {"messages": messages},
            # Allow the graph's middleware nodes for every budgeted tool round.
            config={"configurable": {"thread_id": "local_qa"},
                    "recursion_limit": max(100, 8 * (budget.tool_calls + 1))},
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") != "model" or not observer.result.observations:
                    continue
                for part in getattr(chunk, "tool_call_chunks", []) or []:
                    key = (chunk.id, part.get("index", 0))
                    call = answer_calls.setdefault(key, {"name": "", "args": ""})
                    name = part.get("name") or ""
                    if name != call["name"]:
                        call["name"] += name
                    call["args"] += part.get("args") or ""
                    if call["name"] != "local_answer":
                        continue
                    try:
                        parsed = parse_partial_json(call["args"])
                    except (ValueError, TypeError):
                        continue
                    text = parsed.get("answer") if isinstance(parsed, dict) else None
                    if isinstance(text, str) and text.startswith(streamed):
                        if on_delta and len(text) > len(streamed):
                            on_delta(text[len(streamed):])
                        streamed = text
            if mode == "updates":
                for update in payload.values():
                    if not isinstance(update, dict):
                        continue
                    for message in update.get("messages", []):
                        if isinstance(message, AIMessage) and not message.tool_calls:
                            observer.result.answer = message_chunk_text(message).strip()
        if not observer.result.answer:
            raise RuntimeError("Local Search Agent 未返回答案")
        # Non-streaming providers and legacy free-text replies remain supported.
        if on_delta and observer.result.answer.startswith(streamed):
            on_delta(observer.result.answer[len(streamed):])
        return observer.result
