"""Web-side persistence for the settings overlay.

The overlay DATA MODEL and the read/apply path live in
``searchos.config.web_overlay`` (shared with the CLI/TUI, which apply the same
overlay read-only). This module re-exports those and adds the WRITE path the
web app needs: atomic saves, the async lock, and .env-backed key/provider
edits. Sparse semantics throughout: ``None`` / absent means "no override, env
base wins". Secrets NEVER live here — only env var NAMES; the values stay in
.env. The file sits next to ``.env`` at the repo root (``web_settings.json``,
override with ``SF_WEB_SETTINGS_PATH``).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

# The data model + read/apply path are owned by searchos.config so both the web
# app and the CLI share one implementation. Re-exported so existing web imports
# (``from api.settings_store import store`` / ``ProviderConnection`` / …) keep
# working unchanged.
from searchos.config.web_overlay import (  # noqa: F401
    DEFAULT_PROVIDER_CONNECTIONS,
    CustomProfile,
    EffortLevel,
    EffortOverlay,
    ModelsOverlay,
    ProfileOverride,
    ProviderConnection,
    RunDefaults,
    SkillsOverlay,
    WebSettings,
    _replace_store,
    _seed_default_connections,
    apply_to_runtime,
    load_and_apply,
    overlay_path,
    save_overlay as save,  # web calls settings_store.save(); shared atomic writer
    store,
)

_LOCK = asyncio.Lock()


def _path() -> Path:
    return overlay_path()


async def update(patch_fn, reload: bool = False) -> WebSettings:
    """Mutate the store under the lock, apply to runtime, persist atomically.

    ``patch_fn(store)`` mutates in place; validation errors raised inside it
    propagate before anything is saved. ``reload=True`` rebuilds the settings
    singleton from env before replaying the overlay — required whenever the
    patch REMOVES an override (plain replay can't restore the base value).
    """
    from searchos.config.settings import reload_settings_in_place

    async with _LOCK:
        patch_fn(store)
        if reload:
            reload_settings_in_place()
        apply_to_runtime()
        save()
        return store


async def update_env(env_updates: dict[str, str], patch_fn=None) -> None:
    """Write env vars (keys / provider knobs) through to .env and the runtime.

    Full transaction under the lock:
      1. update os.environ first (empty value → pop)
      2. dry-run ``Settings()`` — an invalid combination (e.g. a local preset
         without SF_MODEL) raises BEFORE anything touches disk; the previous
         os.environ values are restored on failure
      3. atomic .env write
      4. rebuild the settings singleton in place from the new env
      5. optional store patch (e.g. clearing role overrides), then re-apply
         the web overlay — reload resets effort knobs etc. to env defaults,
         so this replay is mandatory, not an optimization
    Never log values here — key material must not reach any log line.
    """
    from searchos.config import env_file
    from searchos.config.settings import Settings, reload_settings_in_place

    from api import deps

    async with _LOCK:
        prev = {k: os.environ.get(k) for k in env_updates}
        try:
            for key, value in env_updates.items():
                if value:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
            fresh = Settings()  # dry-run against the new env
        except Exception:
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            raise

        env_file.update_env_file(Path(deps.ENV_FILE_PATH), env_updates)
        reload_settings_in_place(fresh)
        if patch_fn is not None:
            patch_fn(store)
        apply_to_runtime()
        save()


def reset() -> None:
    """Delete the overlay file and restore the pure env-based settings.

    Both singletons must be mutated IN PLACE — every module holds a reference
    to the same objects, so swapping them out would leave stale copies behind.
    """
    _path().unlink(missing_ok=True)
    _replace_store(WebSettings())

    from searchos.config.settings import reload_settings_in_place
    reload_settings_in_place()
