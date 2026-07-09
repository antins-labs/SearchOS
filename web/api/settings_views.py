"""Read-only view builders for the settings API responses.

Views combine the env-based ``settings`` singleton with the web overlay
(``settings_store.store``). Secrets NEVER appear in a view — key presence is
reported as booleans only (``key_set`` / ``api_key_set``).
"""

from __future__ import annotations

import os

from api import skills_catalog
from api.settings_store import store


def key_set(env_name: str, fallback: str = "") -> bool:
    return bool(os.environ.get(env_name) or fallback)


def effort_view() -> dict:
    from searchos.config.effort import EFFORT_KEYS, EFFORT_LEVELS
    from searchos.config.settings import settings

    return {
        "level": store.effort.level or "medium",
        "knobs": {k: getattr(settings, k) for k in EFFORT_KEYS},
        "overrides": store.effort.overrides,
        "levels": EFFORT_LEVELS,
    }


def skills_view() -> dict:
    from searchos.config.settings import settings

    catalog = skills_catalog.skill_catalog()
    return {
        "enable_skills": settings.enable_skills,
        "access_mode": "only" if store.skills.access_only is not None else "router",
        "categories": {
            cat: [
                {
                    "name": s.meta.name,
                    "description": (s.meta.description or s.meta.trigger or "").strip(),
                    "status": s.meta.status.value,
                    "enabled": skills_catalog.skill_enabled(cat, s.meta.name),
                }
                for s in skills
            ]
            for cat, skills in catalog.items()
        },
    }


def models_view() -> dict:
    from searchos.config.providers import active_provider
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.search import (
        SEARCH_PROVIDER_INFO,
        resolve_search_provider_name,
    )

    cp_map = store.models.custom_profiles
    profiles = {}
    for name, p in settings.profiles.items():
        ov = store.models.profile_overrides.get(name)
        # Which provider connection this card points at (custom carries its own
        # ref; a base card's ref lives in its override).
        provider_ref = cp_map[name].provider_ref if name in cp_map else (
            ov.provider_ref if ov is not None else None
        )
        profiles[name] = {
            "model": p.model,
            "provider": p.provider,
            "api_base": p.api_base,
            "api_key_env": p.api_key_env,
            "api_key_set": key_set(p.api_key_env, p.api_key_fallback),
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "enable_thinking": p.enable_thinking,
            "thinking_style": p.thinking_style,
            "custom": name in cp_map,
            "provider_ref": provider_ref,
            "overridden": sorted(
                f for f in ("model", "api_base", "api_key_env", "provider_ref",
                            "temperature", "enable_thinking")
                if ov is not None and getattr(ov, f) is not None
            ),
        }

    provider_connections = {
        name: {
            "protocol": c.protocol,
            "api_base": c.api_base,
            # Every candidate key env with its own presence flag; the first is
            # the connection's default. A card may select a non-default one.
            "api_key_envs": [{"env": e, "key_set": key_set(e)} for e in c.api_key_envs],
            "thinking_style": c.thinking_style,
            "label": c.label,
            # Connection-level dot: usable if ANY of its keys is present.
            "key_set": any(key_set(e) for e in c.api_key_envs),
        }
        for name, c in store.models.provider_connections.items()
    }

    search_key_fallbacks = {
        "serper": settings.serper_api_key,
        "tavily": settings.tavily_api_key,
    }
    providers = [
        {
            "name": name,
            "label": info["label"],
            "api_key_env": info["api_key_env"],
            "key_set": key_set(info["api_key_env"], search_key_fallbacks.get(name, "")),
            "doc_url": info["doc_url"],
        }
        for name, info in SEARCH_PROVIDER_INFO.items()
    ]

    return {
        "active_provider_preset": active_provider(),
        "profiles": profiles,
        "provider_connections": provider_connections,
        "roles": dict(settings.roles),
        "role_overrides": dict(store.models.roles),
        "search": {
            "resolved": resolve_search_provider_name(store.models.search_provider or ""),
            "configured": store.models.search_provider,
            "providers": providers,
        },
        "browser_backend": settings.browser_backend,
        "jina_api_key_set": key_set("JINA_API_KEY") or key_set("SF_JINA_API_KEY", settings.jina_api_key),
    }


def run_defaults_view() -> dict:
    from searchos.config.settings import settings

    rd = store.run_defaults
    return {
        "max_time_s": rd.max_time_s if rd.max_time_s is not None else settings.default_max_time_s,
        "search_max_results": settings.search_max_results,
        "enable_skills": settings.enable_skills,
    }


def advanced_view() -> dict:
    """First-class runtime knobs. Proxy / cache dir are NOT secrets — echo the
    resolved value so the field round-trips. ``overridden`` lists which knobs the
    overlay currently pins (vs. env/code default)."""
    from searchos.config.settings import settings

    adv = store.advanced
    proxy = adv.https_proxy if adv.https_proxy is not None else (
        os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
    )
    return {
        "llm_max_retries": settings.llm_max_retries,
        "browser_disk_cache_dir": settings.browser_disk_cache_dir,
        "https_proxy": proxy,
        "search_max_results": settings.search_max_results,
        "overridden": sorted(
            f for f in ("llm_max_retries", "browser_disk_cache_dir", "https_proxy")
            if getattr(adv, f) is not None
        ),
    }


def aggregate_view() -> dict:
    return {
        "effort": effort_view(),
        "skills": skills_view(),
        "models": models_view(),
        "run_defaults": run_defaults_view(),
        "advanced": advanced_view(),
    }
