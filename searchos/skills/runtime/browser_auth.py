"""本机浏览器认证：会话由宿主持有，生成脚本不接触密码或 cookie。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


class AuthRequired(RuntimeError):
    pass


def storage_root() -> Path:
    from searchos.config.settings import settings
    return Path(settings.browser_auth_dir).expanduser()


def profile_dir(profile: str = 'x') -> Path:
    if profile != 'x':
        raise ValueError('unsupported browser authentication profile')
    root = storage_root()
    for path in [root, root / profile]:
        if path.is_symlink():
            raise ValueError('authentication storage must not be a symlink')
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    return root / profile


def state_path(profile: str = 'x') -> Path:
    path = profile_dir(profile) / 'state.json'
    if path.is_symlink():
        raise ValueError('authentication state must not be a symlink')
    return path


def read_state(profile: str = 'x') -> dict | None:
    path = state_path(profile)
    if not path.exists():
        return None
    os.chmod(path, 0o600)
    try:
        data = json.loads(path.read_text())
        cookies = data.get('cookies', [])
        if not any(c.get('name') == 'auth_token' and c.get('value') for c in cookies):
            return None
        if any(c.get('domain', '').lstrip('.') not in {'x.com', 'twitter.com'} for c in cookies):
            return None
        return data
    except (ValueError, AttributeError, TypeError):
        return None


def save_state(data: dict, profile: str = 'x') -> None:
    path = state_path(profile)
    clean = {'cookies': [c for c in data.get('cookies', [])
                         if c.get('domain', '').lstrip('.') in {'x.com', 'twitter.com'}],
             'origins': []}
    # 不保存 localStorage、页面、密码、其他站点会话。
    temporary = path.with_suffix('.tmp')
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(temporary, flags, 0o600), 'w') as out:
        json.dump(clean, out)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def browser_options(*, headless: bool, proxy_mode: str = 'inherit') -> dict:
    from searchos.skills.runtime.network import browser_proxy_options
    return {'headless': headless, **browser_proxy_options(proxy_mode)}


def start_login(profile: str = 'x', *, proxy_mode: str = 'inherit') -> None:
    """固定宿主进程打开官方登录页；锁文件避免重复弹窗。"""
    folder = profile_dir(profile)
    browser_options(headless=False, proxy_mode=proxy_mode)
    if sys.platform != 'darwin' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise AuthRequired('auth_unavailable: 当前宿主没有图形桌面，请在本机桌面运行登录流程。')
    from importlib.util import find_spec
    if find_spec('playwright') is None:
        raise AuthRequired('auth_unavailable: 请安装 playwright 和 Chromium 后重试。')
    (folder / 'revoked').unlink(missing_ok=True)
    subprocess.Popen([sys.executable, '-m', 'searchos.skills.runtime.browser_login',
                      '--root', str(storage_root().resolve()), '--profile', profile, '--proxy-mode', proxy_mode],
                     cwd=Path(__file__).resolve().parents[3], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def require_state(profile: str = 'x', *, proxy_mode: str = 'inherit') -> dict:
    if state := read_state(profile):
        return state
    start_login(profile, proxy_mode=proxy_mode)
    raise AuthRequired('auth_required: 已请求打开本机 X 登录窗口，请用户手动登录后以新的调用重试；不要自动循环重试。')


def revoke(profile: str = 'x') -> None:
    # 不保留旧会话副本；后续执行必须重新登录。
    state_path(profile).unlink(missing_ok=True)
    marker = profile_dir(profile) / 'revoked'
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(fd)


def command_profile(package: Path, argv: list[str]) -> str | None:
    if '--help' in argv or '-h' in argv:
        return None
    entry = package / 'SKILL.md'
    if not entry.is_file():
        return None
    import yaml
    parts = entry.read_text().split('---', 2)
    if len(parts) != 3:
        return None
    metadata = (yaml.safe_load(parts[1]) or {}).get('metadata', {})
    profile = metadata.get('searchos-browser-profile')
    entries = str(metadata.get('searchos-browser-entries', '')).split(',')
    if not profile or len(argv) < 2 or argv[1] not in [e.strip() for e in entries]:
        return None
    if profile != 'x' or metadata.get('host') not in {'x.com', 'twitter.com'}:
        raise ValueError('browser profile must match a supported target host')
    return profile


def main():
    import argparse
    parser = argparse.ArgumentParser(description='管理本机技能登录态；不输出密码或 cookie。')
    parser.add_argument('action', choices=['status', 'login', 'logout'])
    parser.add_argument('profile', choices=['x'])
    args = parser.parse_args()
    if args.action == 'login':
        start_login(args.profile)
        print('已请求打开本机登录窗口。')
    elif args.action == 'logout':
        revoke(args.profile)
        print('已删除本机保存的会话；这不会撤销 X 服务器上的其他登录会话。')
    else:
        print(json.dumps({'profile': args.profile, 'has_local_session': read_state(args.profile) is not None}))


if __name__ == '__main__':
    main()
