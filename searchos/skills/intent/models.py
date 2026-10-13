"""外部信号与统一技能生成请求；不包含生成或执行实现。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlparse

from searchos.skills.core.models import SkillCategory


def name_for_host(host: str) -> str:
    name = re.sub(r'[^a-z0-9]+', '-', host.lower()).strip('-')
    if not name or len(name) > 64:
        raise ValueError('host cannot form a portable skill name; specify an explicit name')
    return name


@dataclass(frozen=True)
class SkillSignal:
    """信号携带原始问题或轨迹；其来源不决定生成技能的类别。"""
    kind: Literal['trace', 'task', 'site']
    text: str = ''
    trace_path: Path | str | None = None
    host: str = ''
    probe_urls: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in {'trace', 'task', 'site'}:
            raise ValueError('unsupported skill signal')
        object.__setattr__(self, 'text', self.text.strip())
        if self.trace_path is not None:
            object.__setattr__(self, 'trace_path', Path(self.trace_path))
        object.__setattr__(self, 'host', self.host.strip().lower())
        object.__setattr__(self, 'probe_urls', tuple(dict.fromkeys(str(u).strip() for u in self.probe_urls if str(u).strip())))
        if self.kind == 'task' and not self.text:
            raise ValueError('task must not be empty')
        if self.kind == 'trace' and self.trace_path is None and not self.text:
            raise ValueError('trace requires text or trace_path')
        if self.kind == 'site':
            if not self.host:
                raise ValueError('site intent requires a host')
            if not self.probe_urls:
                object.__setattr__(self, 'probe_urls', ('https://' + self.host + '/',))
        elif self.host or self.probe_urls:
            raise ValueError('host/probe_urls belong to site signals')


@dataclass(frozen=True)
class SkillRequest:
    """Intent 的输出、Pipeline 的输入；一个请求对应一个待生成技能包。"""
    category: SkillCategory | str
    name: str
    description: str
    reason: str = ''
    subtask: str = ''
    host: str = ''
    probe_urls: tuple[str, ...] = ()
    action: Literal['create', 'update'] = 'create'

    def __post_init__(self):
        if self.action not in {'create', 'update'}:
            raise ValueError('request action must be create or update')
        if self.action == 'update' and not self.reason.strip():
            raise ValueError('update requires a concrete capability gap in reason')
        object.__setattr__(self, 'category', SkillCategory(self.category))
        for field in ('name', 'description', 'reason', 'host', 'subtask'):
            object.__setattr__(self, field, getattr(self, field).strip())
        object.__setattr__(self, 'host', self.host.lower())
        object.__setattr__(self, 'probe_urls', tuple(dict.fromkeys(str(u).strip() for u in self.probe_urls if str(u).strip())))
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', self.name) or len(self.name) > 64:
            raise ValueError('request name must be a portable skill name')
        if not self.description:
            raise ValueError('request description must not be empty')
        if self.category == SkillCategory.ACCESS:
            if self.action == 'create' and (not self.host or not self.probe_urls):
                raise ValueError('access request requires host and probe_urls')
            for url in self.probe_urls:
                parsed = urlparse(url)
                if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                    raise ValueError('probe URL must use HTTP(S)')
        elif self.host or self.probe_urls:
            raise ValueError('host and probe_urls belong to access requests')
