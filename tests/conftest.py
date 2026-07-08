"""全局测试隔离。

最关键的一条：把 SF_MODELS_FILE 指向 tmp 下不存在的路径——否则开发机上
真实的 models.json 会作为模型配置主来源泄漏进所有旧链路测试（预设/深合并
用例会整体失真）。需要 models.json 的用例自行往该路径写文件即可。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_models_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_MODELS_FILE", str(tmp_path / "models.json"))
