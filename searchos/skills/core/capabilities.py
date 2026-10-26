"""逐能力可用性的简明元数据与发布注解；验收明细保留在构建记录。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_KEY = "searchos-capabilities"
_START = "<!-- searchos-capabilities:start -->"
_END = "<!-- searchos-capabilities:end -->"
_BLOCK = re.compile(r"\n\n" + re.escape(_START) + r".*?" + re.escape(_END) + r"\n?", re.S)
_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|$)", re.M | re.S)
_STATUS = {"available": "可用", "unavailable": "不可用", "incomplete": "未完成"}


def _normalize(results: dict) -> dict:
    if not isinstance(results, dict):
        raise ValueError("capability_results must be an object")
    normalized = {}
    for name, item in results.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(item, dict):
            raise ValueError("capability results must map names to status objects")
        if not isinstance(item.get("status"), str) or item["status"] not in _STATUS:
            raise ValueError(f"invalid capability status: {name}")
        normalized[name] = {"status": item["status"]}
    return normalized


def read_capability_results(skill_or_meta) -> dict[str, dict]:
    """读取简明状态，兼容旧版详细字段；缺失或损坏的扩展返回空映射。"""
    meta = getattr(skill_or_meta, "meta", skill_or_meta)
    metadata = meta if isinstance(meta, dict) else getattr(meta, "metadata", {})
    if not isinstance(metadata, dict) or not metadata.get(_KEY):
        return {}
    try:
        return _normalize(json.loads(metadata[_KEY]))
    except (TypeError, ValueError):
        return {}


def _cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def annotate_package(package_dir: str | Path, capability_results: dict[str, dict]) -> None:
    """只注解传入的发布副本，保留其余元数据和正文；普通包校验仍由调用方完成。"""
    results = _normalize(capability_results)
    entry = Path(package_dir) / "SKILL.md"
    text = entry.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ValueError("capability annotation requires standard SKILL.md frontmatter")
    frontmatter = yaml.safe_load(match[1])
    if not isinstance(frontmatter, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    metadata = frontmatter.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md metadata must be a mapping")
    body = _BLOCK.sub("", text[match.end():])
    if results:
        metadata[_KEY] = json.dumps(
            results, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows = [
            _START, "## 能力验收状态", "",
            "| 能力 | 可用性 |",
            "| --- | --- |",
        ]
        for name, item in sorted(results.items()):
            rows.append(f"| {_cell(name)} | {_STATUS[item['status']]} |")
        body += "\n\n" + "\n".join([*rows, _END]) + "\n"
    else:
        metadata.pop(_KEY, None)
    frontmatter["metadata"] = metadata
    entry.write_text("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
                     + "---\n" + body, encoding="utf-8")
