"""Model-connection routes — provider presets, API keys, role bindings and
search backend switching.

Same persistence model as routes/settings.py: env/.env is the base layer,
``settings_store`` holds the web-set deltas. Provider switches and key writes
go through ``settings_store.update_env`` (atomic .env write + in-place
settings reload + overlay replay). No response ever contains an API key
value — only ``key_set`` booleans; env names accepted by /keys are strictly
allow-listed (writing arbitrary env vars would be an injection vector).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import settings_store, settings_views
from api.settings_store import store
from api.settings_views import key_set, models_view

router = APIRouter(prefix="/api/settings")

# Provider knobs are written ONLY by PUT /provider — never via PUT /keys.
_KNOB_ENVS = ("SF_PROVIDER", "SF_MODEL", "SF_FAST_MODEL", "SF_API_BASE")


def _allowed_key_envs() -> set[str]:
    """Env names PUT /keys may write. Computed live, never user-extendable."""
    from searchos.config.providers import PRESETS
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.search import SEARCH_PROVIDER_INFO

    allowed = {p.api_key_env for p in PRESETS.values()}
    allowed |= {p.api_key_env for p in settings.profiles.values()}
    allowed |= {info["api_key_env"] for info in SEARCH_PROVIDER_INFO.values()}
    allowed |= {"SF_JINA_API_KEY", "JINA_API_KEY"}
    custom = os.environ.get("SF_API_KEY_ENV", "").strip()
    if custom:
        allowed.add(custom)
    return allowed - set(_KNOB_ENVS)


# --- payload models ---

class RolesUpdate(BaseModel, extra="forbid"):
    roles: dict[str, str]


class SearchBackendUpdate(BaseModel, extra="forbid"):
    provider: str | None = None


class ProviderSwitch(BaseModel, extra="forbid"):
    preset: str
    api_key: str | None = None     # None = keep whatever the env already has
    model: str | None = None       # → SF_MODEL ("" clears the override)
    fast_model: str | None = None  # → SF_FAST_MODEL
    api_base: str | None = None    # → SF_API_BASE


class KeyUpdate(BaseModel, extra="forbid"):
    env: str
    value: str  # "" clears the key


# --- endpoints ---

@router.get("/models")
async def get_models():
    return models_view()


@router.get("/providers")
async def get_providers():
    """Provider preset catalog for the web setup wizard. No key values."""
    from searchos.config.providers import PRESET_GROUPS, PRESETS, active_provider, preset_info

    groups = []
    for group, names in PRESET_GROUPS:
        presets = []
        for name in names:
            info = preset_info(name, PRESETS[name])
            info["key_set"] = bool(os.environ.get(PRESETS[name].api_key_env))
            presets.append(info)
        groups.append({"name": group, "presets": presets})

    return {
        "active": active_provider(),
        "groups": groups,
        # Current env override values (not secrets) so the form can pre-fill.
        "overrides": {
            "model": os.environ.get("SF_MODEL", ""),
            "fast_model": os.environ.get("SF_FAST_MODEL", ""),
            "api_base": os.environ.get("SF_API_BASE", ""),
        },
    }


@router.put("/provider")
async def put_provider(req: ProviderSwitch):
    """Switch the SF_PROVIDER preset — the web counterpart of the setup wizard.

    Persists to .env, hot-reloads the settings singleton, and replays the web
    overlay. Switching to a DIFFERENT preset clears stale SF_MODEL /
    SF_FAST_MODEL / SF_API_BASE overrides (unless re-specified) and the
    role→profile overrides (preset profile names change wholesale). Running
    sessions are unaffected — they snapshotted their models at construction.
    """
    from searchos.config.env_file import validate_env_value
    from searchos.config.providers import ALIASES, active_provider, resolve_preset

    try:
        preset = resolve_preset(req.preset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resolved = req.preset.strip().lower()
    resolved = ALIASES.get(resolved, resolved)  # canonical name for SF_PROVIDER

    key_env = os.environ.get("SF_API_KEY_ENV", "").strip() or preset.api_key_env

    for field in ("api_key", "model", "fast_model", "api_base"):
        value = getattr(req, field)
        if value is not None:
            try:
                validate_env_value(value)
            except ValueError as e:
                raise HTTPException(400, f"Invalid {field}: {e}")

    if not preset.api_key_fallback:
        effective_key = req.api_key if req.api_key is not None else os.environ.get(key_env, "")
        if not effective_key:
            hint = f" (get one at {preset.doc_url})" if preset.doc_url else ""
            raise HTTPException(400, f"API key required: {key_env} is not set{hint}")

    switching = resolved != active_provider()
    warnings: list[str] = []

    env_updates: dict[str, str] = {"SF_PROVIDER": resolved}
    if req.api_key is not None:
        env_updates[key_env] = req.api_key
    for field, env_name in (("model", "SF_MODEL"), ("fast_model", "SF_FAST_MODEL"),
                            ("api_base", "SF_API_BASE")):
        value = getattr(req, field)
        if value is not None:
            env_updates[env_name] = value
        elif switching and os.environ.get(env_name):
            # A stale override from the previous provider would silently
            # replace the new preset's defaults — clear it.
            env_updates[env_name] = ""
            warnings.append(f"Cleared {env_name} override left over from the previous provider")

    if not preset.main_model:
        effective_model = env_updates.get("SF_MODEL")
        if effective_model is None:
            effective_model = os.environ.get("SF_MODEL", "")
        if not effective_model:
            raise HTTPException(
                400, "This preset has no default model — pass 'model' (e.g. qwen3:32b)")

    cleared_roles = sorted(store.models.roles)

    def patch(s):
        s.models.roles.clear()

    try:
        await settings_store.update_env(env_updates, patch)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "models": models_view(),
        "cleared_role_overrides": cleared_roles,
        "warnings": warnings,
    }


@router.put("/keys")
async def put_key(req: KeyUpdate):
    """Set (or clear, with value="") one allow-listed API-key env var."""
    from searchos.config.env_file import validate_env_value

    allowed = _allowed_key_envs()
    if req.env not in allowed:
        raise HTTPException(400, f"Env var {req.env!r} is not an accepted key name")
    try:
        validate_env_value(req.value)
    except ValueError as e:
        raise HTTPException(400, f"Invalid value: {e}")

    await settings_store.update_env({req.env: req.value})
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
