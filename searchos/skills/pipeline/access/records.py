"""构建诊断独立于技能资产；即时保存事件和停止原因，不记录环境或认证内容。"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re


class BuildRecord:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.secrets = [value for key, value in os.environ.items()
                        if re.search(r'KEY|TOKEN|PASSWORD|SECRET|COOKIE', key, re.I) and len(value) >= 8]

    def clean(self, value):
        if isinstance(value, dict):
            return {key: ('[REDACTED]' if re.search(r'^(authorization|cookie|set-cookie|password|api[_-]?key|access_token|auth_token|secret)$', key, re.I)
                          else self.clean(item)) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(item) for item in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            value = re.sub(r'(?i)(Bearer\s+)[\w.\-]+', r'\1[REDACTED]', value)
            return value[:12000] + ('…[truncated]' if len(value) > 12000 else '')
        return value

    def event(self, event, **data):
        path = self.root / 'events.jsonl'
        with path.open('a', encoding='utf-8') as handle:
            path.chmod(0o600)
            handle.write(json.dumps(self.clean(dict(event=event, at=datetime.now(timezone.utc).isoformat(), **data)), ensure_ascii=False) + '\n')

    def summary(self, diagnostics):
        temporary = self.root / 'builder.tmp'
        temporary.write_text(json.dumps(self.clean(diagnostics), ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(self.root / 'builder.json')
