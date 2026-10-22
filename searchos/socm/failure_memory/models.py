"""搜索负面经验：四类记录及历史快照的单向转换。"""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from searchos.util.base_model import CamelModel


class FailureKind(StrEnum):
    QUERY = "query"
    SOURCE = "source"
    SKILL = "skill"
    PATH = "path"


class FailureScope(CamelModel):
    task_id: str = ""
    table_id: str = ""
    target_cells: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    source_scope_key: str = ""


class FailureMemory(CamelModel):
    kind: FailureKind
    target: str
    reason: str
    what_failed: str
    scope: FailureScope = Field(default_factory=FailureScope)
    operation: str = ""
    skill_version: str = ""
    task_id: str = ""
    agent_id: str = ""
    attempt: int = 0
    observation_ids: list[str] = Field(default_factory=list)
    source: str = "observation"
    guidance: str = ""
    confidence: Literal["low", "medium", "high"] = "low"
    id: str = ""
    observed_count: int = 1
    created_at: float = 0.0
    last_seen: float = 0.0
    superseded: bool = False

    @model_validator(mode="after")
    def require_observation(self):
        for name in ("target", "reason", "what_failed"):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} must describe an observed search failure")
            setattr(self, name, value)
        return self

    def key(self) -> str:
        scope = self.scope.model_dump()
        scope["target_cells"] = sorted(set(scope["target_cells"]))
        scope["entities"] = sorted(set(scope["entities"]))
        value = [
            self.kind.value,
            self.target,
            self.reason,
            self.operation,
            self.skill_version,
            scope,
        ]
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()


class FailureStore(CamelModel):
    records: list[FailureMemory] = Field(default_factory=list)

    def record(self, memory: FailureMemory) -> FailureMemory:
        """同一观察回放幂等；不同真实观察只在相同条件与范围下累计。"""
        key = memory.key()
        now = time.time()
        for existing in self.records:
            if existing.key() != key:
                continue
            incoming = set(memory.observation_ids)
            known = set(existing.observation_ids)
            if incoming and incoming <= known:
                return existing
            if existing.superseded:
                continue
            existing.observed_count += 1
            existing.observation_ids = list(
                dict.fromkeys([*existing.observation_ids, *memory.observation_ids])
            )
            existing.last_seen = memory.last_seen or now
            existing.what_failed = memory.what_failed
            if memory.guidance:
                existing.guidance = memory.guidance
            return existing
        memory = memory.model_copy(deep=True)
        memory.id = memory.id or uuid4().hex[:16]
        memory.created_at = memory.created_at or now
        memory.last_seen = memory.last_seen or memory.created_at
        memory.observation_ids = list(dict.fromkeys(memory.observation_ids))
        self.records.append(memory)
        return memory


def migrate_strategy_log(value: dict, source_scope_key: str = "") -> dict:
    """只读取旧 JSON；旧反模式类型与执行逻辑不进入新模块。"""
    records = []
    for item in value.get("patterns", []):
        kind = {"branch": "path"}.get(item.get("kind"), item.get("kind"))
        target = str(item.get("signature", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if kind not in {k.value for k in FailureKind} or not target or not reason:
            continue
        # 旧来源写入只保存域名，旧技能记录没有版本；无法恢复准确适用条件。
        if kind == "source" and not target.startswith(("https://", "http://", "local://")):
            continue
        if kind == "skill" and not item.get("skill_version"):
            continue
        # 旧传感器只有重复/停滞计数，没有查询结果的有效性判定。
        if kind == "query" and (
            target.startswith(("no-progress:", "state-stall:"))
            or "repeated" in reason
            or "stalled" in reason
        ):
            continue
        old_scope = item.get("scope") or {}
        records.append(
            dict(
                kind=kind,
                target=target,
                reason="historical_observation",
                what_failed=reason,
                scope=dict(
                    target_cells=old_scope.get("target_cells", []),
                    source_scope_key=source_scope_key,
                ),
                source="historical",
                observed_count=item.get("observed_count", 1),
                created_at=item.get("first_seen", 0),
                last_seen=item.get("last_seen", 0),
            )
        )
    for item in value.get("failure_memories", []):
        what = str(item.get("what_failed", "")).strip()
        klass = str(item.get("failure_class", "")).lower()
        kind = next(
            (
                kind
                for marker, kind in (
                    ("skill", "skill"),
                    ("source", "source"),
                    ("query", "query"),
                    ("path", "path"),
                    ("branch", "path"),
                )
                if marker in klass
            ),
            None,
        )
        if not kind or not what:
            continue
        applies = item.get("applies_to", "global")
        scope = {"source_scope_key": source_scope_key}
        if applies.startswith("cell:"):
            scope["target_cells"] = [applies[5:]]
        elif applies.startswith("entity:"):
            scope["entities"] = [applies[7:]]
        targets = item.get("do_not_retry") or []
        prefixes = {
            "query": ("query:", "search_query:"),
            "source": ("source:",),
            "skill": ("skill:",),
        }
        target = ""
        for candidate in targets:
            if not isinstance(candidate, str):
                continue
            for prefix in prefixes.get(kind, ()):
                if candidate.startswith(prefix):
                    target = candidate[len(prefix) :].strip()
                    break
            if target:
                break
        if kind == "path":
            target = what[:200]
        if not target or (
            kind == "source" and not target.startswith(("https://", "http://", "local://"))
        ):
            continue
        if kind == "skill" and not item.get("skill_version"):
            continue
        confidence = item.get("confidence", "low")
        records.append(
            dict(
                kind=kind,
                target=target,
                reason=klass or "historical_observation",
                what_failed=what,
                scope=scope,
                guidance=item.get("advice", ""),
                source="historical",
                skill_version=item.get("skill_version", ""),
                confidence=confidence if confidence in {"low", "medium", "high"} else "low",
                created_at=item.get("created_at", 0),
                last_seen=item.get("created_at", 0),
                superseded=item.get("superseded", False),
            )
        )
    return {"records": records}
