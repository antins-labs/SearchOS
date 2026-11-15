import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from searchos.harness.session import _PhaseTracker
from searchos.harness.telemetry.usage import (
    TokenTrackingCallback,
    TokenUsage,
    extract_token_usage,
    start_tracking,
)


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


@pytest.mark.parametrize('cache_fields', [
    {'prompt_tokens_details': {'cached_tokens': 40}},
    {'input_tokens_details': {'cached_tokens': 40}},
    {'input_token_details': {'cache_read': 40}},
    {'prompt_cache_hit_tokens': 40},
    {'cache_read_input_tokens': 40},
])
def test_cache_fields_from_provider_dialects(cache_fields):
    result = LLMResult(generations=[], llm_output={'usage': {
        'input_tokens': 100, 'output_tokens': 20, **cache_fields,
    }})
    assert extract_token_usage(result) == (100, 20, 120, 40)


@pytest.mark.parametrize('raw_key', ['sf_raw_usage', 'token_usage', 'usage'])
def test_message_normalized_usage_preserves_raw_cache_fields(raw_key):
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
    }, response_metadata={raw_key: {
        'prompt_tokens': 100, 'completion_tokens': 20,
        'prompt_cache_hit_tokens': 40,
    }})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 40)


def test_normalized_aggregate_can_fill_missing_cache_from_message_raw_usage():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
    }, response_metadata={'sf_raw_usage': {'prompt_cache_hit_tokens': 40}})
    result = LLMResult(generations=[[ChatGeneration(message=message)]], llm_output={
        'token_usage': {'prompt_tokens': 100, 'completion_tokens': 20,
                        'total_tokens': 120},
    })
    assert extract_token_usage(result) == (100, 20, 120, 40)


def test_generation_info_can_fill_missing_cache_in_normalized_message_usage():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
    })
    generation = ChatGeneration(message=message, generation_info={
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20,
                  'prompt_cache_hit_tokens': 40},
    })
    assert extract_token_usage(LLMResult(generations=[[generation]])) == (100, 20, 120, 40)


def test_explicit_zero_cache_is_not_replaced_by_another_cache_field():
    result = LLMResult(generations=[], llm_output={'usage': {
        'prompt_tokens': 100, 'completion_tokens': 20,
        'prompt_tokens_details': {'cached_tokens': 0},
        'prompt_cache_hit_tokens': 40,
    }})
    assert extract_token_usage(result) == (100, 20, 120, 0)


def test_raw_cache_takes_priority_over_normalized_zero():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 0},
    }, response_metadata={'sf_raw_usage': {'prompt_cache_hit_tokens': 40}})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 40)


def test_explicit_zero_raw_cache_takes_priority_over_normalized_cache():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 40},
    }, response_metadata={'sf_raw_usage': {'prompt_cache_hit_tokens': 0}})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 0)


def test_raw_token_counts_take_priority_over_normalized_counts():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
    }, response_metadata={'sf_raw_usage': {
        'prompt_tokens': 110, 'completion_tokens': 30, 'total_tokens': 140,
    }})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (110, 30, 140, 0)


@pytest.mark.parametrize('last_cache', [0, 50])
def test_raw_stream_snapshots_use_latest_cumulative_fields_once(last_cache):
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 40},
    }, response_metadata={'sf_raw_usage': [
        {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 40},
        {'prompt_tokens': 100, 'prompt_cache_hit_tokens': last_cache},
        {'completion_tokens': 20, 'total_tokens': 120},
    ]})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, last_cache)


def test_explicit_zero_token_counts_do_not_use_alternate_names():
    result = LLMResult(generations=[], llm_output={'usage': {
        'prompt_tokens': 0, 'input_tokens': 100,
        'completion_tokens': 0, 'output_tokens': 20, 'total_tokens': 0,
    }})
    assert extract_token_usage(result) == (0, 0, 0, 0)


def test_missing_cache_does_not_estimate_hit_from_prompt_length():
    result = LLMResult(generations=[], llm_output={'usage': {
        'prompt_tokens': 100_000, 'completion_tokens': 20,
    }})
    assert extract_token_usage(result) == (100_000, 20, 100_020, 0)


def test_batch_prompt_groups_count_once_per_input_and_fill_each_cache():
    groups = []
    for prompt, completion, cached in [(100, 20, 40), (200, 30, 80)]:
        # 同一输入的候选共享 usage，每个输入单独累计。
        message = AIMessage(content='ok', usage_metadata={
            'input_tokens': prompt, 'output_tokens': completion,
            'total_tokens': prompt + completion,
        }, response_metadata={'sf_raw_usage': {'prompt_cache_hit_tokens': cached}})
        groups.append([ChatGeneration(message=message), ChatGeneration(message=message)])
    assert extract_token_usage(LLMResult(generations=groups)) == (300, 50, 350, 120)


def test_aggregate_usage_and_batch_messages_are_not_added_twice():
    groups = []
    for prompt, completion in [(100, 20), (200, 30)]:
        message = AIMessage(content='ok', usage_metadata={
            'input_tokens': prompt, 'output_tokens': completion,
            'total_tokens': prompt + completion,
            'input_token_details': {'cache_read': prompt // 2},
        })
        groups.append([ChatGeneration(message=message), ChatGeneration(message=message)])
    result = LLMResult(generations=groups, llm_output={'token_usage': {
        'prompt_tokens': 300, 'completion_tokens': 50, 'total_tokens': 350,
        'prompt_tokens_details': {'cached_tokens': 150},
    }})
    assert extract_token_usage(result) == (300, 50, 350, 150)


def test_phase_totals_include_calls_before_orchestrator_loop():
    usage = TokenUsage()
    usage.finish_call('router', {'usage': {
        'prompt_tokens': 100, 'completion_tokens': 20,
    }}, role='skill_router')
    tracker = _PhaseTracker(usage)
    usage.finish_call('main', {'usage': {
        'prompt_tokens': 50, 'completion_tokens': 5,
    }}, role='orchestrator')
    phases = tracker.finalize()
    assert sum(p['total_tokens'] for p in phases.values()) == 175
    assert sum(p['llm_calls'] for p in phases.values()) == 2


@pytest.mark.parametrize('aggregate_counts', [False, True])
@pytest.mark.parametrize('derive_first_cache', [False, True])
def test_partial_batch_cache_stays_unknown(aggregate_counts, derive_first_cache):
    first_usage = {'prompt_tokens': 100, 'completion_tokens': 20}
    first_usage.update({'prompt_cache_miss_tokens': 60} if derive_first_cache
                       else {'prompt_cache_hit_tokens': 40})
    groups = [[ChatGeneration(message=AIMessage(content='ok', response_metadata={
        'sf_raw_usage': raw,
    }))] for raw in [first_usage, {'prompt_tokens': 200, 'completion_tokens': 30}]]
    result = LLMResult(generations=groups, llm_output={
        'token_usage': {'prompt_tokens': 300, 'completion_tokens': 50},
    } if aggregate_counts else None)
    usage = start_tracking()
    TokenTrackingCallback(role='orchestrator').on_llm_end(result)
    assert usage.prompt_tokens == 300
    assert usage.completion_tokens == 50
    assert usage.cache_unreported_calls == 1
    assert usage.cache_hit_rate is None


def test_partial_batch_input_does_not_become_complete_call_usage():
    groups = [[ChatGeneration(message=AIMessage(content='ok', response_metadata={
        'sf_raw_usage': raw,
    }))] for raw in [
        {'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_cache_hit_tokens': 40},
        {'completion_tokens': 30, 'prompt_cache_hit_tokens': 80},
    ]]
    usage = start_tracking()
    TokenTrackingCallback(role='orchestrator').on_llm_end(LLMResult(generations=groups))
    assert usage.completion_tokens == 50
    assert usage.usage_unreported_calls == 1
    assert usage.cache_hit_rate is None


@pytest.mark.parametrize(('delta_usage', 'expected_prompt'), [
    ({'input_tokens': 120, 'output_tokens': 20}, 190),
    ({'cache_read_input_tokens': 80, 'output_tokens': 20}, 210),
])
def test_anthropic_partial_delta_keeps_other_cumulative_input_fields(delta_usage, expected_prompt):
    message = AIMessage(content='ok', response_metadata={'sf_raw_usage': [
        {'protocol': 'anthropic', 'event': 'message_start', 'usage': {
            'input_tokens': 100, 'output_tokens': 0,
            'cache_read_input_tokens': 40, 'cache_creation_input_tokens': 30,
        }},
        {'protocol': 'anthropic', 'event': 'message_delta', 'usage': delta_usage},
    ]})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    expected_cache = delta_usage.get('cache_read_input_tokens', 40)
    assert extract_token_usage(result) == (expected_prompt, 20, expected_prompt + 20,
                                            expected_cache)


def test_alternative_generations_can_fill_missing_usage_without_double_counting():
    generations = [ChatGeneration(message=AIMessage(content='ok', response_metadata={
        'sf_raw_usage': raw,
    })) for raw in [
        {'prompt_tokens': 100},
        {'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_cache_hit_tokens': 40},
    ]]
    assert extract_token_usage(LLMResult(generations=[generations])) == (100, 20, 120, 40)


def test_raw_cache_miss_uses_normalized_explicit_cache_before_deriving():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 50},
    }, response_metadata={'sf_raw_usage': {
        'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_cache_miss_tokens': 60,
    }})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 50)


def test_raw_cache_miss_derives_cache_from_known_prompt_when_hit_is_unavailable():
    message = AIMessage(content='ok', usage_metadata={
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
    }, response_metadata={'sf_raw_usage': {'prompt_cache_miss_tokens': 60}})
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    assert extract_token_usage(result) == (100, 20, 120, 40)


def test_later_alternative_raw_usage_precedes_earlier_normalized_usage():
    messages = [
        AIMessage(content='first', usage_metadata={
            'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
            'input_token_details': {'cache_read': 0},
        }),
        AIMessage(content='second', response_metadata={'sf_raw_usage': {
            'prompt_tokens': 110, 'completion_tokens': 30, 'prompt_cache_hit_tokens': 40,
        }}),
    ]
    result = LLMResult(generations=[[ChatGeneration(message=m) for m in messages]])
    assert extract_token_usage(result) == (110, 30, 140, 40)


def test_latest_inconsistent_cache_miss_keeps_cache_unknown():
    message = AIMessage(content='ok', response_metadata={'sf_raw_usage': [
        {'prompt_tokens': 100, 'completion_tokens': 20, 'prompt_cache_miss_tokens': 60},
        {'prompt_tokens': 200, 'prompt_cache_miss_tokens': 300},
    ]})
    usage = start_tracking()
    TokenTrackingCallback('orchestrator').on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=message)]]),
    )
    assert usage.cache_unreported_calls == 1
    assert usage.cache_hit_rate is None
