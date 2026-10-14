"""工作区按需创建目录，抽取日志压缩后仍能恢复与去重。"""

import hashlib
import json
from pathlib import Path

import pytest

from searchos.harness.middleware.extraction.core.store import _ObservationJournal
from searchos.socm.workspace import WorkspaceManager


def item(number):
    return {"content_hash": hashlib.sha256(str(number).encode()).hexdigest(), "content": str(number)}


def test_workspace_creates_only_directories_that_receive_data(tmp_path):
    workspace = WorkspaceManager(tmp_path, "session")
    root = workspace.create()
    assert workspace.create() == root
    assert workspace.read_page("missing") == ""
    assert workspace.read_page_meta("missing") is None
    assert list(root.iterdir()) == []

    workspace.write_output("report.md", "answer")
    workspace.write_intermediate("notes.md", "notes")
    workspace.write_evidence("worker", "source.md", "evidence")
    workspace.write_page("page", "https://example.com", "source", title="Example")
    assert workspace.read_page("page") == "source"
    assert workspace.read_page_meta("page")["title"] == "Example"
    assert (root / "output/report.md").read_text() == "answer"
    assert (root / "intermediate/notes.md").read_text() == "notes"
    assert (root / "evidence/worker/source.md").read_text() == "evidence"
    assert {path.name for path in root.iterdir()} == {"output", "intermediate", "evidence", "pages"}


def test_completed_observations_use_one_index_and_keep_failed_work(tmp_path):
    journal = _ObservationJournal(tmp_path, "worker")
    assert journal.load() == []
    assert not journal.path.exists()
    for number in range(100):
        journal.write(item(number), "pending")
        journal.write(item(number), "done")
    journal.write(item(100), "failed", error="retry")
    assert len(list(journal.path.iterdir())) == 2
    restored = _ObservationJournal(tmp_path, "worker").load()
    assert len([record for record in restored if record["status"] == "done"]) == 100
    failed = next(record for record in restored if record["status"] == "failed")
    assert failed["item"] == item(100)
    assert failed["error"] == "retry"


def legacy_journal(root):
    journal = _ObservationJournal(root, "worker")
    journal.path.mkdir(parents=True)
    for number, status in enumerate(("done", "pending", "failed")):
        record = {"content_hash": item(number)["content_hash"], "status": status}
        if status != "done":
            record["item"] = item(number)
        (journal.path / f'{item(number)["content_hash"]}.json').write_text(json.dumps(record))
    return journal


def test_legacy_journal_compacts_completed_records_without_losing_pending(tmp_path):
    journal = legacy_journal(tmp_path)
    restored = journal.load()
    assert {record["status"] for record in restored} == {"done", "pending", "failed"}
    assert not (journal.path / f'{item(0)["content_hash"]}.json').exists()
    assert (journal.path / "completed.json").is_file()
    assert len(list(journal.path.iterdir())) == 3
    assert _ObservationJournal(tmp_path, "worker").load() == restored


def test_failed_compaction_keeps_legacy_records_for_retry(tmp_path, monkeypatch):
    journal = legacy_journal(tmp_path)
    before = {p.name: p.read_bytes() for p in journal.path.iterdir()}
    with monkeypatch.context() as patch:
        def fail_replace(*args):
            raise OSError("publication failed")
        patch.setattr("searchos.harness.middleware.extraction.core.store.os.replace", fail_replace)
        with pytest.raises(OSError, match="publication failed"):
            journal.load()
    assert {p.name: p.read_bytes() for p in journal.path.iterdir()} == before
    assert len(journal.load()) == 3


def test_completed_index_wins_after_crash_before_pending_file_removal(tmp_path, monkeypatch):
    journal = _ObservationJournal(tmp_path, "worker")
    pending = item(1)
    journal.write(pending, "pending")
    original_unlink = Path.unlink
    pending_path = journal.path / f'{pending["content_hash"]}.json'
    with monkeypatch.context() as patch:
        def fail_unlink(path, *args, **kwargs):
            if path == pending_path:
                raise OSError("crash after publication")
            return original_unlink(path, *args, **kwargs)
        patch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(OSError, match="crash after publication"):
            journal.write(pending, "done")
        journal.write(pending, "failed", error="must not resurrect completed work")
    assert pending_path.exists()
    recovered = _ObservationJournal(tmp_path, "worker")
    assert recovered.load() == [{"content_hash": pending["content_hash"], "status": "done"}]
    assert not pending_path.exists()


@pytest.mark.parametrize("filename, content", [("broken.json", "{"), ("completed.json", '{"version": 1}')])
def test_corrupt_journal_never_removes_legacy_records(tmp_path, filename, content):
    journal = legacy_journal(tmp_path)
    (journal.path / filename).write_text(content)
    before = {p.name: p.read_bytes() for p in journal.path.iterdir()}
    with pytest.raises(ValueError):
        journal.load()
    assert {p.name: p.read_bytes() for p in journal.path.iterdir()} == before
