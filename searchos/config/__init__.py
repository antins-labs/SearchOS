"""SearchOS configuration: single-source settings + LLM factory.

Exports are lazy: ``settings`` is a singleton constructed from environment
variables at first import, and the first-run setup wizard
(``config.setup_wizard``) must be able to run — and mutate ``os.environ`` —
before that happens. Eager imports here would construct it too early.
"""

from typing import Any

_SETTINGS_EXPORTS = {
    "AGENT_BUDGET_OVERRIDES", "ROLE_NAMES", "ModelProfile", "Settings", "settings",
}
_MODELS_EXPORTS = {"get_model_for", "resolve_profile"}

__all__ = sorted(_SETTINGS_EXPORTS | _MODELS_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _SETTINGS_EXPORTS:
        from searchos.config import settings as _settings_mod
        return getattr(_settings_mod, name)
    if name in _MODELS_EXPORTS:
        from searchos.config import models as _models_mod
        return getattr(_models_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
