"""Offline backup/restore of the single persistent SearchOS volume.

The caller must stop all writers first. Restore only accepts an empty volume.
Archives contain secrets; never place them in a web-served directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
import io

FORMAT = "searchos-volume-v1"


def backup(root: Path, output):
    if not (root / "assistant" / "admin-token").is_file():
        raise ValueError("Not an initialized SearchOS data volume")
    # Reject links rather than following paths outside the volume.
    paths = sorted(root.rglob("*"))
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in paths):
        raise ValueError("Data contains links or special files; archive them manually")
    with tarfile.open(fileobj=output, mode="w|gz", dereference=True) as archive:
        payload = json.dumps({"format": FORMAT}).encode()
        info = tarfile.TarInfo("backup.json")
        info.size, info.mode = len(payload), 0o600
        archive.addfile(info, io.BytesIO(payload))
        for path in paths:
            archive.add(path, arcname="data/" + path.relative_to(root).as_posix(), recursive=False)


def restore(root: Path, source):
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Restore requires an empty data volume; existing data was not changed")
    # Stage the entire archive and validate every member before writing any data.
    with tempfile.TemporaryFile() as spool:
        shutil.copyfileobj(source, spool)
        spool.seek(0)
        with tarfile.open(fileobj=spool, mode="r:gz") as archive:
            members = archive.getmembers()
            names = set()
            for member in members:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                        or str(path) != member.name.rstrip("/")
                        or not (member.isfile() or member.isdir())
                        or member.name in names
                        or (member.name != "backup.json" and
                            (not path.parts or path.parts[0] != "data" or len(path.parts) < 2))):
                    raise ValueError("Unsafe or invalid backup member")
                names.add(member.name)
            if not {"backup.json", "data/assistant/admin-token"}.issubset(names):
                raise ValueError("Incomplete SearchOS backup")
            manifest = archive.extractfile("backup.json")
            if manifest is None or json.load(manifest).get("format") != FORMAT:
                raise ValueError("Unsupported backup format")
            # A parent cannot also be a regular file; validate before extracting.
            files = {m.name for m in members if m.isfile()}
            for member in members:
                if any(str(p) in files for p in PurePosixPath(member.name).parents):
                    raise ValueError("Conflicting backup paths")
            for member in members:
                if member.name == "backup.json":
                    continue
                destination = root.joinpath(*PurePosixPath(member.name).parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if member.isdir():
                    destination.mkdir(exist_ok=True, mode=0o700)
                else:
                    with archive.extractfile(member) as src, destination.open("xb") as dst:
                        shutil.copyfileobj(src, dst)
                    # Retain executable scripts without retaining broad permissions.
                    destination.chmod(0o700 if member.mode & 0o111 else 0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--root", type=Path, default=Path("/data"))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.action == "backup":
            backup(args.root, sys.stdout.buffer)
        else:
            restore(args.root, sys.stdin.buffer)
    except (ValueError, OSError, tarfile.TarError) as error:
        print(f"Backup/restore failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
