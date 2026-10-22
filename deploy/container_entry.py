"""Initialize persistent storage before importing any application settings."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv


def prepare(root: Path = Path("/data"), bundled: Path = Path("/app/searchos/skills/library")):
    # Fail closed: containers must never start in localhost's implicit-admin mode.
    origin = os.environ.get("SF_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    if (not re.fullmatch(r"https://[a-zA-Z0-9.-]+", origin)
            or parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.netloc)):
        raise ValueError("SF_PUBLIC_ORIGIN must be https:// followed by a DNS hostname")
    if parsed.hostname.endswith(".example.com") or parsed.hostname == "example.com":
        raise ValueError("Replace the example domain with your own DNS hostname")
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("assistant", "workspaces", "knowledge", "home", "local-index"):
        (root / name).mkdir(exist_ok=True, mode=0o700)
    secret_file = root / "secrets.env"
    secret_file.touch(mode=0o600, exist_ok=True)
    secret_file.chmod(0o600)
    # Load before api.main imports model/settings singletons. Runtime settings
    # written via the UI must survive container replacement.
    load_dotenv(secret_file, override=False)
    skills = root / "skills"
    marker = root / ".skills-initialized"
    if not marker.exists():
        # Use a staging directory so a crash cannot leave a partly seeded library.
        staging = root / ".skills-seed"
        if staging.exists():
            shutil.rmtree(staging)
        if not skills.exists():
            shutil.copytree(bundled, staging)
            staging.rename(skills)
        marker.touch()
    # This is a private, editable snapshot: upgrades do not replace custom skills.


def main():
    prepare()
    if len(sys.argv) < 2:
        raise SystemExit("Missing container command")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
