"""Model-connection routes — role bindings and search backend switching.

Same persistence model as routes/settings.py: env/.env is the base layer,
``settings_store`` holds the web-set deltas. No response ever contains an
API key value — only ``key_set`` booleans.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import settings_store, settings_views
from api.settings_store import store
from api.settings_views import key_set, models_view

router = APIRouter(prefix="/api/settings")


# --- payload models ---

class RolesUpdate(BaseModel, extra="forbid"):
    roles: dict[str, str]


class SearchBackendUpdate(BaseModel, extra="forbid"):
    provider: str | None = None


# --- endpoints ---

@router.get("/models")
async def get_models():
    return models_view()


@router.put("/models/roles")
async def put_roles(req: RolesUpdate):
    from searchos.config.settings import ROLE_NAMES, settings

    warnings = []
    for role, profile in req.roles.items():
        if role not in ROLE_NAMES:
            raise HTTPException(400, f"Unknown role: {role!r}. Valid: {list(ROLE_NAMES)}")
        if profile not in settings.profiles:
            raise HTTPException(400, f"Unknown profile: {profile!r}. Valid: {list(settings.profiles)}")
        p = settings.profiles[profile]
        if not key_set(p.api_key_env, p.api_key_fallback):
            warnings.append(
                f"Profile {profile!r} needs {p.api_key_env} which is not set — runs using role "
                f"{role!r} will fail until it is added to .env"
            )

    def patch(s):
        s.models.roles.update(req.roles)

    await settings_store.update(patch)
    return {"roles": dict(settings.roles), "role_overrides": dict(store.models.roles), "warnings": warnings}


@router.put("/search-backend")
async def put_search_backend(req: SearchBackendUpdate):
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.search import SEARCH_PROVIDER_INFO

    if req.provider is not None:
        if req.provider not in SEARCH_PROVIDER_INFO:
            raise HTTPException(
                400, f"Unknown search provider: {req.provider!r}. Valid: {list(SEARCH_PROVIDER_INFO)}")
        if req.provider in ("serper", "tavily"):
            env_name = SEARCH_PROVIDER_INFO[req.provider]["api_key_env"]
            fallback = settings.serper_api_key if req.provider == "serper" else settings.tavily_api_key
            if not key_set(env_name, fallback):
                raise HTTPException(400, f"{env_name} not set in .env — add it before switching")

    def patch(s):
        s.models.search_provider = req.provider

    await settings_store.update(patch)
    return settings_views.models_view()["search"]
