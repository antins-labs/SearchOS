"""SearchAnything CLI 客户端，仅依赖 Python 标准库。"""

from __future__ import annotations

import json
import os
import socket
import sys

MAX_MESSAGE = 24_000_000


def main():
    args = sys.argv[1:]
    if not args or args[0] in {"--help", "-h"}:
        print("searchanything run SKILL -- COMMAND [ARG ...]")
        return 0
    try:
        if args[0] == "run" and len(args) >= 4 and args[2] == "--":
            request = {
                "op": "run",
                "skill": args[1],
                "argv": args[3:],
                "stdin": sys.stdin.read(128_001),
            }
            if len(request["stdin"].encode()) > 128_000:
                raise ValueError("stdin exceeds 128000 bytes")
        else:
            raise ValueError("use searchanything run SKILL -- COMMAND [ARG ...]")
        request["token"] = os.environ["SEARCHOS_RUN_TOKEN"]
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(os.environ["SEARCHOS_BRIDGE_SOCKET"])
            connection.sendall(json.dumps(request).encode() + b"\n")
            with connection.makefile("rb") as stream:
                data = stream.readline(MAX_MESSAGE + 1)
        if len(data) > MAX_MESSAGE:
            raise ValueError("CLI output exceeds the result limit; read the saved artifact")
        result = json.loads(data)
        sys.stdout.write(result.get("stdout", ""))
        sys.stderr.write(result.get("stderr", ""))
        if result.get("error"):
            print(
                json.dumps(
                    {"status": result.get("status"), "error": result["error"]}, ensure_ascii=False
                ),
                file=sys.stderr,
            )
        return result.get("exit_code") if result.get("exit_code") is not None else 1
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
