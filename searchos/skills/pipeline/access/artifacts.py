"""产物存储：完整输出、分页读取、脱敏和构建事件。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

MAX_RECEIPT_BYTES = 24_000


_INDEX_CHARS = 65_536


def json_fits(value: Any, budget: int = MAX_RECEIPT_BYTES) -> bool:
    """按实际 JSON 编码大小检查回执。"""
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=False, default=str).iterencode(value):
        size += len(chunk.encode("utf-8"))
        if size > budget:
            return False
    return True


def private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("tool result directory must not be a symbolic link")
    return path.resolve()


def _identity(handle: TextIO) -> tuple[int, ...]:
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("read_file requires a regular text file")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@dataclass(frozen=True)
class _Snapshot:
    path: Path
    total_chars: int
    total_bytes: int
    positions: tuple[int, ...]


class TextFilePager:
    """首次脱敏后复用不可变副本，后续只读取所需窗口。"""

    def __init__(self, root: Path, clean: Callable[[Any], Any]):
        self.root, self.clean = root, clean
        self._snapshots: dict[tuple[int, ...], _Snapshot] = {}

    def _snapshot(self, handle: TextIO) -> _Snapshot:
        identity = _identity(handle)
        if cached := self._snapshots.get(identity):
            return cached
        handle.seek(0)
        text = self.clean(handle.read())
        if not isinstance(text, str):
            raise ValueError("text cleaner must return text")
        path = private_directory(self.root) / f"{uuid4().hex}.txt"
        positions, size = [], 0
        with path.open("xb") as output:
            path.chmod(0o600)
            for start in range(0, len(text), _INDEX_CHARS):
                positions.append(size)
                data = text[start : start + _INDEX_CHARS].encode("utf-8")
                output.write(data)
                size += len(data)
        snapshot = _Snapshot(path, len(text), size, tuple(positions or [0]))
        self._snapshots[identity] = snapshot
        with path.open(encoding="utf-8") as saved:
            self._snapshots[_identity(saved)] = snapshot
        return snapshot

    def save(self, source: Path) -> dict[str, Any]:
        """把宿主日志转为持久、可分页的脱敏文件。"""
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r", encoding="utf-8", errors="replace") as handle:
            snapshot = self._snapshot(handle)
        return {
            "path": str(snapshot.path),
            "total_chars": snapshot.total_chars,
            "total_bytes": snapshot.total_bytes,
        }

    def read(self, handle: TextIO, *, path: Path, offset: int = 0,
             limit: int = 16_000) -> dict[str, Any]:
        snapshot = self._snapshot(handle)
        start, count = max(0, offset), min(24_000, max(1, limit))
        content = ""
        if start < snapshot.total_chars:
            block = min(start // _INDEX_CHARS, len(snapshot.positions) - 1)
            descriptor = os.open(snapshot.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as saved:
                saved.seek(snapshot.positions[block])
                skip = start - block * _INDEX_CHARS
                content = saved.read(skip + count)[skip:]

        def receipt(length):
            end = start + length
            more = end < snapshot.total_chars
            return {
                "path": str(path), "content": content[:length],
                "total_chars": snapshot.total_chars, "truncated": more,
                "next_offset": end if more else None,
            }

        if json_fits(result := receipt(len(content))):
            return result
        low, high = 0, len(content)
        while low < high:
            middle = (low + high + 1) // 2
            if json_fits(receipt(middle)):
                low = middle
            else:
                high = middle - 1
        return receipt(low)


PREVIEW_CHARS = 8000


_EXECUTION_STATUS_FIELDS = (
    "execution_id",
    "status",
    "started",
    "exit_code",
    "timed_out",
    "cancelled",
    "auth_required",
    "external_blocked",
    "next_action",
    "cached_external_block",
    "truncated",
    "timeout_phase",
    "error",
    "cleanup_error",
    "record_error",
    "artifact_error",
    "stdout_capture_error",
    "stderr_capture_error",
)


_STATUS_TEXT_CHARS = 1000


class ToolResultStore:
    def __init__(self, root: Path, *, clean: Callable[[Any], Any] | None = None):
        self.root = root
        self.clean = clean or (lambda value: value)
        self._text_files = TextFilePager(root, self.clean)

    def save_text_file(self, source: Path) -> dict[str, Any]:
        return self._text_files.save(Path(source))

    def read_text_file(self, handle, *, path: Path, offset: int = 0,
                       limit: int = 16000) -> dict[str, Any]:
        return self._text_files.read(handle, path=path, offset=offset, limit=limit)

    @staticmethod
    def _compact_receipt(value, result_file, saved_files):
        """超限回执只展示必要状态，完整业务值保存在文件中。"""
        receipt = {
            "display_summary": True,
            "result_file": str(result_file),
            "value_type": "object" if isinstance(value, dict) else
                          "array" if isinstance(value, (list, tuple)) else type(value).__name__,
        }
        if isinstance(value, dict):
            receipt["field_count"] = len(value)
            for key in (*_EXECUTION_STATUS_FIELDS, "valid", "package_valid", "stage",
                        "examples", "observation_id", "content_source", "live_evidence",
                        "source_url", "validation_status"):
                item = value.get(key)
                if isinstance(item, (str, bool, int, float)) or key in value and item is None:
                    receipt[key] = item[:_STATUS_TEXT_CHARS] if isinstance(item, str) else item
            if isinstance(value.get("case_results"), list):
                receipt["case_count"] = len(value["case_results"])
            for key in ("repair_budget", "package_files", "function_index_file", "next_actions",
                        "pending_regressions", "capability_results", "repair_attempts", "validation_scope", "recovery",
                        "parameter_comparisons"):
                if key in value and json_fits({**receipt, key: value[key]}, MAX_RECEIPT_BYTES - 2000):
                    receipt[key] = value[key]
                elif key in {'next_actions', 'pending_regressions'} and isinstance(value.get(key), list):
                    receipt[key + '_count'] = len(value[key])
                    receipt[key] = []
                    for item in value[key]:
                        preview = dict(item)
                        for field in ('functions', 'regression_commands'):
                            if isinstance(preview.get(field), list):
                                preview[field + '_count'] = len(preview[field])
                                preview[field] = preview[field][:2]
                        if json_fits({**receipt, key: [*receipt[key], preview]}, MAX_RECEIPT_BYTES - 4000):
                            receipt[key].append(preview)
                        else:
                            break
                    receipt[key + '_continued_in'] = str(result_file)
        elif isinstance(value, (list, tuple)):
            receipt["item_count"] = len(value)
        elif isinstance(value, str):
            receipt["total_chars"] = len(value)
        if saved_files:
            receipt["saved_files_count"] = len(saved_files)
            receipt["saved_files"] = saved_files[:4]
        if json_fits(receipt):
            return receipt
        minimal = {key: receipt[key] for key in ("display_summary", "result_file", "value_type")}
        for key, item in receipt.items():
            if json_fits({**minimal, key: item}):
                minimal[key] = item
        return minimal

    def present(self, result: Any) -> Any:
        """保存完整脱敏结果，按统一大小限制展示回执。"""
        value = self.clean(result)
        fields = []
        payload_summaries = []
        text_summaries = {}
        has_validation = False

        def status_value(item):
            if isinstance(item, str):
                return item[:_STATUS_TEXT_CHARS]
            if item is None or isinstance(item, (bool, int, float)):
                return item
            return type(item).__name__

        def save_text(pointer, item):
            if item:
                fields.append((pointer, item))

        def preview(item, pointer, field_name="", *, validation_case=False):
            nonlocal has_validation
            if isinstance(item, str) and len(item) > PREVIEW_CHARS:
                save_text(pointer, item)
                return item[:PREVIEW_CHARS]
            if isinstance(item, dict):
                # 宿主验收先按结构压缩，最终再检查整个回执的大小。
                validation = (
                    isinstance(item.get("case_results"), list)
                    and isinstance(item.get("valid"), bool)
                    and isinstance(item.get("package_valid"), bool)
                )
                has_validation |= validation
                shown = {}
                for key, child in item.items():
                    location = pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")
                    if (validation_case and key in {"payload", "execution", "output_text"}
                            and isinstance(child, dict) and child.get("display_summary") is True
                            and isinstance(child.get("result_file"), str)):
                        shown[key] = child
                    elif validation_case and key == "payload":
                        summary = {"display_summary": True, "field": location}
                        if isinstance(child, dict):
                            summary.update(value_type="object", field_count=len(child))
                            if isinstance(child.get("records"), list):
                                summary["records_count"] = len(child["records"])
                        elif isinstance(child, list):
                            summary.update(value_type="array", item_count=len(child))
                        else:
                            summary["value_type"] = (
                                "null" if child is None else type(child).__name__
                            )
                        payload_summaries.append(summary)
                        shown[key] = summary
                    elif validation_case and key == "execution":
                        summary = {"display_summary": True, "field": location}
                        payload_summaries.append(summary)
                        if isinstance(child, dict):
                            summary["field_count"] = len(child)
                            for name in _EXECUTION_STATUS_FIELDS:
                                if name in child:
                                    summary[name] = status_value(child[name])
                            for name in ("stdout", "stderr"):
                                text = child.get(name)
                                if isinstance(text, str):
                                    save_text(location + "/" + name, text)
                        else:
                            summary["value_type"] = (
                                "null" if child is None else type(child).__name__
                            )
                        shown[key] = summary
                    elif validation_case and key == "output_text":
                        summary = {
                            "display_summary": True,
                            "field": location,
                            "value_type": (
                                "text" if isinstance(child, str) else type(child).__name__
                            ),
                        }
                        if isinstance(child, str):
                            summary["total_chars"] = len(child)
                            save_text(location, child)
                        text_summaries[location] = summary
                        shown[key] = summary
                    elif validation and key == "case_results":
                        shown[key] = [
                            preview(case, f"{location}/{index}", validation_case=True)
                            for index, case in enumerate(child)
                        ]
                    else:
                        shown[key] = preview(child, location, str(key))
                return shown
            if isinstance(item, (list, tuple)):
                return [
                    preview(child, f"{pointer}/{index}", field_name)
                    for index, child in enumerate(item)
                ]
            return item

        shown = preview(value, "")
        if not fields and not has_validation and json_fits(shown):
            return value
        result_id = uuid4().hex
        root = private_directory(self.root)
        result_file = root / f"{result_id}.json"
        with result_file.open("x", encoding="utf-8") as handle:
            result_file.chmod(0o600)
            json.dump(value, handle, ensure_ascii=False, default=str)
        for summary in [*payload_summaries, *text_summaries.values()]:
            summary["result_file"] = str(result_file)
        saved_files = []
        for pointer, text in fields:
            digest = hashlib.sha256(pointer.encode()).hexdigest()[:20]
            path = root / f"{result_id}-{digest}.txt"
            with path.open("x", encoding="utf-8") as handle:
                path.chmod(0o600)
                handle.write(text)
            saved_files.append({"field": pointer, "path": str(path), "total_chars": len(text)})
            if pointer in text_summaries:
                text_summaries[pointer]["saved_file"] = str(path)
        receipt = {"saved_files": saved_files, "result_file": str(result_file)}
        if not isinstance(shown, dict):
            return self._compact_receipt(value, result_file, saved_files)
        if set(receipt).intersection(shown):
            # 同名业务字段仍保持原值；宿主回执使用未占用的旁路字段。
            key = "_saved_result"
            while key in shown:
                key = "_" + key
            shown[key] = receipt
        else:
            shown.update(receipt)
        return shown if json_fits(shown) else self._compact_receipt(value, result_file, saved_files)


LOG_STRING_LIMIT = 12000


class BuildRecord:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.secrets = [value for key, value in os.environ.items()
                        if re.search(r'KEY|TOKEN|PASSWORD|SECRET|COOKIE', key, re.I) and len(value) >= 8]

    def clean(self, value, *, max_string_chars: int | None = None):
        """递归脱敏；研究状态保留全文，日志调用显式指定字符串上限。"""
        from searchos.skills.runtime.browser_session import current_session, clean_private
        session = current_session.get()
        value = clean_private(value, [*self.secrets, *(session.secrets if session else ())])
        if isinstance(value, dict):
            return {key: ('[REDACTED]' if re.search(r'^(authorization|cookie|set-cookie|password|api[_-]?key|access_token|auth_token|secret)$', key, re.I)
                          else self.clean(item, max_string_chars=max_string_chars)) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(item, max_string_chars=max_string_chars) for item in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            value = re.sub(r'(?i)(Bearer\s+)[\w.\-]+', r'\1[REDACTED]', value)
            if max_string_chars is not None and len(value) > max_string_chars:
                return value[:max_string_chars] + '…[truncated]'
            return value
        return value

    def event(self, event, **data):
        path = self.root / 'events.jsonl'
        with path.open('a', encoding='utf-8') as handle:
            path.chmod(0o600)
            handle.write(json.dumps(self.clean(dict(event=event, at=datetime.now(timezone.utc).isoformat(), **data),
                                               max_string_chars=LOG_STRING_LIMIT), ensure_ascii=False) + '\n')

    def summary(self, diagnostics):
        temporary = self.root / 'builder.tmp'
        temporary.write_text(json.dumps(self.clean(diagnostics, max_string_chars=LOG_STRING_LIMIT),
                                        ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.chmod(0o600)
        temporary.replace(self.root / 'builder.json')
