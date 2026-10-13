"""测试原生 wrapper 的显式组合顺序。"""


async def model_call(middleware, request, handler):
    for adapter in reversed(middleware):
        inner = handler

        async def handler(request, adapter=adapter, inner=inner):
            return await adapter.awrap_model_call(request, inner)

    return await handler(request)


def capture_pipeline(monkeypatch, pipeline, **kwargs):
    """捕获 pipeline 传给公共图入口的参数，用于检查默认组件选择。"""
    from types import SimpleNamespace
    from searchos.agents import runtime

    monkeypatch.setattr(runtime, "create_search_agent_graph", lambda **args: SimpleNamespace(**args))
    return pipeline(model=object(), tools=[], **kwargs)
