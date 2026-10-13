from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from searchos.util.token_tracker import extract_token_usage, TokenUsage
from searchos.harness.session import _PhaseTracker


def test_stream_message_usage_and_cache_are_counted_once():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 40},
    })
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 40)
    result.llm_output = {'token_usage': {'prompt_tokens': 100, 'completion_tokens': 20,
                                       'prompt_tokens_details': {'cached_tokens': 40}}}
    assert extract_token_usage(result) == (100, 20, 120, 40)


def test_response_metadata_usage():
    result = LLMResult(generations=[[ChatGeneration(message=AIMessage(content='ok',
        response_metadata={'usage': {'input_tokens': 10, 'output_tokens': 2}}))]])
    assert extract_token_usage(result) == (10, 2, 12, 0)


def test_phase_totals_include_calls_before_orchestrator_loop():
    usage = TokenUsage()
    usage.add(100, 20, 120, role='skill_router')
    tracker = _PhaseTracker(usage)
    usage.add(50, 5, 55, role='orchestrator')
    phases = tracker.finalize()
    assert sum(p['total_tokens'] for p in phases.values()) == 175
    assert sum(p['llm_calls'] for p in phases.values()) == 2
