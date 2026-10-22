"""Deployment data lifecycle and fail-closed entrypoint, without cloud credentials."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


entry = module("container_entry")
archive = module("data_archive")


@pytest.mark.parametrize("origin", ["", "http://host.test", "https://example.com",
                                    "https://searchos.example.com", "https://host.test/m",
                                    "https://user@host.test", "https://host.test:443",
                                    "https://host.test\nbad"])
def test_container_refuses_missing_or_invalid_remote_origin(tmp_path, monkeypatch, origin):
    monkeypatch.setenv("SF_PUBLIC_ORIGIN", origin)
    with pytest.raises(ValueError):
        entry.prepare(tmp_path / "data", tmp_path / "skills")
    assert not (tmp_path / "data").exists()


def test_initialize_and_restart_keeps_keys_settings_and_custom_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_PUBLIC_ORIGIN", "https://search.home.test")
    monkeypatch.delenv("SEARCHOS_TEST_KEY", raising=False)
    root, bundled = tmp_path / "data", tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "SKILL.md").write_text("bundled")
    old_mask = os.umask(0o077)
    try:
        entry.prepare(root, bundled)
        (root / "secrets.env").write_text("SEARCHOS_TEST_KEY=private-test-value\n")
        (root / "skills" / "SKILL.md").write_text("user edited")
        (root / "web_settings.json").write_text('{"personal":true}')
        entry.prepare(root, bundled)
        assert os.environ["SEARCHOS_TEST_KEY"] == "private-test-value"
        assert (root / "skills" / "SKILL.md").read_text() == "user edited"
        assert json.loads((root / "web_settings.json").read_text()) == {"personal": True}
        assert (root / "secrets.env").stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(old_mask)
        monkeypatch.delenv("SEARCHOS_TEST_KEY", raising=False)


def test_backup_restore_and_no_overwrite(tmp_path):
    root = tmp_path / "source"
    (root / "assistant").mkdir(parents=True)
    (root / "assistant/admin-token").write_text("secret")
    (root / "assistant/db.sqlite").write_bytes(b"database snapshot")
    (root / "secrets.env").write_text("KEY=private")
    (root / "run.sh").write_text("echo test")
    (root / "run.sh").chmod(0o755)
    os.link(root / "run.sh", root / "same-script.sh")
    buffer = io.BytesIO()
    archive.backup(root, buffer)
    buffer.seek(0)
    target = tmp_path / "restored"
    archive.restore(target, buffer)
    assert (target / "assistant/db.sqlite").read_bytes() == b"database snapshot"
    assert (target / "secrets.env").read_text() == "KEY=private"
    assert (target / "run.sh").stat().st_mode & 0o777 == 0o700
    assert (target / "same-script.sh").read_text() == "echo test"
    buffer.seek(0)
    with pytest.raises(ValueError, match="empty"):
        archive.restore(target, buffer)
    assert (target / "assistant/admin-token").read_text() == "secret"


@pytest.mark.parametrize("name,kind", [("data/../../escaped", "file"),
                                      ("/outside", "file"), ("data/link", "symlink")])
def test_restore_rejects_unsafe_archive_before_extracting(tmp_path, name, kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        member = tarfile.TarInfo(name)
        if kind == "symlink":
            member.type, member.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(member)
    stream.seek(0)
    with pytest.raises(ValueError):
        archive.restore(tmp_path / "target", stream)
    assert list((tmp_path / "target").iterdir()) == []


def test_only_gateway_publishes_ports_and_data_is_private():
    config = yaml.safe_load((ROOT / "deploy/compose.yaml").read_text())
    services = config["services"]
    assert set(services) == {"api", "web", "caddy"}
    assert "ports" not in services["api"] and "ports" not in services["web"]
    assert services["api"]["environment"]["SF_PUBLIC_ORIGIN"].startswith("https://${SEARCHOS_DOMAIN:?")
    assert services["api"]["volumes"] == ["searchos_data:/data"]
    assert "volumes" not in services["web"]
    assert services["caddy"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_custom_secret_file_is_loaded_by_api_in_fresh_process(tmp_path):
    secret_file = tmp_path / "secrets.env"
    secret_file.write_text("SEARCHOS_DEPLOY_TEST_SECRET=persisted\n")
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT / "web"),
           "SF_ENV_FILE": str(secret_file)}
    subprocess.run([sys.executable, "-c",
                    "import api.deps, os; "
                    "assert os.environ['SEARCHOS_DEPLOY_TEST_SECRET'] == 'persisted'; "
                    "assert api.deps.ENV_FILE_PATH == os.environ['SF_ENV_FILE']"],
                   cwd=tmp_path, env=env, check=True)


def test_failed_backup_resumes_previous_services_and_removes_partial(tmp_path):
    """Exercise the operator script without touching Docker or the local service."""
    import shutil
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    shutil.copy(ROOT / "deploy/searchos.sh", deploy)
    (deploy / ".env").write_text("SEARCHOS_DOMAIN=unit.test\nSEARCHOS_EMAIL=test@unit.test\n")
    events = tmp_path / "events"
    docker = tmp_path / "docker"
    docker.write_text("""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$EVENTS"
case "$*" in
  *"ps --status running --services"*) printf 'api\\nweb\\ncaddy\\n' ;;
  *"data_archive.py backup"*) printf 'incomplete'; exit 7 ;;
esac
""")
    docker.chmod(0o700)
    output = tmp_path / "backup.tgz"
    result = subprocess.run(["bash", str(deploy / "searchos.sh"), "backup", str(output)],
                            env={**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"],
                                 "EVENTS": str(events)}, capture_output=True)
    assert result.returncode != 0
    assert not output.exists() and not Path(str(output) + ".partial").exists()
    assert "start api web caddy" in events.read_text()
