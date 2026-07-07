"""SkillRegistry: load, index, and manage skill lifecycle."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from searchos.skills.core.models import Skill, SkillCategory, SkillStatus
from searchos.skills.core.schema import parse_skill_file


# Skills disabled everywhere: hidden from the catalog here and rejected at
# dispatch time in orchestrator_tools.py. Re-enable by removing from this set.
SKILL_BLACKLIST: frozenset[str] = frozenset({
    # Triggers redundant "verify via another source" loops whose search-budget
    # cost consistently outweighs the catch rate.
    "multi_source_verification",
})

logger = logging.getLogger(__name__)


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
    return os.environ.get("SEARCHOS_SKILLS_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _env_disabled_layers() -> set[str]:
    """``SEARCHOS_SKILL_LAYERS_DISABLED=access,strategy`` — drop a whole
    folder's skills in one shot. Values match the top-level subdirectory
    under the skill library (``access`` / ``strategy``)."""
    raw = os.environ.get("SEARCHOS_SKILL_LAYERS_DISABLED", "")
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


class SkillRegistry:
    """In-memory registry of all known skills.

    Responsibilities:
    - Load skills from a directory of Markdown files
    - Index by category, type, status
    - Lifecycle transitions (seed → trial → active → optimized → deprecated)

    v1 is load-only: the Beta(alpha, beta) frontmatter write-back lives in the
    offline evolver, not here.
    """

    def __init__(
        self,
        excluded: list[str] | set[str] | None = None,
        *,
        only: list[str] | set[str] | None = None,
        all_disabled: bool | None = None,
        disabled_layers: list[str] | set[str] | None = None,
    ) -> None:
        self._skills: dict[str, Skill] = {}  # name → Skill
        self._dir_mtime_cache: dict[str, tuple[float, int]] = {}
        self._excluded: set[str] = set(excluded or set()) | _env_excluded()
        # Whitelist — arg wins, else env var, else None (no filter).
        env_only = _env_only()
        self._only: set[str] | None = (
            set(only) if only is not None else env_only
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
        self._excluded = set(names)
        for n in list(self._skills.keys()):
            if n in self._excluded:
                del self._skills[n]
        self._dir_mtime_cache.clear()

    def add_excluded(self, name: str) -> None:
        self._excluded.add(name)
        self._skills.pop(name, None)
        self._dir_mtime_cache.clear()

    def set_only(self, names: list[str] | set[str] | None) -> None:
        """Replace the whitelist. ``None`` clears it (all skills allowed).
        Drops already-loaded skills not in the new whitelist."""
        self._only = set(names) if names is not None else None
        if self._only is not None:
            for n in list(self._skills.keys()):
                if n not in self._only:
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
    def _directory_signature(directory: Path) -> float:
        """Walk directory once and return max(mtime) over all skill.md files.

        Cheaper than hashing; detects add / edit / rename (but not pure delete
        of a single file — delete is rare enough that force=True callers cover
        it). Returns 0 for a missing dir.
        """
        if not directory.exists():
            return 0.0
        latest = 0.0
        for p in directory.rglob("skill.md"):
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                continue
        return latest

    def load_directory(
        self,
        directory: str | Path,
        *,
        force: bool = False,
    ) -> int:
        """Load skills from a directory. Supports two layouts:

        1. Folder-per-skill (v2): ``skill_name/skill.md``
        2. Flat files (v1): ``category/skill_name.md``

        When the directory's latest skill.md mtime is unchanged since the last
        call, the cached load count is returned without re-parsing (big win
        for benchmark loops that re-instantiate the harness per query).

        Pass ``force=True`` to bypass the cache (e.g. after Evolver writes a
        new skill and the caller wants the registry to immediately see it).
        """
        directory = Path(directory)
        cache_key = str(directory.resolve()) if directory.exists() else str(directory)
        current_sig = self._directory_signature(directory)

        cached = self._dir_mtime_cache.get(cache_key)
        if not force and cached is not None and cached[0] == current_sig:
            logger.debug(
                "Skill library %s unchanged (mtime=%s) — reusing cached %d skills",
                directory, current_sig, cached[1],
            )
            return cached[1]

        count = 0
        for sub in sorted(directory.rglob("skill.md")):
            # Skip hidden staging/backup dirs (e.g. an access-skill build in
            # progress) — they are not installed skills.
            if any(p.startswith(".") for p in sub.relative_to(directory).parts[:-1]):
                continue
            try:
                skill = parse_skill_file(sub)
                if self._is_blocked(skill.meta.name):
                    logger.info("Skipping blocked skill: %s", skill.meta.name)
                    continue
                # Auto-detect layer from directory path
                rel = sub.relative_to(directory)
                parts = rel.parts
                if len(parts) >= 2 and parts[0] in ("strategy", "access", "orchestrator"):
                    skill.meta.category = SkillCategory(parts[0])
                # Access-skill identity is its directory name — it matches the
                # ``skill_<name>`` typed tool and the baker's layout. Override
                # any stray skill.md frontmatter name so the two never diverge.
                if skill.meta.category == SkillCategory.ACCESS:
                    skill.meta.name = sub.parent.name
                if (
                    skill.meta.category is not None
                    and skill.meta.category.value in self._disabled_layers
                ):
                    logger.info(
                        "Skipping skill %s — layer %s disabled",
                        skill.meta.name, skill.meta.category.value,
                    )
                    continue
                executor_path = sub.parent / "executor.py"
                if executor_path.exists():
                    skill.meta.has_executor = True
                self._skills[skill.meta.name] = skill
                count += 1
            except Exception:
                logger.warning("Failed to parse skill: %s", sub, exc_info=True)

        self._dir_mtime_cache[cache_key] = (current_sig, count)
        logger.info("Loaded %d skills from %s", count, directory)
        return count

    # --- Query ---

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[Skill]:
        return [s for s in self._skills.values() if s.meta.category == category]

    def list_active(self) -> list[Skill]:
        """Return skills with status active or optimized."""
        active_statuses = {SkillStatus.ACTIVE, SkillStatus.OPTIMIZED}
        return [s for s in self._skills.values() if s.meta.status in active_statuses]

    # --- Registration ---

    def register(self, skill: Skill) -> None:
        """Add or replace a skill in the registry."""
        if self._is_blocked(skill.meta.name):
            logger.info("Refusing to register blocked skill: %s", skill.meta.name)
            return
        self._skills[skill.meta.name] = skill
        logger.info("Registered skill: %s (status=%s)", skill.meta.name, skill.meta.status.value)

    def generate_catalog(
        self,
        access_allow: set[str] | None = None,
        strategy_allow: set[str] | None = None,
    ) -> str:
        """Generate a compact skill catalog for LLM consumption.

        ``access_allow``: when set, list only access skills named in it (the
        ``skill_router`` top-k pre-filter). ``strategy_allow``: when set, list
        only strategy skills named in it (the ``/skill`` picker's unchecked
        set subtracted); ``None`` keeps all strategy skills.

        Lists **selectable** skills the orchestrator may pass in
        ``skills=[...]`` when dispatching a sub-agent — strategy skills
        (methodology folded into the agent's prompt) and access skills
        (turned into typed ``skill_<name>`` tools by ``render_skill_sets``
        for that dispatch). Only the dispatched names are injected; the
        rest stay discoverable via ``list_skills`` / ``load_skill``.

        Orchestrator-layer skills are excluded — they go into the
        orchestrator's own prompt via the playbook router, never into a
        sub-agent's ``skills=[...]``.
        """
        selectable: list[Skill] = []

        for skill in sorted(self._skills.values(), key=lambda s: s.meta.name):
            if skill.meta.name in SKILL_BLACKLIST:
                continue
            # Orchestrator-layer skills are injected into the orchestrator's
            # own system prompt via the playbook router — they are never
            # passed in `skills=[...]` to a sub-agent. Hide from this catalog
            # so the orchestrator doesn't accidentally forward the name.
            if skill.meta.category == SkillCategory.ORCHESTRATOR:
                continue
            if skill.meta.status == SkillStatus.DEPRECATED:
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
            f"[Selectable skills — {len(selectable)} | pass these names in `skills=[...]`]",
        ]
        for skill in selectable:
            desc = skill.meta.description or skill.meta.trigger or "(no description)"
            desc_short = desc.replace("\n", " ")[:100]
            lines.append(f"- **{skill.meta.name}**: {desc_short}")

        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._skills)
