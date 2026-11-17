"""SkillRegistry: load and index runtime-enabled Skills."""

from __future__ import annotations

import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path

from searchos.skills.core.models import (
    Skill,
    SkillAvailability,
    SkillCategory,
)
from searchos.skills.core.skill_markdown import parse_skill_file
from searchos.skills.names import canonical_skill_name, canonical_skill_names

# Skills disabled everywhere: hidden from the catalog here and rejected at
# dispatch time in orchestrator_tools.py. Re-enable by removing from this set.
SKILL_BLACKLIST: frozenset[str] = frozenset({
    # Triggers redundant "verify via another source" loops whose search-budget
    # cost consistently outweighs the catch rate.
    "multi_source_verification", "multi-source-verification",
})

logger = logging.getLogger(__name__)


def _directory_snapshot(directory: Path) -> tuple[str, dict[Path, str], dict[Path, Path]]:
    """一次元数据扫描同时计算目录与各技能包的失效签名。"""
    digests = {}
    entries: dict[Path, Path] = {}
    for root, directories, files in os.walk(directory):
        directories[:] = sorted(d for d in directories if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            if name.startswith("."):
                continue
            path = Path(root) / name
            stat = path.stat()
            identity = str((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)).encode()
            parent = path.parent
            if name in {"SKILL.md", "skill.md"} and (parent not in entries or name == "SKILL.md"):
                entries[parent] = path
            while True:
                digest = digests.setdefault(parent, hashlib.sha256())
                digest.update(str(path.relative_to(parent)).encode())
                digest.update(identity)
                if parent == directory:
                    break
                parent = parent.parent
    signatures = {path: digest.hexdigest() for path, digest in digests.items()}
    return signatures.get(directory, hashlib.sha256().hexdigest()), signatures, entries


@lru_cache(maxsize=2048)
def _parsed_skill(path: str, signature: str) -> Skill:
    return parse_skill_file(Path(path))


def _env_excluded() -> set[str]:
    raw = os.environ.get("SEARCHOS_SKILL_EXCLUDE", "")
    return {n.strip() for n in raw.split(",") if n.strip()}


def _env_only() -> set[str] | None:
    """Optional whitelist. When set, ONLY these skill names load.

    - ``SEARCHOS_SKILL_ONLY=a,b,c`` — load only a/b/c
    - unset or empty — no whitelist, all non-excluded skills load

    Related: ``SEARCHOS_SKILL_LAYERS_DISABLED=access,strategy`` drops a
    whole folder. ``SEARCHOS_SKILLS_DISABLED=1`` kills everything.
    """
    raw = os.environ.get("SEARCHOS_SKILL_ONLY", "")
    names = {n.strip() for n in raw.split(",") if n.strip()}
    return names or None


def _env_all_disabled() -> bool:
    """``SEARCHOS_SKILLS_DISABLED=1`` one-shot kill switch."""
    return os.environ.get(
        "SEARCHOS_SKILLS_DISABLED",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}


def _env_disabled_layers() -> set[str]:
    """``SEARCHOS_SKILL_LAYERS_DISABLED=access,strategy`` — drop a whole
    folder's skills in one shot. Values match the top-level subdirectory
    under the skill library (``access`` / ``strategy``)."""
    raw = os.environ.get("SEARCHOS_SKILL_LAYERS_DISABLED", "")
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


class SkillRegistry:
    """In-memory registry of runtime-enabled Skills.

    Responsibilities:
    - Load skills from a directory of Markdown files
    - Apply global, layer, name, and Skill Availability filters
    - Index enabled Skills by name and category

    Disabled Skills remain on disk but never enter the runtime registry.
    """

    def __init__(
        self,
        excluded: list[str] | set[str] | None = None,
        *,
        only: list[str] | set[str] | None = None,
        all_disabled: bool | None = None,
        disabled_layers: list[str] | set[str] | None = None,
    ) -> None:
        self.diagnostics: list[str] = []
        self._skills: dict[str, Skill] = {}  # name → Skill
        self.discovery_cache: dict[tuple, list[dict]] = {}
        self._dir_mtime_cache: dict[str, tuple[str, int]] = {}
        self._excluded: set[str] = canonical_skill_names(set(excluded or set()) | _env_excluded())
        # Whitelist — arg wins, else env var, else None (no filter).
        env_only = _env_only()
        self._only: set[str] | None = (
            canonical_skill_names(only) if only is not None else (canonical_skill_names(env_only) if env_only is not None else None)
        )
        # All-disabled kill switch. Arg wins over env.
        self._all_disabled: bool = (
            all_disabled if all_disabled is not None else _env_all_disabled()
        )
        # Layer-level kill switch. Names match folder under the library
        # root (``access`` / ``strategy``). Arg wins over env.
        self._disabled_layers: set[str] = (
            {n.lower() for n in disabled_layers}
            if disabled_layers is not None
            else _env_disabled_layers()
        )

    def set_excluded(self, names: list[str] | set[str]) -> None:
        """Replace the exclude list. Use to hot-disable misbehaving skills."""
        self._excluded = canonical_skill_names(names)
        for n in list(self._skills.keys()):
            if canonical_skill_name(n) in self._excluded:
                del self._skills[n]
        self._dir_mtime_cache.clear()

    def add_excluded(self, name: str) -> None:
        self._excluded.add(canonical_skill_name(name))
        self._skills.pop(name, None)
        self._skills.pop(canonical_skill_name(name), None)
        self._dir_mtime_cache.clear()

    def set_only(self, names: list[str] | set[str] | None) -> None:
        """Replace the whitelist. ``None`` clears it (all skills allowed).
        Drops already-loaded skills not in the new whitelist."""
        self._only = canonical_skill_names(names) if names is not None else None
        if self._only is not None:
            for n in list(self._skills.keys()):
                if canonical_skill_name(n) not in self._only:
                    del self._skills[n]
        self._dir_mtime_cache.clear()

    def set_disabled_layers(self, layers: list[str] | set[str] | None) -> None:
        """Replace the disabled-layer set. Drops already-loaded skills whose
        layer is now disabled. ``None`` clears (no layer disabled)."""
        self._disabled_layers = {n.lower() for n in (layers or set())}
        for n in list(self._skills.keys()):
            layer_val = self._skills[n].meta.category
            if layer_val is not None and layer_val.value in self._disabled_layers:
                del self._skills[n]
        self._dir_mtime_cache.clear()

    def set_all_disabled(self, flag: bool) -> None:
        """Kill switch — drops ALL loaded skills when True."""
        self._all_disabled = bool(flag)
        if self._all_disabled:
            self._skills.clear()
            self._dir_mtime_cache.clear()

    def _is_blocked(self, name: str) -> bool:
        """Return True if ``name`` should NOT be loaded.

        Priority: all_disabled > not-in-only > in-excluded.
        """
        name = canonical_skill_name(name)
        if self._all_disabled:
            return True
        if self._only is not None and name not in self._only:
            return True
        if name in self._excluded:
            return True
        return False

    @property
    def excluded(self) -> set[str]:
        return set(self._excluded)

    @property
    def only(self) -> set[str] | None:
        return set(self._only) if self._only is not None else None

    @property
    def all_disabled(self) -> bool:
        return self._all_disabled

    @property
    def disabled_layers(self) -> set[str]:
        return set(self._disabled_layers)

    # --- Loading ---

    @staticmethod
    def _directory_signature(directory: Path) -> str:
        return _directory_snapshot(directory)[0]

    def load_directory(
        self,
        directory: str | Path,
        *,
        force: bool = False,
    ) -> int:
        """Load skills from a directory. Supports two layouts:

        1. Folder-per-skill (v2): ``skill_name/skill.md``
        2. Flat files (v1): ``category/skill_name.md``

        When package contents are unchanged, the cached load count is returned
        without re-parsing. Resource changes and deletions invalidate it.

        Pass ``force=True`` to bypass the cache (e.g. after Evolver writes a
        new skill and the caller wants the registry to immediately see it).
        """
        directory = Path(directory)
        cache_key = str(directory.resolve()) if directory.exists() else str(directory)
        current_sig, package_signatures, entries = _directory_snapshot(directory)

        cached = self._dir_mtime_cache.get(cache_key)
        if not force and cached is not None and cached[0] == current_sig:
            logger.debug(
                "Skill library %s unchanged (mtime=%s) — reusing cached %d skills",
                directory, current_sig, cached[1],
            )
            return cached[1]

        # Drop previous entries originating in this root, including deleted packages.
        for name, skill in list(self._skills.items()):
            if skill.file_path and Path(skill.file_path).resolve().is_relative_to(directory.resolve()):
                del self._skills[name]
        count = 0
        for sub in sorted(entries.values()):
            try:
                skill = (
                    parse_skill_file(sub) if force
                    else _parsed_skill(str(sub.resolve()), package_signatures[sub.parent])
                ).model_copy(deep=True)
                if self._is_blocked(skill.meta.name):
                    logger.info("Skipping blocked skill: %s", skill.meta.name)
                    continue
                if skill.meta.availability is SkillAvailability.DISABLED:
                    logger.info("Skipping disabled skill: %s", skill.meta.name)
                    continue
                # Auto-detect layer from directory path
                rel = sub.relative_to(directory)
                parts = rel.parts
                if len(parts) >= 2 and parts[0] in ("strategy", "access", "orchestrator"):
                    skill.meta.category = SkillCategory(parts[0])
                if skill.package_format == "legacy" and skill.meta.category == SkillCategory.ACCESS:
                    logger.warning("Skipping Access Skill without SKILL.md: %s", sub)
                    continue
                if (
                    skill.meta.category is not None
                    and skill.meta.category.value in self._disabled_layers
                ):
                    logger.info(
                        "Skipping skill %s — layer %s disabled",
                        skill.meta.name, skill.meta.category.value,
                    )
                    continue
                if self._is_blocked(skill.meta.name):
                    continue
                existing = self._skills.get(skill.meta.name)
                if existing is not None and existing.file_path != skill.file_path:
                    message = f"Skill name conflict: {skill.meta.name}: {existing.file_path} vs {skill.file_path}"
                    self.diagnostics.append(message)
                    logger.error(message)
                    continue
                self._skills[skill.meta.name] = skill
                count += 1
            except Exception:
                logger.warning("Failed to parse skill: %s", sub, exc_info=True)

        self._dir_mtime_cache[cache_key] = (current_sig, count)
        logger.info("Loaded %d skills from %s", count, directory)
        return count

    # --- Query ---

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name) or self._skills.get(canonical_skill_name(name))

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[Skill]:
        return [s for s in self._skills.values() if s.meta.category == category]

    # --- Registration ---

    def register(self, skill: Skill) -> None:
        """Add or replace a skill in the registry."""
        if skill.meta.availability is SkillAvailability.DISABLED:
            logger.info("Refusing to register disabled skill: %s", skill.meta.name)
            return
        if self._is_blocked(skill.meta.name):
            logger.info("Refusing to register blocked skill: %s", skill.meta.name)
            return
        existing = self._skills.get(skill.meta.name)
        if existing and existing.file_path != skill.file_path:
            raise ValueError(f"Skill name conflict: {skill.meta.name}")
        if skill.meta.category.value in self._disabled_layers:
            return
        self._skills[skill.meta.name] = skill
        self._dir_mtime_cache.clear()
        logger.info("Registered skill: %s", skill.meta.name)

    def generate_catalog(
        self,
        access_allow: set[str] | None = None,
        strategy_allow: set[str] | None = None,
    ) -> str:
        """Generate a compact skill catalog for LLM consumption.

        ``access_allow``: when set, list only access skills named in it (the
        caller's explicit filter). ``strategy_allow``: when set, list
        only strategy skills named in it (the ``/skill`` picker's unchecked
        set subtracted); ``None`` keeps all strategy skills.

        Lists strategy and access skills available to retrieval agents.
        The playbook router supplies orchestrator skills separately.
        """
        access_allow = canonical_skill_names(access_allow) if access_allow is not None else None
        strategy_allow = canonical_skill_names(strategy_allow) if strategy_allow is not None else None
        selectable: list[Skill] = []

        for skill in sorted(self._skills.values(), key=lambda s: s.meta.name):
            if skill.meta.name in SKILL_BLACKLIST:
                continue
            if skill.meta.category == SkillCategory.ORCHESTRATOR:
                continue
            if (
                access_allow is not None
                and skill.meta.category == SkillCategory.ACCESS
                and skill.meta.name not in access_allow
            ):
                continue
            if (
                strategy_allow is not None
                and skill.meta.category == SkillCategory.STRATEGY
                and skill.meta.name not in strategy_allow
            ):
                continue
            selectable.append(skill)

        lines = [
            f"[Available retrieval skills: {len(selectable)}]",
        ]
        for skill in selectable:
            desc = skill.meta.description or skill.meta.trigger or "(no description)"
            desc_short = desc.replace("\n", " ")
            lines.append(f"- **{skill.meta.name}**: {desc_short}")

        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._skills)
