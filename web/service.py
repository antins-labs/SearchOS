#!/usr/bin/env python3
"""User-owned macOS service. No sudo, public listeners, or secret copying.

Run with the repository's .venv/bin/python. See workspace/mobile-assistant/10-local-service.md.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import plistlib
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
LABEL = "com.searchos.personal"
ROOT = Path.home() / "Library" / "Application Support" / "SearchOS"
CONFIG = ROOT / "service.json"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DOMAIN = f"gui/{os.getuid()}"
TARGET = f"{DOMAIN}/{LABEL}"


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    with temp.open("w") as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, indent=2, ensure_ascii=False)
    temp.replace(path)


def service_env(config):
    # launchd has no interactive shell/nvm environment. Pin binaries and PATH.
    env = dict(os.environ)
    env.update(config.get("environment", {}))
    env.update({
        "PATH": config["path"], "PYTHONPATH": config["repo"],
        "PYTHONUNBUFFERED": "1", "NODE_ENV": "production",
        "SF_API_PROXY": f"http://127.0.0.1:{config['api_port']}",
        "SF_NEXT_DIST_DIR": ".next-service", "SF_SERVICE_MANAGED": "launchd",
        "SF_SERVICE_KEEP_AWAKE": "ac" if config["keep_awake"] else "off",
    })
    env.pop("NEXT_PUBLIC_API_URL", None)
    return env


def commands(config):
    repo = Path(config["repo"])
    result = {
        "api": ([config["python"], "-m", "uvicorn", "api.main:app", "--app-dir", str(repo / "web"),
                 "--host", "127.0.0.1", "--port", str(config["api_port"]), "--workers", "1",
                 "--timeout-graceful-shutdown", "10"], repo),
        "web": ([config["node"], str(repo / "web/frontend/node_modules/next/dist/bin/next"),
                 "start", "--hostname", "127.0.0.1", "--port", str(config["web_port"])], repo / "web/frontend"),
    }
    if config["keep_awake"]:
        result["awake"] = (["/usr/bin/caffeinate", "-s"], repo)
    return result


def launch_plist(config, config_path=CONFIG):
    return {
        "Label": LABEL,
        "ProgramArguments": [config["python"], str(Path(config["repo"]) / "web/service.py"), "run", "--config", str(config_path)],
        "WorkingDirectory": config["repo"],
        "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 15,
        "ExitTimeOut": 20, "ProcessType": "Background", "Umask": 0o077,
        "StandardOutPath": str(Path(config["logs"]) / "launcher.log"),
        "StandardErrorPath": str(Path(config["logs"]) / "launcher.log"),
    }


def launchctl(*args, check=True):
    return subprocess.run(["/bin/launchctl", *args], check=check, capture_output=True, text=True)


def loaded():
    return launchctl("print", TARGET, check=False).returncode == 0


def check_ports(config):
    for port in (config["api_port"], config["web_port"]):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(f"端口 {port} 已被占用。请先停止旧 SearchOS 服务；不会自动终止未知进程。") from error


def read_config(path=CONFIG):
    config = json.loads(path.read_text())
    for key in ("api_port", "web_port"):
        if type(config[key]) is not int or not 1024 <= config[key] <= 65535:
            raise ValueError(f"{key} 必须为 1024–65535 的端口")
    if config["api_port"] == config["web_port"]:
        raise ValueError("网页与 API 必须使用不同端口")
    if not isinstance(config.get("environment", {}), dict):
        raise ValueError("environment 必须是配置对象")
    return config


def install(args):
    if loaded():
        raise RuntimeError("服务正在运行。更新前请确认没有执行中任务，再执行 stop。")
    if CONFIG.exists():
        config = read_config()
        if Path(config["repo"]) != REPO:
            raise RuntimeError("已有其他目录的 SearchOS 服务配置，请先卸载旧服务或明确迁移配置。")
    else:
        node = shutil.which("node")
        if not node:
            raise RuntimeError("未找到 Node.js")
        config = {"repo": str(REPO), "python": str(REPO / ".venv/bin/python"), "node": node,
                  "path": os.environ.get("PATH", "/usr/bin:/bin"), "api_port": args.api_port,
                  "web_port": args.web_port, "keep_awake": not args.no_keep_awake,
                  "logs": str(ROOT / "logs"), "environment": {}}
    check_ports(config)
    subprocess.run([config["python"], "-c", "import uvicorn, multipart; from api.main import app"],
                   cwd=config["repo"], env={**service_env(config), "PYTHONPATH": f"{config['repo']}:{config['repo']}/web"}, check=True)
    # Refuse a cross-origin frontend setting: phone cookies and WS must remain same-origin.
    frontend = Path(config["repo"]) / "web/frontend"
    from dotenv import dotenv_values
    for path in [frontend / ".env", frontend / ".env.local", frontend / ".env.production", frontend / ".env.production.local"]:
        if path.exists() and dotenv_values(path).get("NEXT_PUBLIC_API_URL"):
            raise RuntimeError(f"请移除 {path.name} 中的 NEXT_PUBLIC_API_URL，常驻服务要求同源访问。")
    subprocess.run([config["node"], str(frontend / "node_modules/next/dist/bin/next"), "build"],
                   cwd=frontend, env=service_env(config), check=True)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    Path(config["logs"]).mkdir(parents=True, exist_ok=True, mode=0o700)
    save_json(CONFIG, config)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(launch_plist(config)))
    PLIST.chmod(0o600)
    start()


def start():
    if loaded():
        print("SearchOS 常驻服务已加载；使用 status 查看健康状态。")
        return
    config = read_config()
    check_ports(config)
    if not (Path(config["repo"]) / "web/frontend/.next-service/BUILD_ID").is_file():
        raise RuntimeError("缺少生产构建，请执行 install。")
    launchctl("enable", TARGET)
    launchctl("bootstrap", DOMAIN, str(PLIST))
    print("SearchOS 已启用：登录账户后自动启动，子进程退出自动重启。")


def stop():
    if loaded():
        launchctl("bootout", TARGET)
        deadline = time.monotonic() + 25
        while loaded() and time.monotonic() < deadline:
            time.sleep(0.25)
        if loaded():
            raise RuntimeError("服务尚未停止，请检查 launchctl 状态。")
        # bootout can return before SIGTERM cleanup and uvicorn shutdown finish.
        if CONFIG.exists():
            lock_path = Path(read_config()["logs"]) / "supervisor.lock"
            if lock_path.exists():
                with lock_path.open("a+") as lock:
                    while True:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() >= deadline:
                                raise RuntimeError("后台进程仍在退出，请稍后重试。")
                            time.sleep(0.25)


def status():
    if not CONFIG.exists():
        print("尚未安装常驻服务。")
        return
    config = read_config()
    print(f"系统服务：{'已加载' if loaded() else '未加载'}；自启动配置：{'存在' if PLIST.exists() else '不存在'}")
    # Access is deliberately public; no administrator credential is read or logged.
    for name, url in [("API", f"http://127.0.0.1:{config['api_port']}/api/assistant/access"),
                      ("网页", f"http://127.0.0.1:{config['web_port']}/m")]:
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as response:
                print(f"{name}：HTTP {response.status}")
        except Exception:
            print(f"{name}：暂时无法连接")
    print(f"入口：http://127.0.0.1:{config['web_port']}/m\n日志：{config['logs']}\n配置：{CONFIG}")


def logger_for(name, directory):
    logger = logging.getLogger(f"service.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(directory / f"{name}.log", maxBytes=2 * 1024 * 1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


def restart_delay(failures):
    return min(60, 2 ** min(failures, 6))


def run(config):
    os.umask(0o077)
    directory = Path(config["logs"])
    directory.mkdir(parents=True, exist_ok=True)
    # Also prevents accidental duplicate supervisors outside launchd.
    lock = (directory / "supervisor.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    log = logger_for("supervisor", directory)
    shutdown = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: shutdown.set())
    states = {name: {"process": None, "next": 0, "failures": 0, "started": 0}
              for name in commands(config)}
    loggers = {name: logger_for(name, directory) for name in states}

    def drain(process, logger):
        try:
            for line in process.stdout:
                logger.info(line.rstrip())
        finally:
            process.stdout.close()

    try:
        while not shutdown.is_set():
            for name, (command, cwd) in commands(config).items():
                state = states[name]
                process = state["process"]
                now = time.monotonic()
                if process and process.poll() is not None:
                    state["failures"] = 0 if now - state["started"] > 60 else state["failures"] + 1
                    state["next"] = now + restart_delay(state["failures"])
                    log.warning("%s exited (%s); restart in %ss", name, process.returncode, restart_delay(state["failures"]))
                    state["process"] = None
                if state["process"] is None and now >= state["next"]:
                    try:
                        process = subprocess.Popen(command, cwd=cwd, env=service_env(config),
                                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                   text=True, errors="replace")
                        state.update(process=process, started=now)
                        threading.Thread(target=drain, args=(process, loggers[name]), daemon=True).start()
                        log.info("%s started pid=%s", name, process.pid)
                    except OSError:
                        state["failures"] += 1
                        state["next"] = now + restart_delay(state["failures"])
                        log.exception("%s failed to start", name)
            shutdown.wait(0.5)
    finally:
        processes = [state["process"] for state in states.values() if state["process"]]
        for process in processes:
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 12
        for process in processes:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.info("service stopped")
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "start", "stop", "restart", "status", "uninstall", "run"])
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=3100)
    parser.add_argument("--no-keep-awake", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG, help="run 内部使用")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("当前安装器支持 macOS；其他主机可复用配置并使用其系统服务管理器。")
    try:
        if args.action == "install":
            if not (1024 <= args.api_port <= 65535 and 1024 <= args.web_port <= 65535 and args.api_port != args.web_port):
                parser.error("请指定两个不同的 1024–65535 端口")
            install(args)
        elif args.action == "run":
            run(read_config(args.config))
        elif args.action == "start":
            start()
        elif args.action == "stop":
            stop()
            print("服务已停止；下次登录仍会自动启动。永久关闭请执行 uninstall。")
        elif args.action == "restart":
            stop()
            start()
        elif args.action == "status":
            status()
        elif args.action == "uninstall":
            stop()
            PLIST.unlink(missing_ok=True)
            print("已取消常驻与自启动；配置、日志、计划和资料均保留。")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"操作失败：{error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
