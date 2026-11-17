"""Topic/document catalog management and WebUI graph projection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from searchos.local import messages
from searchos.local.catalog import (
    CatalogDocument,
    CatalogMarkdownStore,
    Subindex,
    make_subindex_id,
)
from searchos.local.models import ProcessingStatus
from searchos.local.storage.files import advisory_lock
from searchos.local.storage.sources import SourceRegistry

if TYPE_CHECKING:
    from searchos.local.library.service import LocalLibraryService


def clean_label(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > 120:
        raise ValueError(messages.NAME_INVALID)
    return cleaned


def edit_document(
    service: LocalLibraryService,
    library_id: str,
    document_id: str,
    name: str,
) -> dict[str, Any]:
    name = clean_label(name)
    root = Path(service.get_library(library_id).index_root)
    store = CatalogMarkdownStore(root)
    with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
        service.get_document(library_id, document_id)
        catalog, state = store.load(), store.read_state()
        affected = set()
        for key, topic in catalog.items():
            if document_id in topic.documents:
                topic.documents[document_id] = replace(topic.documents[document_id], name=name)
                affected.add(key)
        state["display_names"][document_id] = name
        if document_id not in state["manual_display_names"]:
            state["manual_display_names"].append(document_id)
        store.mark_pending(catalog, affected, state)
        store.write_state(state)
        store.write(catalog)
    return service.library_graph(library_id)


def edit_topic(
    service: LocalLibraryService,
    library_id: str,
    title: str,
    summary: str = "",
    subindex_id: str | None = None,
) -> dict[str, Any]:
    title = clean_label(title)
    root = Path(service.get_library(library_id).index_root)
    store = CatalogMarkdownStore(root)
    with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
        SourceRegistry(root).ensure_active()
        catalog, state = store.load(), store.read_state()
        if subindex_id is not None and subindex_id not in catalog:
            raise KeyError(messages.TOPIC_NOT_FOUND)
        if any(
            t.title.casefold() == title.casefold() and key != subindex_id
            for key, t in catalog.items()
        ):
            raise ValueError(messages.TOPIC_EXISTS)
        key = subindex_id or make_subindex_id(title, catalog)
        topic = catalog.setdefault(key, Subindex(key, title))
        topic.title, topic.summary = title, " ".join(summary.split())
        for field in ("manual_topics", "manual_topic_summaries"):
            if key not in state[field]:
                state[field].append(key)
        store.mark_pending(catalog, {key}, state)
        store.write_state(state)
        store.write(catalog)
    return service.library_graph(library_id)


def delete_topic(
    service: LocalLibraryService,
    library_id: str,
    subindex_id: str,
) -> dict[str, Any]:
    root = Path(service.get_library(library_id).index_root)
    store = CatalogMarkdownStore(root)
    with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
        SourceRegistry(root).ensure_active()
        catalog, state = store.load(), store.read_state()
        if subindex_id not in catalog:
            raise KeyError(messages.TOPIC_NOT_FOUND)
        removed = catalog.pop(subindex_id)
        state["manual_documents"] = sorted(
            set(state["manual_documents"]) | set(removed.documents)
        )
        for field in ("manual_topics", "manual_topic_summaries"):
            state[field] = [key for key in state[field] if key != subindex_id]
        state["topics"].pop(subindex_id, None)
        store.write_state(state)
        store.write(catalog)
    registry = SourceRegistry(root)
    for document_id in removed.documents:
        with advisory_lock(root / ".locks" / f"publish-{document_id}.lock"):
            with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
                still_classified = any(
                    document_id in topic.documents for topic in store.load().values()
                )
            if still_classified:
                continue
            try:
                record = registry.read(document_id)
            except FileNotFoundError:
                continue
            if record.catalog_status != ProcessingStatus.PARTIAL:
                registry.write(
                    record.model_copy(update={"catalog_status": ProcessingStatus.PARTIAL})
                )
    return service.library_graph(library_id)


def set_document_topics(
    service: LocalLibraryService,
    library_id: str,
    document_id: str,
    subindex_ids: list[str],
) -> dict[str, Any]:
    selected = list(dict.fromkeys(subindex_ids))
    if len(selected) > 3:
        raise ValueError(messages.TOPIC_LIMIT)
    library = service.get_library(library_id)
    root = Path(library.index_root)
    store = CatalogMarkdownStore(root)
    with advisory_lock(root / ".locks" / f"publish-{document_id}.lock"):
        with advisory_lock(root / ".locks" / "catalog-transaction.lock"):
            _, record, blocks = service._document_blocks(library_id, document_id)
            catalog = store.load()
            state = store.read_state()
            old_ids = {key for key, topic in catalog.items() if document_id in topic.documents}
            unknown = [subindex_id for subindex_id in selected if subindex_id not in catalog]
            if unknown:
                raise KeyError(messages.TOPICS_NOT_FOUND.format(topics=", ".join(unknown)))
            existing_record = next(
                (
                    item.documents[document_id]
                    for item in catalog.values()
                    if document_id in item.documents
                ),
                None,
            )
            catalog_document = CatalogDocument(
                document_id=document_id,
                name=state["display_names"].get(document_id)
                or (existing_record.name if existing_record else Path(record.relative_path).name),
                summary=(
                    record.recap.summary.strip()
                    or (existing_record.summary if existing_record else messages.RECAP_PENDING)
                ),
                character_count=sum(len(block.text) for block in blocks if block.is_primary),
            )
            for topic in catalog.values():
                topic.documents.pop(document_id, None)
            for subindex_id in selected:
                catalog[subindex_id].documents[document_id] = catalog_document
            if document_id not in state["manual_documents"]:
                state["manual_documents"].append(document_id)
            state["display_names"][document_id] = catalog_document.name
            store.mark_pending(catalog, old_ids | set(selected), state)
            store.write(catalog)
            store.write_state(state)

            catalog_status = (
                ProcessingStatus.READY
                if selected and record.recap_status == ProcessingStatus.READY
                else ProcessingStatus.PARTIAL
            )
            SourceRegistry(root).write(
                record.model_copy(update={"catalog_status": catalog_status})
            )
    return service.library_graph(library_id)


def library_graph(service: LocalLibraryService, library_id: str) -> dict[str, Any]:
    library = service.get_library(library_id)
    documents = service.list_documents(library_id)
    documents_by_id = {item["document_id"]: item for item in documents}
    catalog_store = CatalogMarkdownStore(Path(library.index_root))
    catalog = catalog_store.load()
    catalog_state = catalog_store.read_state()
    root_id = f"index:{library_id}"
    nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "node_type": "index",
            "label": library.name,
            "summary": "",
            "character_count": 0,
        }
    ]
    edges: list[dict[str, str]] = []
    catalog_documents: dict[str, Any] = {}

    for topic in sorted(catalog.values(), key=lambda item: item.title.casefold()):
        current_documents = [
            item for item in topic.documents.values() if item.document_id in documents_by_id
        ]
        if not current_documents and topic.subindex_id not in catalog_state["manual_topics"]:
            continue
        topic_id = f"subindex:{topic.subindex_id}"
        nodes.append(
            {
                "id": topic_id,
                "node_type": "subindex",
                "subindex_id": topic.subindex_id,
                "label": topic.title,
                "summary": topic.summary,
                "character_count": sum(item.character_count for item in current_documents),
                "document_count": len(current_documents),
                "recap_status": catalog_state["topics"]
                .get(topic.subindex_id, {})
                .get("status", "ready"),
                "recap_error": catalog_state["topics"]
                .get(topic.subindex_id, {})
                .get("error", ""),
            }
        )
        edges.append({"source": root_id, "target": topic_id, "relation": "contains"})
        for item in sorted(current_documents, key=lambda value: value.name.casefold()):
            catalog_documents.setdefault(item.document_id, item)
            edges.append(
                {
                    "source": topic_id,
                    "target": f"document:{item.document_id}",
                    "relation": "classifies",
                }
            )

    for document in documents:
        catalog_document = catalog_documents.get(document["document_id"])
        document_id = f"document:{document['document_id']}"
        nodes.append(
            {
                "id": document_id,
                "node_type": "document",
                "document_id": document["document_id"],
                "label": catalog_state["display_names"].get(document["document_id"])
                or (catalog_document.name if catalog_document else document["name"]),
                "original_name": document["name"],
                "summary": (
                    catalog_document.summary
                    if catalog_document
                    else document.get("summary") or messages.CATALOG_PENDING
                ),
                "character_count": catalog_document.character_count if catalog_document else 0,
                "document_kind": document["kind"],
                "size_bytes": document["size_bytes"],
                "searchable": document["searchable"],
                "parse_status": document["parse_status"],
                "recap_status": document["recap_status"],
                "catalog_status": document["catalog_status"],
                "source_revision": document["source_revision"],
                "warnings": document["warnings"],
            }
        )
        if catalog_document is None:
            edges.append(
                {
                    "source": root_id,
                    "target": document_id,
                    "relation": "pending_catalog",
                }
            )

    topic_count = sum(node["node_type"] == "subindex" for node in nodes)
    nodes[0]["summary"] = messages.LIBRARY_COUNTS.format(
        topics=topic_count, documents=len(documents)
    )
    nodes[0]["character_count"] = sum(
        item.character_count for item in catalog_documents.values()
    )

    return {
        "library_id": library_id,
        "name": library.name,
        "nodes": nodes,
        "edges": edges,
    }
