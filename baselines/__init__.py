"""SearchForge baselines package.

Registers the hyphenated 'gpt-oss-simple-browser' directory as an importable
Python package under the name 'baselines.gpt_oss_simple_browser'.
"""

import importlib.util
import sys
from pathlib import Path

_BROWSER_DIR = Path(__file__).parent / "gpt-oss-simple-browser"


def _register_subpkg(dotted_name: str, fs_path: Path):
    """Register a filesystem path as a Python (sub-)package."""
    if dotted_name in sys.modules:
        return
    init = fs_path / "__init__.py" if fs_path.is_dir() else fs_path
    sub_locs = [str(fs_path)] if fs_path.is_dir() else None
    spec = importlib.util.spec_from_file_location(
        dotted_name, init, submodule_search_locations=sub_locs,
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)


# Top-level package
_register_subpkg("baselines.gpt_oss_simple_browser", _BROWSER_DIR)

# Sub-packages / modules used by searchforge
for _sub in ("tools", "llm"):
    _sub_dir = _BROWSER_DIR / _sub
    if _sub_dir.is_dir():
        _register_subpkg(f"baselines.gpt_oss_simple_browser.{_sub}", _sub_dir)

for _mod_name in ("state", "models", "config", "agent"):
    _mod_file = _BROWSER_DIR / f"{_mod_name}.py"
    if _mod_file.exists():
        _register_subpkg(f"baselines.gpt_oss_simple_browser.{_mod_name}", _mod_file)

# Tools sub-modules
for _tool_mod in ("search", "browser", "html_processor", "tool_defs"):
    _tool_file = _BROWSER_DIR / "tools" / f"{_tool_mod}.py"
    if _tool_file.exists():
        _register_subpkg(
            f"baselines.gpt_oss_simple_browser.tools.{_tool_mod}", _tool_file,
        )
