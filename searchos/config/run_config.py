"""Immutable task-local settings shared by search tools and middleware."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class EffectiveRunConfig:
    enable_web_image_read: bool
    web_image_read_mode: Literal["auto", "native", "vision"]
    jina_retain_images: Literal["alt", "all"]
    explore_max_waves: int
    source: Literal["product", "eval"] = "product"
    explore_on_start: bool = False

    @classmethod
    def from_settings(cls, *, for_eval: bool = False) -> EffectiveRunConfig:
        from searchos.config.settings import settings

        return cls(
            enable_web_image_read=False if for_eval else settings.enable_web_image_read,
            web_image_read_mode="auto" if for_eval else settings.web_image_read_mode,
            jina_retain_images="alt" if for_eval else settings.effective_jina_retain_images(),
            explore_max_waves=settings.explore_max_waves,
            source="eval" if for_eval else "product",
            explore_on_start=for_eval and settings.enable_explore,
        )

    def snapshot(self) -> dict[str, object]:
        return asdict(self)


_active: ContextVar[EffectiveRunConfig | None] = ContextVar(
    "searchos_effective_run_config", default=None,
)


def current_run_config() -> EffectiveRunConfig:
    return _active.get() or EffectiveRunConfig.from_settings()


@contextmanager
def activate_run_config(config: EffectiveRunConfig) -> Iterator[None]:
    token = _active.set(config)
    try:
        yield
    finally:
        _active.reset(token)
