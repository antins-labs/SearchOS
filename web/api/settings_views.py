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

    profiles = {}
    for name, p in settings.profiles.items():
        ov = store.models.profile_overrides.get(name)
        profiles[name] = {
            "model": p.model,
            "provider": p.provider,
            "api_base": p.api_base,
            "api_key_env": p.api_key_env,
            "api_key_set": key_set(p.api_key_env, p.api_key_fallback),
            "temperature": p.temperature,
            "max_tokens": p.max_tokens,
            "enable_thinking": p.enable_thinking,
            "custom": name in store.models.custom_profiles,
            "overridden": sorted(
                f for f in ("model", "api_base", "api_key_env")
                if ov is not None and getattr(ov, f) is not None
            ),
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
        "roles": dict(settings.roles),
        "role_overrides": dict(store.models.roles),
        "search": {
            "resolved": resolve_search_provider_name(store.models.search_provider or ""),
            "configured": store.models.search_provider,
            "providers": providers,
        },
        "browser_backend": settings.browser_backend,
    }


def run_defaults_view() -> dict:
    from searchos.config.settings import settings

    rd = store.run_defaults
    return {
        "max_time_s": rd.max_time_s if rd.max_time_s is not None else settings.default_max_time_s,
        "search_max_results": settings.search_max_results,
        "enable_skills": settings.enable_skills,
    }


def aggregate_view() -> dict:
    return {
        "effort": effort_view(),
        "skills": skills_view(),
        "models": models_view(),
        "run_defaults": run_defaults_view(),
    }
