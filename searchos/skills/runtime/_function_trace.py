"""在同一次 Python CLI 执行中记录包内函数；输出与退出状态沿用原入口。"""
import json
import runpy
import sys
import threading
from pathlib import Path


def main():
    destination, root, entry, *arguments = sys.argv[1:]
    root = Path(root).resolve()
    calls, complete = set(), True
    paths = {}

    def profile(frame, event, arg):
        nonlocal complete
        if event == 'c_call' and getattr(arg, '__module__', '') in {'posix', 'nt', '_posixsubprocess'} and getattr(
                arg, '__name__', '') in {'fork', 'fork_exec', 'posix_spawn', 'execv', 'execve', '_exit'}:
            complete = False
        if event != 'call':
            return
        code = frame.f_code
        filename = code.co_filename
        if filename not in paths:
            path = Path(filename)
            paths[filename] = path.resolve().relative_to(root).as_posix() if path.is_absolute() and path.resolve().is_relative_to(root) else None
        relative = paths[filename]
        if relative is not None:
            parent = frame.f_back
            entry_root = bool(parent and parent.f_code.co_name == '<module>'
                and parent.f_globals.get('__name__') == '__main__'
                and Path(parent.f_code.co_filename).resolve() == root / entry)
            calls.add((relative, code.co_firstlineno, code.co_name, entry_root))
        elif frame.f_globals.get('__name__') in {'subprocess', 'multiprocessing.process'} and code.co_name in {'__init__', 'start'}:
            complete = False

    sys.argv = [str(root / entry), *arguments]
    sys.path[0] = str((root / entry).parent)
    threading.setprofile(profile)
    sys.setprofile(profile)
    try:
        runpy.run_path(str(root / entry), run_name='__main__')
    finally:
        complete &= sys.getprofile() is profile and threading.getprofile() is profile
        sys.setprofile(None)
        threading.setprofile(None)
        Path(destination).write_text(json.dumps({'complete': complete, 'calls': [
            {'path': path, 'lineno': line, 'name': name, 'entry_root': entry_root}
            for path, line, name, entry_root in sorted(calls)]}), encoding='utf-8')


if __name__ == '__main__':
    main()
