"""Parse Skill Markdown files: YAML frontmatter + body."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from searchos.skills.core.models import Skill, SkillCategory, SkillMeta

# Matches YAML frontmatter between --- delimiters
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Matches ```yaml/```markdown/``` code fence (LLM-generated skills use various fences)
_CODEFENCE_RE = re.compile(r"^```(?:ya?ml|markdown)?\s*\n(.*?)\n```\s*\n", re.DOTALL)


def _normalize_frontmatter(text: str) -> str:
    """Strip a leading code fence line so the standard ``---`` parser can work.

    LLM-generated skills produce various formats:
      ```yaml\\n---\\nname: foo\\n---\\n```  (fence wrapping frontmatter)
      ```markdown\\n---\\nname: foo\\n---\\n...body...\\n```  (fence wrapping entire file)

    Strategy: just strip the opening fence line. The ``---`` frontmatter
    parser handles the rest. Don't try to match the closing fence — it may
    be at the very end of the file or interleaved with code blocks.
    """
    stripped = text.lstrip()
    if re.match(r"^```\w*\s*$", stripped.split("\n", 1)[0]):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
    return stripped


def parse_skill_file(path: str | Path) -> Skill:
    """Read a Markdown skill file and return a ``Skill`` object.

    Supports both flat files (skill.md) and folder structure
    (skill_name/skill.md). Handles standard ``---`` frontmatter and
    LLM-generated `` ```yaml `` fences.

    When a sibling ``anti_patterns.md`` exists in the same directory,
    its contents are parsed into ``skill.anti_patterns_index`` (for
    cheap system-prompt injection) and ``skill.anti_patterns_details``
    (fetched on demand by sub-agents).
    """
    path = Path(path)
    if path.is_dir():
        skill_md = path / "skill.md"
        if skill_md.exists():
            path = skill_md
        else:
            raise ValueError(f"No skill.md found in directory: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        skill = parse_skill_text(text, file_path=str(path))
    except ValueError:
        # Access skills are defined by a sibling ``manifest.yaml``; their
        # skill.md is human documentation and carries no frontmatter.
        # Synthesize the metadata from the manifest rather than failing.
        manifest = path.parent / "manifest.yaml"
        if not manifest.exists():
            raise
        skill = _skill_from_manifest(manifest, body=text, file_path=str(path))
    _attach_anti_patterns(skill, path.parent)
    return skill


def _skill_from_manifest(manifest_path: Path, *, body: str, file_path: str) -> Skill:
    """Build a Skill for an access skill defined by ``manifest.yaml``.

    The directory name is the canonical skill identifier — it matches the
    ``skill_<name>`` typed-tool naming and the access-skill baker's layout;
    the manifest only supplies the one-line catalog description.
    """
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    desc_lines = str(data.get("description") or "").strip().splitlines()
    meta = SkillMeta(
        name=manifest_path.parent.name,
        description=desc_lines[0] if desc_lines else "",
        category=SkillCategory.ACCESS,
    )
    return Skill(meta=meta, body=body.strip(), file_path=file_path)


def _attach_anti_patterns(skill: Skill, skill_dir: Path) -> None:
    """Populate ``anti_patterns_*`` fields from sibling ``anti_patterns.md``.

    Silent on missing file (normal for skills without recorded failures)
    and on parse errors (logged). Never raises — a malformed anti file
    must not break skill loading.
    """
    ap_path = skill_dir / "anti_patterns.md"
    if not ap_path.exists():
        return
    try:
        from searchos.skills.core.anti_patterns import (
            index_markdown,
            parse_anti_patterns_md,
        )
        text = ap_path.read_text(encoding="utf-8")
        _name, entries = parse_anti_patterns_md(text)
        if not entries:
            return
        skill.anti_patterns_index = index_markdown(entries)
        skill.anti_patterns_details = [
            {
                "name": e.name,
                "summary": e.summary,
                "what_failed": e.what_failed,
                "why": e.why,
                "instead": e.instead,
                "observed": e.observed,
                "last_seen": e.last_seen,
                "source": e.source,
            }
            for e in entries
        ]
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "anti_patterns.md parse failed for %s", skill_dir, exc_info=True,
        )


def parse_skill_text(text: str, *, file_path: str = "") -> Skill:
    """Parse skill from raw Markdown text."""
    text = _normalize_frontmatter(text)

    match = _FRONTMATTER_RE.match(text)
    if not match:
        # Fallback: try treating everything before the first markdown heading
        # as YAML (handles ```yaml ... ``` without --- delimiters inside)
        heading_pos = re.search(r"\n#\s", text)
        if heading_pos:
            candidate = text[:heading_pos.start()].strip()
            # Remove trailing ``` from stripped code fence
            candidate = re.sub(r"```\s*$", "", candidate).strip()
            try:
                raw = yaml.safe_load(candidate)
                if isinstance(raw, dict) and ("name" in raw or "skill_name" in raw):
                    meta = SkillMeta.model_validate(raw)
                    body = text[heading_pos.start():].strip()
                    return Skill(meta=meta, body=body, file_path=file_path)
            except Exception:
                pass
        raise ValueError(f"No YAML frontmatter found in skill file: {file_path}")

    raw_meta = yaml.safe_load(match.group(1))
    if not isinstance(raw_meta, dict):
        raise ValueError(f"Frontmatter is not a mapping in: {file_path}")

    meta = SkillMeta.model_validate(raw_meta)
    body = text[match.end():].strip()

    return Skill(meta=meta, body=body, file_path=file_path)
