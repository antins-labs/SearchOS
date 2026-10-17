from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from api.research.contracts import SourcesRequest


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=12000)
    frequency: Literal["daily", "weekly", "once"] = "daily"
    time: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=1, ge=1, le=7)
    date: str | None = None
    timezone: str = "Asia/Shanghai"
    effort: Literal["low", "medium", "high", "max"] = "medium"
    max_time: int = Field(default=300, ge=30, le=3600)
    sources: SourcesRequest = Field(default_factory=SourcesRequest)
    active: bool = False
    version: int | None = None

    @field_validator("title", "instruction")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("无效时区") from exc
        return value

    @model_validator(mode="after")
    def validate_scope(self):
        if self.frequency == "once":
            if not self.date:
                raise ValueError("单次计划需要日期")
            date.fromisoformat(self.date)
        if self.sources.mode != "web" and not self.sources.local:
            raise ValueError("资料任务需要明确指定文档")
        if self.sources.mode == "web" and self.sources.local:
            raise ValueError("联网任务不能包含资料授权")
        return self


def next_occurrence(payload: dict, after: float) -> float | None:
    """Find a wall-clock occurrence, skipping DST gaps, with one run per date."""
    zone = ZoneInfo(payload["timezone"])
    local = datetime.fromtimestamp(after, zone)
    hour, minute = map(int, payload["time"].split(":"))
    first = date.fromisoformat(payload["date"]) if payload["frequency"] == "once" else local.date()
    for offset in range(1 if payload["frequency"] == "once" else 9):
        day = first + timedelta(days=offset)
        if payload["frequency"] == "weekly" and day.isoweekday() != payload["weekday"]:
            continue
        candidate = datetime.combine(day, time(hour, minute), tzinfo=zone)
        stamp = candidate.timestamp()
        roundtrip = datetime.fromtimestamp(stamp, UTC).astimezone(zone)
        if (roundtrip.hour, roundtrip.minute, roundtrip.date()) != (hour, minute, day):
            continue  # Nonexistent local time, e.g. a spring-forward gap.
        if stamp > after:
            return stamp
    return None


def in_quiet_hours(preferences: dict, now: float) -> bool:
    if not preferences.get("quiet_enabled"):
        return False
    local = datetime.fromtimestamp(now, ZoneInfo(preferences.get("timezone", "Asia/Shanghai")))
    current = local.strftime("%H:%M")
    start, end = preferences.get("quiet_start", "22:00"), preferences.get("quiet_end", "08:00")
    if start == end:
        return False
    return start <= current < end if start < end else current >= start or current < end
