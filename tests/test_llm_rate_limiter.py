"""Shared LLM RPM/TPM limiter configuration tests."""

from searchos.util.llm_rate_limiter import get_shared_rate_limiter


def test_shared_limiter_updates_limits_for_existing_quota_bucket():
    key = ("https://quota.example/v1", "model-test", "TEST_RATE_KEY")
    first, _ = get_shared_rate_limiter(key, rpm=10, tpm=1000)
    second, _ = get_shared_rate_limiter(key, rpm=25, tpm=5000)

    assert second is first
    assert first.rpm == 25
    assert first.tpm == 5000


def test_shared_limiter_can_disable_limits_after_creation():
    key = ("https://quota.example/v1", "model-disable", "TEST_RATE_KEY")
    limiter, _ = get_shared_rate_limiter(key, rpm=10, tpm=1000)
    same, _ = get_shared_rate_limiter(key, rpm=0, tpm=0)

    assert same is limiter
    assert limiter.rpm == 0
    assert limiter.tpm == 0
