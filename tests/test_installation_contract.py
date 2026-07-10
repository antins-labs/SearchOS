"""安装与打包契约回归测试。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]


def _requirement_names(requirements: list[str]) -> set[str]:
    names: set[str] = set()
    for requirement in requirements:
        name = requirement.split("[", 1)[0]
        for marker in ("<", ">", "=", "!", "~", ";"):
            name = name.split(marker, 1)[0]
        names.add(name.strip().lower())
    return names


def test_runtime_dependencies_are_declared_directly() -> None:
    metadata = _project_metadata()
    declared = _requirement_names(metadata["dependencies"])

    # 这些包由 SearchOS 直接导入，不能只依赖其他包偶然传递安装。
    assert {
        "certifi",
        "langchain",
        "openai",
        "python-dotenv",
        "pyyaml",
        "requests",
    } <= declared


def test_cli_and_access_install_contract() -> None:
    metadata = _project_metadata()
    assert metadata["scripts"]["searchos"] == "searchos.cli:main"

    extras = metadata["optional-dependencies"]
    access = _requirement_names(extras["access"])
    assert {
        "beautifulsoup4",
        "curl-cffi",
        "openpyxl",
        "pandas",
        "pillow",
        "playwright",
        "pypdf2",
        "python-dateutil",
    } <= access
    assert any(item.startswith("searchos[access") for item in extras["all"])


def test_one_click_installer_is_executable() -> None:
    installer = ROOT / "install.sh"
    assert installer.is_file()
    assert os.access(installer, os.X_OK)


def test_installer_diagnoses_conflicting_console_script() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "command -v searchos" in installer
    assert "它不属于当前仓库" in installer
    assert "hash -r" in installer


def test_active_access_executors_compile() -> None:
    access_root = ROOT / "searchos" / "skills" / "library" / "access"
    executors = [
        path
        for path in access_root.rglob("executor.py")
        if "_rejected" not in path.parts
    ]
    assert executors
    for executor in executors:
        compile(executor.read_text(encoding="utf-8"), str(executor), "exec")
