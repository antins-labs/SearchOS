"""Per-run source controls and skill override semantics."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from searchos.tools.simple_browser.search.base import SearchResult
from searchos.tools.simple_browser.state import (
    SourceControls,
    apply_source_controls,
    get_source_controls,
    is_url_allowed,
    normalize_domain,
    set_source_controls,
)

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "web") not in sys.path:
    sys.path.insert(0, str(_REPO / "web"))


def test_normalize_domain_accepts_host_and_url():
    assert normalize_domain("HTTPS://Docs.Example.com/path?q=1") == "docs.example.com"
    assert normalize_domain("*.example.com") == "example.com"
    assert normalize_domain("example.com:443") == "example.com"


def test_source_controls_exclude_subdomains_and_prioritize_trusted():
    controls = SourceControls(
        trusted_domains=("official.example",),
        excluded_domains=("spam.example",),
    )
    results = [
        SearchResult(title="Neutral", url="https://news.example/item"),
        SearchResult(title="Blocked", url="https://cdn.spam.example/item"),
        SearchResult(title="Trusted", url="https://docs.official.example/item"),
        SearchResult(title="Neutral 2", url="https://other.example/item"),
    ]

    filtered = apply_source_controls(results, controls)

    assert [result.title for result in filtered] == ["Trusted", "Neutral", "Neutral 2"]
    assert not is_url_allowed("https://spam.example/page", controls)
    assert is_url_allowed("https://notspam.example/page", controls)


async def test_source_controls_are_isolated_between_concurrent_runs():
    async def bind(domain: str):
        set_source_controls([domain], [])
        await asyncio.sleep(0)
        return get_source_controls().trusted_domains

    first, second = await asyncio.gather(bind("first.example"), bind("second.example"))

    assert first == ("first.example",)
    assert second == ("second.example",)


def test_explicit_router_override_can_replace_global_access_pin(monkeypatch):
    from api import skills_catalog

    monkeypatch.setattr(
        skills_catalog,
        "skill_pools",
        lambda: {"access": {"alpha", "beta"}, "strategy": set(), "orchestrator": set()},
    )
    monkeypatch.setattr(skills_catalog.store.skills, "access_only", ["alpha"])

    from api.routes.search import SkillOverrides

    kwargs = skills_catalog.effective_skill_kwargs(SkillOverrides(access_only=None))

    assert kwargs["access_only"] is None
