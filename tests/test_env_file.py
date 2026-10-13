"""searchos/config/env_file.py — .env 原子读写与值校验。"""

import pytest

from searchos.config.env_file import (
    apply_env_updates,
    find_env_path,
    remove_env_keys,
    update_env_file,
    validate_env_value,
)


def test_update_replaces_in_place_and_keeps_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# 注释保留\nSF_PROVIDER=old\nOTHER=1\n")
    update_env_file(env, {"SF_PROVIDER": "deepseek"})
    lines = env.read_text().splitlines()
    assert lines[0] == "# 注释保留"
    assert lines[1] == "SF_PROVIDER=deepseek"
    assert lines[2] == "OTHER=1"


def test_update_appends_new_keys_with_separator(tmp_path):
    env = tmp_path / ".env"
    env.write_text("EXISTING=x\n")
    update_env_file(env, {"NEW_KEY": "v"})
    text = env.read_text()
    assert "EXISTING=x" in text
    assert text.rstrip().endswith("NEW_KEY=v")


def test_update_creates_missing_file_with_header(tmp_path):
    env = tmp_path / ".env"
    update_env_file(env, {"SF_PROVIDER": "ollama"})
    text = env.read_text()
    assert text.startswith("# SearchOS")
    assert "SF_PROVIDER=ollama" in text


def test_update_is_atomic_no_tmp_leftover(tmp_path):
    env = tmp_path / ".env"
    update_env_file(env, {"A": "1"})
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_repeated_update_keeps_single_line(tmp_path):
    env = tmp_path / ".env"
    update_env_file(env, {"SF_PROVIDER": "deepseek"})
    update_env_file(env, {"SF_PROVIDER": "openai"})
    lines = [l for l in env.read_text().splitlines() if l.startswith("SF_PROVIDER=")]
    assert lines == ["SF_PROVIDER=openai"]


def test_apply_env_updates_syncs_environ(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setenv("SF_TEST_KEY", "stale")
    apply_env_updates(env, {"SF_TEST_KEY": "fresh", "SF_TEST_EMPTY": ""})
    import os
    assert os.environ["SF_TEST_KEY"] == "fresh"
    assert "SF_TEST_EMPTY" not in os.environ  # 空串 = 清除
    assert "SF_TEST_EMPTY=" in env.read_text()


@pytest.mark.parametrize("bad", [
    "x\nSF_EVIL=1",   # 行注入
    "with space",
    'quo"te',
    "quo'te",
    "ha#sh",
    "back\\slash",
    "café",           # 非 ASCII
    "x" * 2000,       # 超长
])
def test_validate_rejects_unsafe_values(bad):
    with pytest.raises(ValueError):
        validate_env_value(bad)


@pytest.mark.parametrize("ok", ["", "sk-abc123", "https://api.deepseek.com/v1", "glm-5.2"])
def test_validate_accepts_normal_values(ok):
    validate_env_value(ok)


def test_remove_env_keys_drops_lines_keeps_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# 头注释\nSF_ENABLE_SKILLS=true\nOPENAI_API_KEY=sk-keep\nHTTP_PROXY=http://x\n")
    removed = remove_env_keys(env, ["SF_ENABLE_SKILLS", "HTTP_PROXY", "ABSENT_KEY"])
    assert set(removed) == {"SF_ENABLE_SKILLS", "HTTP_PROXY"}
    text = env.read_text()
    assert "# 头注释" in text
    assert "OPENAI_API_KEY=sk-keep" in text
    assert "SF_ENABLE_SKILLS" not in text
    assert "HTTP_PROXY" not in text


def test_remove_env_keys_noop_when_no_match(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-x\n")
    assert remove_env_keys(env, ["NOPE"]) == []
    assert env.read_text() == "OPENAI_API_KEY=sk-x\n"


def test_remove_env_keys_missing_file(tmp_path):
    assert remove_env_keys(tmp_path / "absent.env", ["A"]) == []


def test_remove_env_keys_ignores_commented_assignment(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# SF_ENABLE_SKILLS=true\nSF_ENABLE_SKILLS=true\n")
    removed = remove_env_keys(env, ["SF_ENABLE_SKILLS"])
    assert removed == ["SF_ENABLE_SKILLS"]  # 只删真实赋值行，注释保留
    assert env.read_text() == "# SF_ENABLE_SKILLS=true\n"


def test_find_env_path_prefers_existing(tmp_path):
    (tmp_path / ".env").write_text("")
    assert find_env_path(tmp_path) == tmp_path / ".env"


def test_find_env_path_defaults_to_start(tmp_path):
    sub = tmp_path / "nowhere"
    sub.mkdir()
    # 包上级目录可能真有 .env（开发机），存在则返回那一个也是正确语义；
    # 只断言返回值是合法路径且以 .env 结尾。
    assert find_env_path(sub).name == ".env"
