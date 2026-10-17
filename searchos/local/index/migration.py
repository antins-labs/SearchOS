"""Conservative migration of verifiable legacy local-document indexes."""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from searchos.local.models import PipelineOptions
from searchos.local.pipeline import DocumentRecapPipeline
from searchos.local.storage_io import atomic_write_text, file_sha256

_RECORD_START = "## 文件记录\n\n"
_BODY_START = "\n\n## 正文\n\n"
_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^sha256:([0-9a-f]{64})$")
_SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".pdf"})


@dataclass(frozen=True, slots=True)
class MigrationItem:
    document_id: str
    status: str
    source: str = ""
    message: str = ""


class _SourceChangedError(Exception):
    pass


def _legacy_record(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8")
    start = raw.find(_RECORD_START)
    if start < 0:
        raise ValueError("缺少固定文件记录区")
    start += len(_RECORD_START)
    end = raw.find(_BODY_START, start)
    if end < 0:
        raise ValueError("缺少固定正文区")
    output: dict[str, str] = {}
    for line in raw[start:end].splitlines():
        if not line.startswith("- ") or "：" not in line:
            raise ValueError("文件记录区包含未知行")
        key, value = line[2:].split("：", 1)
        if key in output:
            raise ValueError(f"文件记录字段重复：{key}")
        output[key] = value.strip()
    required = {"文档 ID", "原文绝对路径", "授权根目录", "内容哈希"}
    missing = required - set(output)
    if missing:
        raise ValueError("文件记录缺少字段：" + ", ".join(sorted(missing)))
    return output


def _inspect_candidate(
    path: Path,
    authorized_roots: tuple[Path, ...],
) -> tuple[Path, Path, str]:
    record = _legacy_record(path)
    document_id = record["文档 ID"]
    if not _DOCUMENT_ID.fullmatch(document_id) or document_id != path.stem:
        raise ValueError("文档 ID 无效或与缓存文件名不一致")
    source = Path(record["原文绝对路径"]).expanduser().resolve()
    source_root = Path(record["授权根目录"]).expanduser().resolve()
    if source_root not in authorized_roots:
        raise PermissionError("记录的授权根目录未由本次迁移显式授权")
    try:
        source.relative_to(source_root)
    except ValueError as exc:
        raise PermissionError("原文超出记录的授权根目录") from exc
    if source.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise NotImplementedError(f"旧索引迁移不支持 {source.suffix or '(无扩展名)'}")
    if not source.is_file():
        raise FileNotFoundError("原文当前不可用")
    match = _SHA256.fullmatch(record["内容哈希"])
    if match is None:
        raise ValueError("内容哈希不是有效 SHA-256")
    if file_sha256(source) != match.group(1):
        raise _SourceChangedError("原文版本与旧索引不一致")
    return source, source_root, document_id


async def migrate_legacy_index(
    index_root: Path,
    *,
    authorized_roots: list[Path],
) -> list[MigrationItem]:
    root = index_root.expanduser().resolve()
    roots = tuple(item.expanduser().resolve() for item in authorized_roots)
    pipeline = DocumentRecapPipeline(output_root=root)
    output: list[MigrationItem] = []
    for path in sorted((root / "texts").glob("*.md")):
        document_id = path.stem
        try:
            source, source_root, document_id = _inspect_candidate(path, roots)
            await pipeline.process(
                source,
                source_root=source_root,
                document_id=document_id,
                options=PipelineOptions(
                    allow_remote=False,
                    build_catalog=False,
                    force=True,
                ),
            )
        except PermissionError as exc:
            output.append(MigrationItem(document_id, "unauthorized", message=str(exc)))
        except FileNotFoundError as exc:
            output.append(MigrationItem(document_id, "unavailable", message=str(exc)))
        except NotImplementedError as exc:
            output.append(MigrationItem(document_id, "unsupported", message=str(exc)))
        except _SourceChangedError as exc:
            output.append(MigrationItem(document_id, "source_changed", message=str(exc)))
        except Exception as exc:  # noqa: BLE001
            output.append(MigrationItem(document_id, "invalid", message=str(exc)))
        else:
            output.append(MigrationItem(document_id, "migrated", source=str(source)))
    return output


def write_migration_report(path: Path, items: list[MigrationItem]) -> None:
    lines = [
        "# 旧本地索引迁移清单",
        "",
        "| document_id | 状态 | 来源 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for item in items:
        values = [item.document_id, item.status, item.source, item.message]
        escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    atomic_write_text(path, "\n".join(lines).rstrip() + "\n")


async def _run() -> int:
    parser = argparse.ArgumentParser(description="迁移可验证来源版本的旧本地文档索引")
    parser.add_argument("index_root", type=Path)
    parser.add_argument(
        "--authorized-root",
        type=Path,
        action="append",
        required=True,
        help="本次迁移允许访问的原文根目录；可重复提供",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    items = await migrate_legacy_index(
        args.index_root,
        authorized_roots=args.authorized_root,
    )
    report = args.report or args.index_root / "migration-report.md"
    write_migration_report(report, items)
    for item in items:
        print(f"{item.status}: {item.document_id} {item.message}".rstrip())
    print(f"报告：{report}")
    return 0 if all(item.status == "migrated" for item in items) else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()


__all__ = ["MigrationItem", "migrate_legacy_index", "write_migration_report"]
