# Configuration Layers

**English** | [简体中文](zh/configuration.md)

SearchOS separates configuration into two tracks: **secrets stay in `.env`,
while every other user-adjustable setting lives in the overlay
(`web_settings.json`)**. The overlay is the single user-configuration source
shared by the Web UI and CLI/TUI. It is applied last and therefore has the
highest priority.

```text
L5  Per-run request overrides   POST /api/search body (effort / max_time / skills)
L4  User settings overlay       web_settings.json — effort / skills / models /
                                run_defaults / advanced; shared by Web and TUI
L3  Explicit SF_* overrides     SF_PROFILES__* / SF_ROLES__* and similar values
                                from .env, merged recursively
L2  SF_PROVIDER preset          providers.py generates default profiles and roles
L1  Secrets in .env             *_API_KEY values loaded into the process environment
```

**Precedence:** code defaults → `SF_*` environment configuration (L2/L3) →
overlay (L4). The overlay wins when values conflict. `SF_*` variables remain
available for power users and backward compatibility, but the recommended
interfaces are `searchos --setup`, the Web settings page, and the TUI commands
`/effort`, `/skill`, `/search`, and `/config`.

## Layer responsibilities

| Layer | Written by | Read by | Read timing |
|---|---|---|---|
| L1 `.env` | Manual edits, `searchos --setup`, or the Web settings page (secret values only) | All processes through `load_dotenv` | Once at process startup |
| L2 presets | `SF_PROVIDER` environment variable | `config/providers.py` | When `Settings()` is constructed |
| L3 overrides | `SF_PROFILES__*` and related values in `.env` | The `config/settings.py` validator | When `Settings()` is constructed |
| L4 overlay | Web settings API, TUI commands, or the wizard (`web/api/settings_store.py` + `config/web_overlay.py`) | `load_and_apply()` and each settings update | At startup and after every write |
| L5 per-run | Run overrides in the Web Composer | `web/api/routes/search.py` | For each search request |

## The four overlay sections

- **effort** — budget preset (`low`, `medium`, `high`, or `max`) plus individual
  overrides for concurrency, iterations, searches and discoveries per agent,
  wall-clock limit, and Skill router top-k. See `EFFORT_KEYS` in
  `config/effort.py`.
- **skills** — `access_only`, `access_deny`, `strategy_deny`, and
  `orchestrator_deny`. The environment-level
  `SEARCHOS_SKILL_LAYERS_DISABLED` and `SEARCHOS_SKILL_ONLY` switches remain
  available for advanced debugging, but normal configuration belongs in the
  overlay or UI.
- **models** — provider connections, model cards (`custom_profiles` and
  `profile_overrides`), role bindings, `search_provider`, and
  `browser_backend`.
- **advanced** — first-class controls outside the effort presets, including
  `llm_max_retries`, `browser_disk_cache_dir`, and `https_proxy`.
  `https_proxy` is not a `settings` field: `apply_to_runtime()` exports it back
  to `HTTP_PROXY` and `HTTPS_PROXY` in `os.environ`, removing them when the
  value is empty. `search_max_results` belongs to `run_defaults`.

## Secret flow

- **`.env` stores secret values only**, including `*_API_KEY` and
  `RAGFLOW_USER_ID`. Manual edits, `searchos --setup`, and the Web settings
  endpoints (`PUT /api/settings/provider` and `PUT /api/settings/keys`) all use
  the atomic writer in `searchos/config/env_file.py`. It writes a temporary file
  and replaces the original while preserving comments.
- Proxy configuration is not treated as a secret. `PUT /api/settings/advanced`
  stores it in the overlay and exports it to the process environment at runtime.
- Environment-variable names written by the Web API must pass an allowlist
  assembled from provider/profile `api_key_env` values and search/browser keys.
  `validate_env_value` rejects newlines, quotes, and `#` to prevent `.env` line
  injection.
- API responses and logs never include secret values. They expose only booleans
  such as `key_set` or `api_key_set`. Proxy and cache-directory values are not
  secrets and remain visible and editable in the UI.
- Concurrent writes from separate TUI and Web processes are last-writer-wins.
  Within the Web process, one asyncio lock serializes updates.

## Migrating an older `.env`

At startup, `load_and_apply()` calls `migrate_legacy_env_into_overlay()`. It
non-destructively seeds legacy values such as `SF_ENABLE_SKILLS`,
`SF_SEARCH_PROVIDER`, `SF_BROWSER_DISK_CACHE_DIR`, and `HTTP(S)_PROXY` into
empty overlay fields. The migration is idempotent and preserves behavior.

Run `searchos --setup` again to remove migrated legacy lines explicitly after
confirmation. Because the overlay has higher priority, those old `.env` lines
are otherwise inactive in the Web UI.

## CLI/TUI and Web consistency

- Both CLI `_setup_provider` and Web `init_search_provider` read
  `models.search_provider` from the overlay. If it is absent, they fall back to
  `SF_SEARCH_PROVIDER`, infer a provider from available keys, and finally use
  the backward-compatible RagFlow default.
- TUI commands `/effort`, `/skill`, `/search`, `/model`, and `/config` update the
  overlay through `save_overlay()`. Their values survive restarts and remain in
  sync with the Web settings page.
- `/config` without arguments opens the interactive settings panel in
  `searchos/tui/config_modal.py`. It covers model role bindings, model cards,
  provider connections and keys, search and browser backends, proxy and cache
  settings, effort budgets, retries, and the runtime Skill switch. `/model`
  opens the Model section directly; `/config <item> <value>` remains available
  for quick edits.
- API keys entered in the TUI use the same atomic `.env` writer as the Web UI
  and setup wizard. The interface displays only whether each key is configured.

## When changes take effect

| Configuration | Read behavior | Effect of changing the environment at runtime |
|---|---|---|
| Model API key (`profile.api_key_env`) | `get_model_for()` reads `os.environ` for each call | Applies to new sessions immediately |
| `SERPER_API_KEY`, `TAVILY_API_KEY`, and `RAGFLOW_*` | Read whenever a search provider is constructed | Applies to the next search |
| `SF_PROVIDER`, `SF_MODEL`, `SF_API_BASE`, `SF_JINA_API_KEY`, and other `SF_*` values | The module-level `settings = Settings()` is an import-time snapshot | Requires `reload_settings_in_place()` |

Web settings endpoints update environment-backed configuration through the
`settings_store.update_env()` transaction:

```text
Inside the lock:
  update os.environ
  → construct Settings() as a dry run (roll back on failure)
  → atomically write .env
  → reload_settings_in_place()
  → reapply the L4 overlay
```

Reapplying L4 is essential because rebuilding the singleton would otherwise
replace Web-managed effort settings with their environment-level defaults.

Changing a provider preset also clears L4 role overrides and per-profile field
overrides whose profile names belong to the old preset. It removes stale
`SF_MODEL`, `SF_FAST_MODEL`, and `SF_API_BASE` overrides unless the request
supplies replacements. Running sessions are unaffected because a
`SearchSession` snapshots its model configuration when created.

L4 supports two forms of model customization:

- **Profile overrides** (`models.profile_overrides`) sparsely override `model`,
  `api_base`, or `api_key_env` on built-in profiles. These values do not use L3
  because environment-variable paths cannot address profile names containing
  dots, and stale values cannot be cleaned safely during preset switches.
- **Custom profiles** (`models.custom_profiles`) define a complete model,
  protocol, API base, and key variable. They survive provider switches and can
  bind to any role. `main`, `judge`, `fast`, `synthesis`, and `reformat` are
  reserved preset names.

## Related modules

- `searchos/config/settings.py` — `Settings` singleton and
  `reload_settings_in_place()`
- `searchos/config/profiles.py` — `ModelProfile`, `ROLE_NAMES`, and built-in
  profiles
- `searchos/config/providers.py` — `SF_PROVIDER` preset registry; see
  [Provider configuration](providers.md)
- `searchos/config/env_file.py` — atomic `.env` reads/writes, value validation,
  and `remove_env_keys`
- `searchos/config/web_overlay.py` — overlay model, `apply_to_runtime()`, and
  migration
- `searchos/config/effort.py` — effort presets shared by the TUI and Web UI
- `web/api/settings_store.py` — L4 write transaction, validation rollback, and
  overlay replay
- `web/api/routes/models.py` and `routes/settings.py` — settings API endpoints
