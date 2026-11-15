"""Exec 的不可变输入与产物；文本结果沿用原有保存页面。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path
from uuid import uuid4

from searchos.tools.search_state import _current_task_id_var, get_workspace
from searchos.tools.simple_browser.pages import PageContents


def root() -> Path:
    workspace = get_workspace()
    if workspace is None:
        raise ValueError("reading references require a task workspace")
    directory = workspace.path / "source_refs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save(content: bytes, *, source: str, media_type: str, metadata=None, name="") -> str:
    metadata = dict(metadata or {})
    payload = {
        "source": source,
        "media_type": media_type,
        "metadata": metadata,
        "name": name,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    identity = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    ref = "ref_" + identity
    directory = root()
    suffix = mimetypes.guess_extension(media_type) or ".bin"
    payload["file"] = ref + ".content" + suffix
    destination = directory / payload["file"]
    if not destination.exists():
        temporary = directory / ("." + uuid4().hex)
        temporary.write_bytes(content)
        temporary.replace(destination)
    manifest = directory / (ref + ".json")
    if not manifest.exists():
        temporary = directory / ("." + uuid4().hex)
        temporary.write_text(json.dumps(payload, ensure_ascii=False))
        temporary.replace(manifest)
    return ref


def read(ref: str) -> tuple[dict, Path]:
    if not re.fullmatch(r"ref_[a-f0-9]{64}", ref):
        from searchos.tools.simple_browser.session import _get_browser, _read_page_from_disk

        source = _get_browser().get_page_by_url(ref) or _read_page_from_disk(ref)
        if source is None:
            raise ValueError("use a returned ref or an already opened page URL")
        ref = save_page(source)
    directory = root()
    manifest = directory / (ref + ".json")
    if manifest.is_symlink():
        raise ValueError("invalid reference manifest")
    payload = json.loads(manifest.read_text())
    from searchos.skills.runtime.paths import resolve_resource_file

    path = resolve_resource_file(directory, payload["file"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != payload["sha256"]:
        raise ValueError("saved source content changed")
    metadata = payload.get("metadata", {})
    owner = metadata.get("producer_task")
    task = _current_task_id_var.get()
    from searchos.tools.skills.execution import _context

    if owner and owner not in {task, _context()[1]}:
        raise ValueError("execution artifact belongs to another task")
    from searchos.tools.simple_browser.session import is_url_allowed

    if payload["source"].startswith(("http://", "https://")) and not is_url_allowed(
        payload["source"]
    ):
        raise ValueError("source is excluded for this task")
    return payload, path


def save_page(page: PageContents) -> str:
    return save(
        page.text.encode(),
        source=page.source_url or page.url,
        media_type="text/plain",
        name=page.title,
        metadata={**page.metadata, "urls": page.urls, "view_url": page.url},
    )


def publish(ref: str) -> str | None:
    """将文本产物注册为原 open/find 可读取的页面。"""
    payload, path = read(ref)
    if (
        not payload["media_type"].startswith("text/")
        and payload["media_type"] != "application/json"
    ):
        return None
    metadata = dict(payload.get("metadata", {}))
    url = f"skill://exec/{metadata['execution_id']}/{ref}"
    from searchos.tools.simple_browser.session import _persist_page

    _persist_page(url, PageContents(
        url=url,
        title=payload["name"],
        text=path.read_text(errors="replace"),
        metadata=metadata,
    ))
    return url


def save_artifacts(
    result: dict, execution_directory: Path, *, task_id: str, inputs=()
) -> list[dict]:
    from searchos.skills.runtime.paths import resolve_resource_file

    saved = []
    for item in result.get("artifacts", []):
        path = resolve_resource_file(execution_directory / "artifacts", item["path"])
        media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        ref = save(
            path.read_bytes(),
            source=f"exec://{result['execution_id']}/{item['path']}",
            media_type=media,
            name=item["path"],
            metadata={
                "producer_task": task_id,
                "execution_id": result["execution_id"],
                "input_refs": list(inputs),
                "kind": "execution_result",
                "evidence_eligible": False,
            },
        )
        item = {"ref": ref, "name": item["path"], "media_type": media}
        page_url = publish(ref)
        if page_url:
            item["page_url"] = page_url
        saved.append(item)
    return saved


def save_child_results(executions: list[dict], parent_directory: Path, *, task_id: str) -> dict:
    """保存子调用索引，复用技能结果页面并补齐中断时的输出读取入口。"""
    entries = []
    for result in executions:
        entry = {key: result[key] for key in (
            "execution_id", "skill", "argv", "status", "exit_code", "error", "index_page_url",
        ) if key in result}
        entry["streams"] = {}
        for stream in ("stdout", "stderr"):
            log = parent_directory.parent / result["execution_id"] / f"{stream}.log"
            metadata = result.get("streams", {}).get(stream, {})
            if not log.is_file() and stream not in result:
                continue
            text = log.read_bytes().decode("utf-8", errors="replace") if log.is_file() else str(result[stream])
            total = len(text) if log.is_file() or not metadata.get("preview_truncated") else None
            entry[stream] = text[:512]
            info = {
                "shown_chars": len(entry[stream]), "total_chars": total,
                "truncated": total is None or len(entry[stream]) < total,
            }
            if metadata.get("log_truncated"):
                info["log_truncated"] = True
            page_url = next((page["url"] for page in result.get("pages", [])
                             if page["url"].endswith("/" + stream)), None)
            if not page_url and text:
                ref = save(text.encode(), source=f"exec://{result['execution_id']}/{stream}",
                           media_type="text/plain", name=stream, metadata={
                               "execution_id": result["execution_id"], "producer_task": task_id,
                               "kind": "execution_result", "evidence_eligible": False,
                           })
                page_url = publish(ref)
            if page_url:
                info["page_url"] = page_url
            entry["streams"][stream] = info
        entries.append(entry)
    parent_id = parent_directory.name
    ref = save(json.dumps({"executions": entries}, ensure_ascii=False, indent=2).encode(),
               source=f"exec://{parent_id}/child_results", media_type="application/json",
               name="Skill execution results", metadata={
                   "execution_id": parent_id, "producer_task": task_id,
                   "kind": "execution_index", "evidence_eligible": False,
               })
    return {"total": len(entries), "page_url": publish(ref), "items": entries}
