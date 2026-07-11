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
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    allowed |= {e for c in store.models.provider_connections.values() for e in c.api_key_envs}
    allowed |= {info["api_key_env"] for info in SEARCH_PROVIDER_INFO.values()}
    # Proxy is no longer a .env key — it lives in the overlay's `advanced` section
    # (PUT /api/settings/advanced), applied to os.environ at runtime.
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


class ProviderConnUpsert(BaseModel, extra="forbid"):
    """A user-defined provider connection. Model cards reference it by name; the
    key VALUES are written separately via PUT /keys (only the env names live
    here). ``api_key_envs`` may list several keys — the first is the default."""
    protocol: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_envs: list[str] = Field(default_factory=list)
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] = "none"
    label: str = ""


class ProfilePatch(BaseModel, extra="forbid"):
    """Model-card edits. ``provider_ref`` re-points the card at a user-defined
    provider connection (its protocol/base/key_env/thinking_style then win). The
    card's own tunables are model id + temperature + enable_thinking.

    On a base profile "" clears a connection field's override; on a custom profile
    fields are edited in place. model_fields_set tells "not sent" from an explicit
    None (temperature None = omit the param; provider_ref None = drop the ref)."""
    model: str | None = None
    api_base: str | None = None
    api_key_env: str | None = None
    provider: Literal["openai_compatible", "openai", "anthropic"] | None = None
    provider_ref: str | None = None
    temperature: float | None = None
    enable_thinking: bool | None = None
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] | None = None
    rpm: int | None = Field(default=None, ge=0)
    tpm: int | None = Field(default=None, ge=0)


class ProfileCreate(BaseModel, extra="forbid"):
    name: str
    model: str
    # A card normally points at a provider connection; the inline provider/
    # api_base/api_key_env are only used (and api_key_env required) when no ref.
    provider_ref: str | None = None
    provider: Literal["openai_compatible", "openai", "anthropic"] = "openai_compatible"
    api_base: str = ""
    api_key_env: str = ""
    temperature: float | None = None
    enable_thinking: bool = False
    thinking_style: Literal["chat_template_kwargs", "enable_thinking", "none"] = "none"
    rpm: int = Field(default=0, ge=0)
    tpm: int = Field(default=0, ge=0)


_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Every provider preset generates these tier names — reserving them keeps a
# later preset switch from colliding with a custom profile.
_RESERVED_PROFILE_NAMES = {"main", "judge", "fast", "synthesis", "reformat"}


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
    cleared_profile_overrides = sorted(store.models.profile_overrides)

    def patch(s):
        # Preset profile names change wholesale — role bindings and per-profile
        # overrides would dangle or mis-apply. Custom profiles are
        # self-contained and survive.
        s.models.roles.clear()
        s.models.profile_overrides.clear()

    try:
        await settings_store.update_env(env_updates, patch)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "models": models_view(),
        "cleared_role_overrides": cleared_roles,
        "cleared_profile_overrides": cleared_profile_overrides,
        "warnings": warnings,
    }


@router.patch("/profiles/{name}")
async def patch_profile(name: str, req: ProfilePatch):
    """Edit a profile's connection fields (model / api_base / api_key_env).

    Base (env/preset) profiles get sparse overrides in the web overlay; ""
    clears one field's override back to the base value. Custom profiles are
    edited in place. Changes affect sessions created afterwards.
    """
    from searchos.config.settings import settings

    from api.settings_store import ProfileOverride

    is_custom = name in store.models.custom_profiles
    if not is_custom and name not in settings.profiles:
        raise HTTPException(404, f"Unknown profile: {name!r}")

    if req.api_key_env is not None and req.api_key_env != "" \
            and not _ENV_NAME_RE.fullmatch(req.api_key_env):
        raise HTTPException(400, "api_key_env must look like AN_ENV_VAR_NAME")
    if is_custom:
        for field in ("model", "api_key_env"):
            if getattr(req, field) == "":
                raise HTTPException(400, f"{field} cannot be empty on a custom profile")

    if req.provider_ref not in (None, "") and req.provider_ref not in store.models.provider_connections:
        raise HTTPException(400, f"Unknown provider connection: {req.provider_ref!r}")

    def patch(s):
        if is_custom:
            cp = s.models.custom_profiles[name]
            for field in ("model", "api_base", "api_key_env", "provider"):
                value = getattr(req, field)
                if value is not None:
                    setattr(cp, field, value)
            # provider_ref: "" drops the ref (back to inline fields), a name sets it.
            if "provider_ref" in req.model_fields_set:
                cp.provider_ref = req.provider_ref or None
            # Sampling knobs — model_fields_set distinguishes "not sent" from an
            # explicit None (temperature None means "omit the param").
            if "temperature" in req.model_fields_set:
                cp.temperature = req.temperature
            if req.enable_thinking is not None:
                cp.enable_thinking = req.enable_thinking
            if req.thinking_style is not None:
                cp.thinking_style = req.thinking_style
            for field in ("rpm", "tpm"):
                if field in req.model_fields_set:
                    setattr(cp, field, getattr(req, field) or 0)
        else:
            ov = s.models.profile_overrides.get(name) or ProfileOverride()
            for field in ("model", "api_base", "api_key_env"):
                value = getattr(req, field)
                if value is not None:
                    setattr(ov, field, value or None)  # "" → clear the override
            # provider_ref / temperature: None from the wire means "clear this
            # override" (a base card falls back to its env connection / base temp).
            if "provider_ref" in req.model_fields_set:
                ov.provider_ref = req.provider_ref or None
            if "temperature" in req.model_fields_set:
                ov.temperature = req.temperature
            if req.enable_thinking is not None:
                ov.enable_thinking = req.enable_thinking
            for field in ("rpm", "tpm"):
                if field in req.model_fields_set:
                    setattr(ov, field, getattr(req, field))
            if ov == ProfileOverride():
                s.models.profile_overrides.pop(name, None)
            else:
                s.models.profile_overrides[name] = ov

    # reload=True: clearing an override can only be undone by rebuilding the
    # base profile from env — plain replay would keep the mutated value.
    await settings_store.update(patch, reload=True)
    return models_view()


@router.post("/profiles")
async def create_profile(req: ProfileCreate):
    """Create a custom profile. Survives provider switches; deletable."""
    from searchos.config.settings import settings

    from api.settings_store import CustomProfile

    if not _PROFILE_NAME_RE.fullmatch(req.name):
        raise HTTPException(400, "Profile name must be alphanumeric with . _ - (max 64 chars)")
    if req.name in _RESERVED_PROFILE_NAMES:
        raise HTTPException(400, f"{req.name!r} is reserved for provider presets")
    if req.name in settings.profiles or req.name in store.models.custom_profiles:
        raise HTTPException(400, f"Profile {req.name!r} already exists")
    if not req.model.strip():
        raise HTTPException(400, "model is required")
    if req.provider_ref:
        if req.provider_ref not in store.models.provider_connections:
            raise HTTPException(400, f"Unknown provider connection: {req.provider_ref!r}")
    elif not _ENV_NAME_RE.fullmatch(req.api_key_env):
        # No connection → the inline api_key_env must be a real env var name.
        raise HTTPException(400, "Pick a provider connection, or give a valid api_key_env")

    def patch(s):
        s.models.custom_profiles[req.name] = CustomProfile(
            model=req.model.strip(), provider_ref=req.provider_ref or None,
            provider=req.provider,
            api_base=req.api_base.strip(),
            api_key_env=req.api_key_env or "OPENAI_API_KEY",
            temperature=req.temperature, enable_thinking=req.enable_thinking,
            thinking_style=req.thinking_style,
            rpm=req.rpm, tpm=req.tpm,
        )

    await settings_store.update(patch)
    return models_view()


@router.delete("/profiles/{name}")
async def delete_profile(name: str):
    """Delete a custom profile. Built-in/preset profiles can't be deleted."""
    from searchos.config.settings import settings

    if name not in store.models.custom_profiles:
        if name in settings.profiles:
            raise HTTPException(400, f"{name!r} is a built-in profile — only custom profiles can be deleted")
        raise HTTPException(404, f"Unknown profile: {name!r}")

    bound = sorted(role for role, profile in settings.roles.items() if profile == name)
    if bound:
        raise HTTPException(
            400, f"Profile {name!r} is bound to roles {bound} — rebind them first")

    def patch(s):
        s.models.custom_profiles.pop(name, None)
        s.models.profile_overrides.pop(name, None)
        s.models.roles = {r: p for r, p in s.models.roles.items() if p != name}

    await settings_store.update(patch, reload=True)
    return models_view()


@router.put("/provider-connections/{name}")
async def put_provider_connection(name: str, req: ProviderConnUpsert):
    """Create or update a user-defined provider connection. Model cards point at
    it by name; editing it re-flows to every card that references it."""
    from api.settings_store import ProviderConnection

    if not _PROFILE_NAME_RE.fullmatch(name):
        raise HTTPException(400, "Connection name must be alphanumeric with . _ - (max 64 chars)")
    if not req.api_key_envs:
        raise HTTPException(400, "At least one api_key_env is required")
    envs: list[str] = []
    for env in req.api_key_envs:
        if not _ENV_NAME_RE.fullmatch(env):
            raise HTTPException(400, f"api_key_env {env!r} must look like AN_ENV_VAR_NAME")
        if env not in envs:  # de-dup, keep order (first = default)
            envs.append(env)

    def patch(s):
        s.models.provider_connections[name] = ProviderConnection(
            protocol=req.protocol, api_base=req.api_base.strip(),
            api_key_envs=envs, thinking_style=req.thinking_style,
            label=req.label.strip(),
        )

    # reload so cards referencing this connection rebuild against its new fields.
    await settings_store.update(patch, reload=True)
    return models_view()


@router.delete("/provider-connections/{name}")
async def delete_provider_connection(name: str):
    """Delete a provider connection. Blocked while any model card references it."""
    if name not in store.models.provider_connections:
        raise HTTPException(404, f"Unknown provider connection: {name!r}")

    used = sorted(
        p for p, cp in store.models.custom_profiles.items() if cp.provider_ref == name
    ) + sorted(
        p for p, ov in store.models.profile_overrides.items() if ov.provider_ref == name
    )
    if used:
        raise HTTPException(
            400, f"Connection {name!r} is used by model cards {used} — repoint them first")

    def patch(s):
        s.models.provider_connections.pop(name, None)

    await settings_store.update(patch, reload=True)
    return models_view()


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
