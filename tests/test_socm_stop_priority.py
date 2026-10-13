"""停止状态优先于 SOCM 缺口，收尾调用不能重新启动工具循环。"""
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.agents.execution import ControlExecutor
from searchos.socm import SearchState


@dataclass
class Request:
    messages: list
    system_message: object = None
    tools: list = field(default_factory=lambda: ['search', 'open'])
    tool_choice: object = 'auto'


def stopped_worker(role='search_agent_3'):
    state = SearchState()
    state.coverage_map.add_table('t', ['Name', 'Score'], primary_key=['Name'], entities=['A'])
    control = ControlState()
    control.stop("no_progress_tools_x10")
    control.blocked_tools.update({"search", "open", "find", "skill_*"})
    mw = ControlExecutor(
        control, finish_without_tools=role != "orchestrator",
    )
    mw.test_workspace = SimpleNamespace(load_state=lambda: state)
    mw.test_task = TaskContext(agent_id=role)
    return mw


async def model_with_context(middleware, request, handler):
    context = SOCMContextMiddleware(
        middleware.test_workspace,
        task=middleware.test_task,
        guidance="Continue your assigned task.", control=middleware.control,
    )

    async def with_context(request):
        return await context.awrap_model_call(request, handler)

    return await middleware.call_model(request, with_context)


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['search_agent_3', 'explore_agent_1'])
async def test_stop_guidance_preserves_tool_schema_across_turns(role):
    mw = stopped_worker(role)
    seen = []

    async def handler(request):
        seen.append(request)
        return AIMessage(content='Partial findings; A remains unknown.')

    for _ in range(2):
        await model_with_context(mw, Request([HumanMessage(content='Find A')]), handler)
    for request in seen:
        assert request.tools == ['search', 'open']
        assert request.tool_choice == 'auto'
        assert 'HARD STOP' in request.system_message.content
        assert 'Continue your assigned task' not in request.messages[-1].content
    assert 'Search is stopped' in seen[0].messages[-1].content


@pytest.mark.asyncio
@pytest.mark.parametrize('wrapped', [False, True])
async def test_model_cannot_restart_tools_after_stop_even_if_it_ignores_request(wrapped):
    mw = stopped_worker()

    async def handler(request):
        message = AIMessage(content='I will search again.',
            tool_calls=[{'name':'search', 'args':{'query':'A score'}, 'id':'repeat'}])
        return ModelResponse(result=[message]) if wrapped else message

    response = await model_with_context(mw, Request([HumanMessage(content='Find A')]), handler)
    message = response.result[0] if wrapped else response
    assert not message.tool_calls
    assert 'Search stopped' in message.content
    assert 'no_progress_tools_x10' in message.content


@pytest.mark.asyncio
async def test_orchestrator_retains_drain_tools():
    mw = stopped_worker('orchestrator')
    # 本测试只检查模型工具契约，调度提醒不属于该分支。
    async def handler(request):
        assert request.tools == ['check_agents']
        return AIMessage(content='Drained')
    await model_with_context(mw, Request([HumanMessage(content='Finish')], tools=['check_agents']), handler)


@pytest.mark.asyncio
async def test_agent_graph_terminates_even_when_model_keeps_requesting_search():
    from searchos.agents.runtime import create_search_agent_graph
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.tools import tool

    executed = []

    @tool
    def search(query: str) -> str:
        """Search a query."""
        executed.append(query)
        return 'no results'

    class StubbornModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = StubbornModel(responses=[AIMessage(content='Search again',
        tool_calls=[{'name':'search', 'args':{'query':'same query'}, 'id':'again'}])])
    graph = create_search_agent_graph(model=model, tools=[search], control=stopped_worker().control)
    result = await graph.ainvoke({'messages':[HumanMessage(content='Find A')]}, {'recursion_limit':5, 'configurable': {'thread_id': 'stop'}})
    assert not executed
    assert 'Search stopped' in result['messages'][-1].content
    assert not result['messages'][-1].tool_calls
