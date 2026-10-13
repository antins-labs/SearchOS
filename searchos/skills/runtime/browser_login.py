"""独立本机登录窗口；只接受固定站点，状态不包含页面或凭据。"""
import argparse
import fcntl
import json
import os
import time

from searchos.skills.runtime.browser_auth import profile_dir, save_state, browser_options


def write_login_status(stage: str, *, profile: str = 'x') -> None:
    path = profile_dir(profile) / 'login-status.json'
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'w') as stream:
        json.dump({'stage': stage, 'pid': os.getpid(), 'updated_at': time.time()}, stream)
    os.chmod(path, 0o600)


def wait_for_login(context, page, folder, *, profile='x', timeout_s=900):
    from playwright.sync_api import Error as BrowserError
    page.bring_to_front()
    try:
        page.goto('https://x.com/i/flow/login', timeout=45000, wait_until='domcontentloaded')
        write_login_status('waiting_for_user', profile=profile)
    except BrowserError:
        # 页面加载失败时保留窗口，用户可以看见错误并手动刷新；不静默退出。
        write_login_status('navigation_failed', profile=profile)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if (folder/'revoked').exists():
            write_login_status('cancelled', profile=profile)
            return
        if page.is_closed():
            write_login_status('window_closed', profile=profile)
            return
        if any(c['name'] == 'auth_token' and c['value'] for c in context.cookies('https://x.com')):
            save_state(context.storage_state(), profile)
            write_login_status('authenticated', profile=profile)
            return
        page.wait_for_timeout(1000)
    write_login_status('timed_out', profile=profile)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--profile', choices=['x'], required=True)
    args = parser.parse_args()
    from searchos.config.settings import settings
    settings.browser_auth_dir = args.root
    folder = profile_dir(args.profile)
    fd = os.open(folder/'login.lock', os.O_CREAT | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        write_login_status('launching', profile=args.profile)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(**browser_options(headless=False))
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    wait_for_login(context, page, folder, profile=args.profile)
                finally:
                    browser.close()
        except Exception:
            # 不记录原始异常：浏览器异常可能包含页面信息或请求参数。
            write_login_status('browser_failed', profile=args.profile)


if __name__ == '__main__':
    main()
