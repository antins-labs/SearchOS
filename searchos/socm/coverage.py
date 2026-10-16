"""SOCM · Coverage Map — entity × attribute fill tracker (paper §Coverage Map).

Multi-table: ``tables`` keyed by table_id; cell keys are
``"{table_id}/{entity}.{attribute}"``. Single-table mode uses table_id="_default".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field, computed_field

from searchos.socm.evidence import EvidenceComparison, EvidenceNode, EvidenceStatus
from searchos.util.base_model import CamelModel

if TYPE_CHECKING:
    from searchos.socm.state import SearchState


class CellStatus(str, Enum):
    MISSING = "missing"
    FILLED = "filled"
    UNCERTAIN = "uncertain"
    HARD_CELL = "hard_cell"  # confirmed unreachable


class ColumnCheck(CamelModel):
    """Machine-checkable admission rule for a column — only trivially
    mechanical constraints (numeric range, closed value set); semantic ones
    stay in ColumnDesc.desc prose. Violating rows are rejected at ingest."""
    min: float | None = None
    max: float | None = None
    enum: list[str] | None = None

    def violation(self, value: Any) -> str | None:
        """Reason string if ``value`` violates this check, else None.
        Lists are checked element-wise; null-ish values never violate."""
        if value is None:
            return None
        items = value if isinstance(value, (list, tuple)) else [value]
        for item in items:
            s = str(item).strip()
            if not s or s.lower() in ("null", "none", "n/a"):
                continue
            if self.enum is not None:
                allowed = {str(e).strip().lower() for e in self.enum}
                if s.lower() not in allowed:
                    return f"{s!r} not in enum {self.enum}"
                continue
            if self.min is None and self.max is None:
                continue
            try:
                num = float(s.replace(",", "").replace("%", ""))
            except ValueError:
                return f"{s!r} is not numeric (column has a min/max check)"
            if self.min is not None and num < self.min:
                return f"{s} < min {self.min:g}"
            if self.max is not None and num > self.max:
                return f"{s} > max {self.max:g}"
        return None


class ColumnDesc(CamelModel):
    """Per-column: data type + semantic clarification."""
    type: str = "str"     # str | int | float | date | list[str] | ...
    desc: str = ""        # format constraint + semantic clarification
    check: ColumnCheck | None = None


class CoverageCell(CamelModel):
    """One cell (entity × attribute). Holds the set of supporting evidence
    ids — not a single canonical value; the synthesizer reads all findings
    and decides how to render. ``status`` derives from best alignment seen;
    ``display_hint`` is a short cached snippet for live summaries;
    ``full_value`` preserves the selected projection for tools and exports."""

    status: CellStatus = CellStatus.MISSING
    supporting_evidence_ids: list[str] = []
    best_alignment: str = ""           # full | partial | loose | ""
    best_confidence: float = 0.0       # confidence of the display_hint winner
    best_tier: int = 1                 # provenance tier of winner (2 anchored / 1 page / 0 derived)
    has_conflict: bool = False
    display_hint: str = ""
    full_value: str | None = None
    primary_evidence_id: str = ""
    conflict_evidence_ids: list[str] = Field(default_factory=list)
    conflict_history_evidence_ids: list[str] = Field(default_factory=list)
    conflict_status: Literal["clear", "pending", "uncertain", "confirmed"] = "clear"

    @computed_field  # type: ignore[misc]
    @property
    def value(self) -> str:
        return self.full_value if self.full_value is not None else self.display_hint


class CellEvidenceBinding(CamelModel):
    """一条事实在一个单元格中的投影；状态仅作用于该用途。"""

    evidence_id: str
    value: str
    alignment: str = "full"
    status: EvidenceStatus = EvidenceStatus.ACTIVE


class SchemaMode(str, Enum):
    # 初始化模式影响抽取规划；新增行始终先完成身份校验。
    CLOSED = "closed"           # seeded upfront, still grows
    COLUMN_ONLY = "column_only" # unseeded, rows discovered from scratch


class TableSchema(CamelModel):
    table_id: str = ""
    table_label: str = ""
    entities: list[str] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)
    column_desc: dict[str, ColumnDesc] = Field(default_factory=dict)
    schema_mode: SchemaMode = SchemaMode.CLOSED
    primary_key: list[str] = Field(default_factory=list)
    row_label: str = ""
    entity_aliases: dict[str, str] = Field(default_factory=dict)
    attribute_aliases: dict[str, str] = Field(default_factory=dict)
    removed_entities: dict[str, str] = Field(default_factory=dict)  # entity → reason (soft delete)

    @property
    def is_column_only(self) -> bool:
        return self.schema_mode == SchemaMode.COLUMN_ONLY or (
            not self.entities and bool(self.attributes)
        )

    @property
    def data_columns(self) -> list[str]:
        keys = set(self.primary_key)
        return [a for a in self.attributes if a not in keys]

    @staticmethod
    def make_entity_key(key_values: dict[str, str], primary_key: list[str]) -> str:
        vals = [str(key_values.get(k, "")).strip() for k in primary_key]
        vals = [v for v in vals if v]
        if len(vals) <= 1:
            return vals[0] if vals else ""
        return "|".join(vals)


class RelationKind(str, Enum):
    ONE_TO_MANY = "one_to_many"
    MANY_TO_MANY = "many_to_many"


class ForeignKey(CamelModel):
    """Links columns in one table to another table's primary key."""
    target_table: str
    columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)


class Relation(CamelModel):
    from_table: str
    foreign_key: ForeignKey = Field(default_factory=ForeignKey)
    kind: RelationKind = RelationKind.ONE_TO_MANY
    label: str = ""


class CoverageMap(CamelModel):
    """Coverage tracking across one or more tables."""

    tables: dict[str, TableSchema] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list)
    cells: dict[str, CoverageCell] = Field(default_factory=dict)
    # Cells popped by remove_entity; restore_entity puts them back verbatim.
    removed_cells: dict[str, CoverageCell] = Field(default_factory=dict)
    evidence_bindings: dict[str, list[CellEvidenceBinding]] = Field(default_factory=dict)
    evidence_comparisons: dict[str, dict[str, EvidenceComparison]] = Field(default_factory=dict)

    def initialize(
        self, entities: list[str], attributes: list[str],
        *, table_id: str = "", table_label: str = "",
        primary_key: list[str] | None = None,
        row_label: str = "",
        column_desc: dict[str, ColumnDesc] | None = None,
    ) -> None:
        tid = table_id or "_default"
        mode = SchemaMode.COLUMN_ONLY if not entities else SchemaMode.CLOSED
        schema = TableSchema(
            table_id=tid, table_label=table_label,
            entities=entities, attributes=attributes,
            schema_mode=mode,
            primary_key=list(primary_key or []),
            row_label=row_label,
            column_desc=column_desc or {},
        )
        self.tables[tid] = schema
        self.cells = {}
        pk = list(primary_key or [])
        for entity in entities:
            pk_values = entity.split("|") if pk and "|" in entity else [entity] if pk else []
            for attr in attributes:
                key = f"{tid}/{entity}.{attr}"
                if pk and attr in pk:
                    pk_idx = pk.index(attr)
                    val = pk_values[pk_idx] if pk_idx < len(pk_values) else entity
                    self.cells[key] = CoverageCell(
                        status=CellStatus.FILLED, best_alignment="full", display_hint=val,
                    )
                else:
                    self.cells[key] = CoverageCell()

    _FUZZY_AMBIGUITY_MARGIN = 1.5

    # ---- Multi-table helpers ----

    @property
    def primary_table_id(self) -> str:
        return next(iter(self.tables), "_default")

    @property
    def table_schema(self) -> TableSchema:
        """First table's schema — entry point for single-table code paths."""
        if self.tables:
            return next(iter(self.tables.values()))
        return TableSchema()

    @property
    def is_multi_table(self) -> bool:
        return len(self.tables) > 1

    def get_table(self, table_id: str) -> TableSchema | None:
        return self.tables.get(table_id)

    def add_columns(self, table_id: str, columns: dict[str, ColumnDesc]) -> list[str]:
        """原子扩展非主键列；不修改原有单元格、证据或已排除行。"""
        schema = self.tables.get(table_id)
        if schema is None:
            raise ValueError(f"Unknown table: {table_id}")
        if not columns:
            raise ValueError("At least one column is required")
        names = list(schema.attributes)
        added = []
        for name, description in columns.items():
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError("Column names must be non-empty and have no surrounding whitespace")
            if not isinstance(description, ColumnDesc):
                raise ValueError("Column descriptions must be validated ColumnDesc values")
            if name in schema.attributes:
                if description != schema.column_desc.get(name, ColumnDesc()):
                    raise ValueError(f"Cannot redefine existing column: {name}")
                continue
            collision = self._resolve_name(name, names, schema.attribute_aliases)
            if collision is not None or name in schema.attribute_aliases:
                raise ValueError(f"Column {name!r} conflicts with an existing name or alias")
            names.append(name)
            added.append(name)
        # Dots in entity/attribute names are allowed; their composite keys must
        # still identify one cell, including cells of excluded rows.
        keys = set()
        for entity in [*schema.entities, *schema.removed_entities]:
            for name in names:
                key = self.cell_key(table_id, entity, name)
                if key in keys:
                    raise ValueError(f"Ambiguous cell key: {key}")
                keys.add(key)
        new_cells = {self.cell_key(table_id, entity, name): CoverageCell()
                     for entity in schema.entities for name in added}
        if any(key in self.cells or key in self.removed_cells for key in new_cells):
            raise ValueError("New columns conflict with existing cell records")
        schema.attributes.extend(added)
        schema.column_desc.update({name: columns[name].model_copy(deep=True) for name in added})
        self.cells.update(new_cells)
        return added

    def _effective_table_id(self, table_id: str = "") -> str:
        return table_id or self.primary_table_id

    def cell_key(self, table_id: str, entity: str, attr: str) -> str:
        return f"{table_id}/{entity}.{attr}"

    def cell_binding(self, key: str) -> tuple[str, str, str] | None:
        """按 schema 解析归属，允许实体名和列名包含句点。"""
        tid, separator, rest = key.partition("/")
        schema = self.tables.get(tid)
        if not separator or schema is None:
            return None
        rows = {*schema.entities, *schema.removed_entities}
        matches = [(tid, rest[:-(len(attr) + 1)], attr) for attr in schema.attributes
                   if rest.endswith(f".{attr}") and rest[:-(len(attr) + 1)] in rows]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def parse_cell_key(key: str) -> tuple[str, str, str]:
        """Parse cell key → (table_id, entity, attribute)."""
        if "/" in key:
            tid, rest = key.split("/", 1)
        else:
            tid, rest = "", key
        if "." in rest:
            # PK values may contain periods ("U.S. Bank Stadium"); the attribute
            # is appended after the final period, so split from the right.
            ent, attr = rest.rsplit(".", 1)
        else:
            ent, attr = rest, ""
        return tid, ent, attr

    def add_table(
        self, table_id: str, attributes: list[str], *,
        table_label: str = "", primary_key: list[str] | None = None,
        row_label: str = "", column_desc: dict[str, ColumnDesc] | None = None,
        entities: list[str] | None = None,
    ) -> str:
        """Add a table. ``schema_mode`` is derived from ``entities`` (seeded →
        CLOSED, unseeded → COLUMN_ONLY) so the judge stays anchored on existing
        rows and spelling variants merge instead of double-counting."""
        if table_id in self.tables:
            return table_id
        ents = list(entities or [])
        mode = SchemaMode.CLOSED if ents else SchemaMode.COLUMN_ONLY
        schema = TableSchema(
            table_id=table_id, table_label=table_label, attributes=attributes,
            primary_key=list(primary_key or []), row_label=row_label,
            column_desc=column_desc or {}, schema_mode=mode,
        )
        self.tables[table_id] = schema
        for ent in ents:  # add_entity's "exists" guard makes later loops no-op
            self.add_entity(ent, table_id=table_id)
        return table_id

    def add_relation(self, rel: Relation) -> None:
        self.relations.append(rel)

    # ---- Cell key resolution (multi-table aware) ----

    def _resolve_cell_key(self, entity: str, attribute: str, *, table_id: str = "") -> str | None:
        """只挂载到已确认的行列，不猜测相似实体。"""
        tid = self._effective_table_id(table_id)
        entity = self.resolve_entity(entity, table_id=tid)
        attribute = self.resolve_attribute(attribute, table_id=tid)
        if entity is None or attribute is None:
            return None
        key = self.cell_key(tid, entity, attribute)
        return key if key in self.cells else None

    @classmethod
    def _resolve_name(cls, raw: str, names: list[str], aliases: dict[str, str]) -> str | None:
        """归一化和显式别名共用同一规则，歧义时不匹配。"""
        seen: set[str] = set()
        while raw not in seen:
            seen.add(raw)
            if raw in names:
                return raw
            norm = cls._normalize_for_fuzzy(raw.lower())
            if not norm:
                return None
            target = aliases.get(raw)
            if target is None and raw not in names:
                matches = {v for k, v in aliases.items()
                           if cls._normalize_for_fuzzy(k.lower()) == norm}
                if len(matches) > 1:
                    return None
                target = next(iter(matches), None)
            if target is not None and target != raw:
                raw = target
                continue
            matches = [n for n in names if cls._normalize_for_fuzzy(n.lower()) == norm]
            return matches[0] if len(matches) == 1 else None
        return None

    def resolve_row(self, entity: str, *, table_id: str = "") -> tuple[str | None, str]:
        """返回规范名称及 active/excluded/missing 状态。"""
        schema = self.tables.get(self._effective_table_id(table_id))
        if schema is None:
            return None, "missing"
        name = self._resolve_name(
            entity, [*schema.entities, *schema.removed_entities], schema.entity_aliases,
        )
        if name is None:
            return None, "missing"
        return name, "excluded" if name in schema.removed_entities else "active"

    def resolve_attribute(self, attribute: str, *, table_id: str = "") -> str | None:
        schema = self.tables.get(self._effective_table_id(table_id))
        if schema is None:
            return None
        return self._resolve_name(attribute, schema.attributes, schema.attribute_aliases)

    def resolve_entity(self, entity: str, *, table_id: str = "") -> str | None:
        """Resolve a raw PK string to an existing canonical row, or None.

        CONSERVATIVE by design: exact (incl. alias map) then normalized-exact
        only. PK identity must never merge two distinct rows — a false merge
        is silent, unrecoverable data loss — so loose fuzzy rules (substring,
        prefix, n-gram) are NOT applied here; they'd collapse siblings like
        "2020"/"2021", "GPT-4"/"GPT-4o". Normalization folds only cosmetic
        variance (case, whitespace, unicode quotes/dashes). Reorder /
        abbreviation variants are left to the LLM, where a miss is at worst a
        visible duplicate row, never a wrong merge."""
        canonical, status = self.resolve_row(entity, table_id=table_id)
        return canonical if status == "active" else None

    # Unicode punctuation → ASCII fold. Sources serialize the same name with
    # different quote/dash glyphs (nobelprize.org "L’Huillier" U+2019 vs the
    # Academy's straight "L'Huillier"); without folding, fuzzy match falls
    # below threshold and a duplicate row is promoted.
    _UNICODE_PUNCT_FOLD: ClassVar[dict[str, str]] = {
        "’": "'", "‘": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "‟": '"', "″": '"',
        "–": "-", "—": "-", "‒": "-",
        "‐": "-", "‑": "-", "―": "-",
    }

    @staticmethod
    def _normalize_for_fuzzy(s: str) -> str:
        """Strip cosmetic variance between schema and access-skill attribute
        names: bullets, separators (_ / - between words → space), trailing
        punctuation, collapsed whitespace. Caller has already lowercased.
        Unicode punctuation is folded to ASCII first."""
        for src, dst in CoverageMap._UNICODE_PUNCT_FOLD.items():
            if src in s:
                s = s.replace(src, dst)
        # Bullet / list-marker prefixes ("• Prime Minister"). A bare leading
        # '-' is handled separately so a numeric sign ("-1") isn't stripped
        # into "1" (which would false-merge during PK canonicalization).
        s = re.sub(r"^[•·・*\s]+", "", s)
        s = re.sub(r"^-+\s+", "", s)  # '-' as a bullet only
        # Underscores always separate; a hyphen separates ONLY between word
        # chars ("Federal-State"→"Federal State", "GPT-4"→"GPT 4") — a leading
        # sign / standalone dash is preserved so "-1" ≠ "1".
        s = s.replace("_", " ")
        s = re.sub(r"(?<=\w)-(?=\w)", " ", s)
        s = re.sub(r"[.,;:!?\)\]]+$", "", s)
        s = " ".join(s.split())
        return s

    @staticmethod
    def _fuzzy_name_score(a: str, b: str) -> int:
        """Score name match (0 = no match). Priority: exact > substring >
        shared prefix > shared Chinese 3-grams. Generic English tokens are
        ignored (too generic)."""
        a = CoverageMap._normalize_for_fuzzy(a)
        b = CoverageMap._normalize_for_fuzzy(b)

        if a == b:
            return len(a) * 10
        if a in b or b in a:
            return min(len(a), len(b)) * 5

        # Shared prefix — strong signal (same organization root)
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        prefix_len = 0
        for i in range(min(len(shorter), len(longer))):
            if shorter[i] == longer[i]:
                prefix_len += 1
            else:
                break
        if prefix_len >= 3:
            return prefix_len * 3

        # Shared Chinese 3-grams only (skip pure-English grams like "nlp"):
        # catches "中科院" shared across "中科院自动化所NLP组" / "中科院自动化所模式识别实验室".
        chinese_re = re.compile(r'[一-鿿]')
        if len(a) >= 3 and len(b) >= 3:
            grams_a = {a[i:i+3] for i in range(len(a) - 2) if chinese_re.search(a[i:i+3])}
            grams_b = {b[i:i+3] for i in range(len(b) - 2) if chinese_re.search(b[i:i+3])}
            shared = grams_a & grams_b
            if len(shared) >= 2:
                return len(shared)

        return 0

    _ALIGNMENT_RANK: ClassVar[dict[str, int]] = {"full": 3, "partial": 2, "loose": 1, "": 0}

    def fill(
        self, entity: str, attribute: str, *,
        finding_id: str, alignment: str = "loose",
        confidence: float = 0.5, tier: int = 1,
        display_hint: str = "", table_id: str = "",
    ) -> None:
        """挂载证据并选择展示值；文本差异交给独立的语义比较。"""
        key = self._resolve_cell_key(entity, attribute, table_id=table_id)
        if key is None:
            return
        cell = self.cells[key]

        if finding_id and finding_id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(finding_id)

        new_key = (tier, self._ALIGNMENT_RANK.get(alignment, 0), confidence)
        old_key = (cell.best_tier, self._ALIGNMENT_RANK.get(cell.best_alignment, 0),
                   cell.best_confidence)
        if new_key > old_key or (bool(display_hint) and not cell.display_hint):
            cell.best_alignment = alignment
            cell.best_confidence = confidence
            cell.best_tier = tier
            if display_hint:
                cell.full_value = display_hint
                cell.display_hint = display_hint[:120]
            if finding_id:
                cell.primary_evidence_id = finding_id

        if cell.best_alignment in ("full", "partial", "loose"):
            cell.status = CellStatus.FILLED

    @property
    def total_cells(self) -> int:
        return len(self.cells)

    @property
    def filled_cells(self) -> int:
        return sum(1 for c in self.cells.values() if c.status == CellStatus.FILLED)

    @property
    def empty_tables(self) -> list[str]:
        return [tid for tid, t in self.tables.items() if not t.entities]

    @property
    def coverage_score(self) -> float:
        # A declared-but-empty table is unstarted work, not vacuously complete:
        # count one phantom MISSING row per empty table so the score can't read
        # 100% while a whole table has no rows.
        phantom = sum(len(t.attributes) for t in self.tables.values() if not t.entities)
        total = len(self.cells) + phantom
        if not total:
            return 0.0
        return self.filled_cells / total

    def is_removed_entity(self, entity: str, *, table_id: str = "") -> bool:
        """Exact or normalized hit on a soft-deleted entity (stops spelling
        variants from bypassing the soft delete to re-enter the table)."""
        _, status = self.resolve_row(entity, table_id=table_id)
        return status == "excluded"

    def remove_entity(self, entity: str, *, table_id: str = "", reason: str = "") -> bool:
        """Soft-delete a row: drop from entities, stash its cells. Evidence
        nodes stay in the graph for audit."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        entity = self.resolve_entity(entity, table_id=tid)
        if schema is None or entity not in schema.entities:
            return False
        schema.entities.remove(entity)
        schema.removed_entities[entity] = reason or "removed"
        for attr in schema.attributes:
            key = self.cell_key(tid, entity, attr)
            cell = self.cells.pop(key, None)
            if cell is not None:
                self.removed_cells[key] = cell
        return True

    def restore_entity(self, entity: str, *, table_id: str = "") -> bool:
        """Reverse a soft-delete: row returns with its original cells."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        entity, status = self.resolve_row(entity, table_id=tid)
        if schema is None or entity is None or status != "excluded":
            return False
        schema.removed_entities.pop(entity, None)
        if entity not in schema.entities:
            schema.entities.append(entity)
        for attr in schema.attributes:
            key = self.cell_key(tid, entity, attr)
            cell = self.removed_cells.pop(key, None)
            if cell is not None:
                self.cells[key] = cell
            elif key not in self.cells:
                self.cells[key] = CoverageCell()
        return True

    def edit_entity(
        self, old_name: str, new_name: str | None = None, *, table_id: str = "",
    ) -> tuple[bool, str, str]:
        """Rename an entity's PK, preserving cell state and evidence refs.
        Returns (success, message, canonical_old_name) — callers need the
        resolved old name to update evidence nodes referencing the old PK."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        if schema is None:
            return False, f"unknown table {tid!r}", ""
        canonical = self.resolve_entity(old_name, table_id=tid)
        if canonical is None:
            return False, f"entity {old_name!r} not found", ""
        if not new_name or new_name.strip() == canonical:
            return True, "no rename needed", canonical
        new_name = new_name.strip()
        target, target_status = self.resolve_row(new_name, table_id=tid)
        if target_status == "active" and target != canonical:
            return False, f"target name {new_name!r} already exists", canonical
        if target_status == "excluded":
            return False, f"target name {new_name!r} is in removed_entities", canonical

        aliases = [alias for alias in schema.entity_aliases
                   if self.resolve_entity(alias, table_id=tid) == canonical]
        idx = schema.entities.index(canonical)
        schema.entities[idx] = new_name
        for alias in aliases:
            schema.entity_aliases[alias] = new_name
        schema.entity_aliases.pop(new_name, None)
        schema.entity_aliases[canonical] = new_name
        for attr in schema.attributes:
            old_key = self.cell_key(tid, canonical, attr)
            new_key = self.cell_key(tid, new_name, attr)
            if old_key in self.evidence_bindings:
                self.evidence_bindings[new_key] = self.evidence_bindings.pop(old_key)
            cell = self.cells.pop(old_key, None)
            if cell is not None:
                if attr in (schema.primary_key or []):
                    pk = schema.primary_key
                    pk_values = new_name.split("|") if pk and "|" in new_name else [new_name]
                    pk_idx = pk.index(attr) if attr in pk else 0
                    cell.display_hint = pk_values[pk_idx] if pk_idx < len(pk_values) else new_name
                    cell.full_value = cell.display_hint
                self.cells[new_key] = cell
        return True, f"renamed {canonical!r} → {new_name!r}", canonical

    def add_entity(self, entity: str, *, table_id: str = "") -> bool:
        """Add a new row with MISSING cells for all attributes."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        if schema is None:
            return False
        entity = entity.strip()
        if not entity or self.resolve_entity(entity, table_id=tid) is not None:
            return False
        # Orchestrator-excluded rows must not auto-revive via extraction/merge;
        # revival only goes through the add_entities tool's restore branch.
        if self.is_removed_entity(entity, table_id=tid):
            return False
        schema.entities.append(entity)
        pk = schema.primary_key
        pk_values = entity.split("|") if pk and "|" in entity else [entity] if pk else []
        for attr in schema.attributes:
            key = self.cell_key(tid, entity, attr)
            if pk and attr in pk:
                pk_idx = pk.index(attr)
                val = pk_values[pk_idx] if pk_idx < len(pk_values) else entity
                self.cells[key] = CoverageCell(
                    status=CellStatus.FILLED, best_alignment="full", display_hint=val,
                )
            else:
                self.cells[key] = CoverageCell()
        return True

    _SOURCE_AUTHORITY_WEIGHT: ClassVar[dict[str, float]] = {
        "official": 1.0, "industry_pr": 0.85, "aggregator": 0.7,
        "news": 0.65, "blog": 0.5, "unclear": 0.6,
    }

    @staticmethod
    def _fill_alignment(node: EvidenceNode) -> str:
        # agent:// summaries are lossy restatements — may seed cells but must
        # never outrank a direct page source on alignment tier.
        alignment = node.alignment or "loose"
        if alignment == "full" and (node.source or "").startswith("agent://"):
            return "partial"
        return alignment

    @staticmethod
    def _fill_tier(node: EvidenceNode) -> int:
        # span-anchored page (2) > unanchored page (1) > derived summary/seed (0)
        if (node.source or "").startswith("agent://") or node.id.startswith(("f_seed_", "f_assert_")):
            return 0
        return 2 if node.span else 1

    @staticmethod
    def _effective_confidence(node: EvidenceNode) -> float:
        # Raw judge confidence is nearly always 0.9, so it can't break ties.
        # Source authority + provenance are more reliable: official beats
        # aggregator; a direct page beats a lossy agent:// summary.
        authority = CoverageMap._SOURCE_AUTHORITY_WEIGHT.get(node.source_authority, 0.6)
        conf = node.confidence * authority
        if (node.source or "").startswith("agent://"):
            conf *= 0.6
        return conf

    def fill_from_evidence(self, nodes: list[EvidenceNode]) -> int:
        """投影已持久化节点，返回新增挂载数。生产写入统一经过 commit_evidence。"""
        filled = 0
        from searchos.socm.values import is_missing_value

        for node in nodes:
            if node.status != EvidenceStatus.ACTIVE:
                continue
            if not node.entity or not node.attribute:
                continue
            if is_missing_value(node.value or node.finding):
                continue
            tid = node.table_id or (self.primary_table_id if len(self.tables) == 1 else "")
            if not tid:
                continue
            key = self._resolve_cell_key(node.entity, node.attribute, table_id=tid)
            if key is None:
                continue
            if node.id not in self.cells[key].supporting_evidence_ids:
                self.fill(
                    node.entity, node.attribute,
                    finding_id=node.id, alignment=self._fill_alignment(node),
                    confidence=self._effective_confidence(node), tier=self._fill_tier(node),
                    display_hint=node.value or node.finding, table_id=tid,
                )
                filled += 1
        return filled


# 证据提交与单元格投影共用 Coverage Map 的归属规则。


def evidence_rank(node: EvidenceNode) -> tuple[int, int, float]:
    """Coverage 与所有输出共用的证据优先级。"""
    return (
        CoverageMap._fill_tier(node),
        CoverageMap._ALIGNMENT_RANK.get(CoverageMap._fill_alignment(node), 0),
        CoverageMap._effective_confidence(node),
    )


def evidence_table_id(cmap: CoverageMap, node: EvidenceNode) -> str:
    # 多表旧证据必须有明确归属，不能默认为第一张表。
    return node.table_id or (cmap.primary_table_id if len(cmap.tables) == 1 else "")


def evidence_scope(state: SearchState, node: EvidenceNode) -> dict[str, Any]:
    cmap = state.coverage_map
    tid = evidence_table_id(cmap, node)
    scope = {"table_id": tid, "row_status": "unbound", "exclusion_reason": ""}
    if not node.entity and not node.attribute:
        scope["table_id"] = node.table_id
        return scope
    entity, status = cmap.resolve_row(node.entity, table_id=tid) if tid else (None, "missing")
    scope["row_status"] = status
    if status == "excluded":
        scope["exclusion_reason"] = cmap.tables[tid].removed_entities[entity]
    elif status == "missing":
        scope["exclusion_reason"] = "unresolved_entity_or_table"
    elif node.attribute and cmap.resolve_attribute(node.attribute, table_id=tid) is None:
        scope.update(row_status="missing", exclusion_reason="unresolved_attribute")
    return scope


def answer_evidence(state: SearchState) -> list[EvidenceNode]:
    visible_bindings = {
        binding.evidence_id for key, bindings in state.coverage_map.evidence_bindings.items()
        if key in state.coverage_map.cells
        for binding in bindings if binding.status == EvidenceStatus.ACTIVE
    }
    return [
        node
        for node in state.evidence_graph.nodes
        if node.status == EvidenceStatus.ACTIVE
        and (evidence_scope(state, node)["row_status"] in {"active", "unbound"} or node.id in visible_bindings)
        and evidence_source_allowed(state, node)
    ]


def evidence_source_allowed(state: SearchState, node: EvidenceNode) -> bool:
    scope = state.source_scope
    if scope is None or node.source.startswith("agent://"):
        return True
    is_local = node.source.startswith("local://") or bool(node.local_source_metadata)
    if not is_local:
        return scope.get("mode") != "local"
    if scope.get("mode") == "web":
        return False
    from searchos.local.reader.references import parse_ref_id

    try:
        ref = parse_ref_id(node.source)
    except ValueError:
        return False
    return any(
        record.get("document_id") == ref.document_id
        and str(record.get("source_revision", "")).startswith(ref.source_revision)
        and (not ref.library_id or record.get("library_id") == ref.library_id)
        for record in scope.get("documents", [])
    )


def evidence_matches_cell(
    cmap: CoverageMap,
    node: EvidenceNode,
    table_id: str,
    entity: str,
    attribute: str,
) -> bool:
    return project_cell_evidence(cmap, node, table_id, entity, attribute) is not None


def project_cell_evidence(cmap: CoverageMap, node: EvidenceNode, table_id: str,
                          entity: str, attribute: str) -> EvidenceNode | None:
    """按指定格生成只读投影视图；原始事实不携带新的表格归属。"""
    key = cmap._resolve_cell_key(entity, attribute, table_id=table_id)
    if node.status != EvidenceStatus.ACTIVE or key is None:
        return None
    bindings = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == node.id]
    if bindings:
        binding = next((b for b in bindings if b.status == EvidenceStatus.ACTIVE), None)
        if binding is None:
            return None
        return node.model_copy(update={"table_id": table_id, "entity": entity, "attribute": attribute,
                                       "value": binding.value, "alignment": binding.alignment})
    tid = evidence_table_id(cmap, node)
    if node.status != EvidenceStatus.ACTIVE or not tid or tid != table_id:
        return None
    original_key = cmap._resolve_cell_key(node.entity, node.attribute, table_id=tid)
    return node if original_key == key else None


def bind_cell_evidence(state: SearchState, bindings: list[tuple[str, CellEvidenceBinding]],
                       *, overwrite: bool = False,
                       validation_values: dict[tuple[str, str], Any] | None = None) -> int:
    """提交已核验的投影。调用方负责语义支持检查；这里校验身份、范围和列约束。"""
    from searchos.socm.values import is_missing_value

    cmap = state.coverage_map
    allowed = {node.id for node in answer_evidence(state)}
    seen = set()
    for key, binding in bindings:
        target = cmap.cell_binding(key)
        if key not in cmap.cells or target is None:
            raise ValueError(f"Unknown or excluded cell: {key}")
        if binding.evidence_id not in allowed or binding.status != EvidenceStatus.ACTIVE:
            raise ValueError("Cell evidence must be active and in the current source scope")
        if is_missing_value(binding.value) or binding.alignment not in {"full", "partial", "loose"}:
            raise ValueError("A non-empty value and valid alignment are required")
        tid, entity, attr = target
        if attr in cmap.tables[tid].primary_key:
            index = cmap.tables[tid].primary_key.index(attr)
            parts = entity.split("|")
            expected = parts[index] if index < len(parts) else entity
            if binding.value != expected:
                raise ValueError("Cell projection cannot redefine row identity")
        desc = cmap.tables[tid].column_desc.get(attr)
        checked_value = (validation_values or {}).get((key, binding.evidence_id), binding.value)
        if desc and desc.check and (reason := desc.check.violation(checked_value)):
            raise ValueError(reason)
        identity = (key, binding.evidence_id)
        if identity in seen:
            raise ValueError("Duplicate cell evidence binding in one batch")
        seen.add(identity)
        previous = next((b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == binding.evidence_id), None)
        if previous is None and binding.evidence_id in cmap.cells[key].supporting_evidence_ids:
            node = state.evidence_graph.get_node(binding.evidence_id)
            view = project_cell_evidence(cmap, node, *target)
            if view is not None:
                previous = CellEvidenceBinding(evidence_id=node.id, value=view.value or view.finding,
                                                alignment=view.alignment or "loose")
        if previous is not None and previous != binding and not overwrite:
            raise ValueError("Changing or reactivating a projection requires an explicit overwrite")
    touched = set()
    added = 0
    reset_keys = set()
    # Preserve the original cell use before a legacy node is shared. Later
    # clearing that cell must change its binding, not the shared source fact.
    for _, binding in bindings:
        node = state.evidence_graph.get_node(binding.evidence_id)
        tid = evidence_table_id(cmap, node)
        original = cmap._resolve_cell_key(node.entity, node.attribute, table_id=tid) if tid else None
        if original and node.id in cmap.cells[original].supporting_evidence_ids:
            records = cmap.evidence_bindings.setdefault(original, [])
            if not any(b.evidence_id == node.id for b in records):
                records.append(CellEvidenceBinding(evidence_id=node.id, value=node.value or node.finding,
                                                   alignment=node.alignment or "loose"))
    for key, binding in bindings:
        records = cmap.evidence_bindings.setdefault(key, [])
        cell = cmap.cells[key]
        for fid in cell.supporting_evidence_ids:
            node = state.evidence_graph.get_node(fid)
            target = cmap.cell_binding(key)
            view = project_cell_evidence(cmap, node, *target) if node and target else None
            if view and not any(b.evidence_id == fid for b in records):
                records.append(CellEvidenceBinding(evidence_id=fid, value=view.value or view.finding,
                                                   alignment=view.alignment or "loose"))
        if overwrite and key not in reset_keys:
            chosen = {item.evidence_id for target, item in bindings if target == key}
            for record in records:
                if record.evidence_id not in chosen:
                    record.status = EvidenceStatus.SUPERSEDED
            cell.supporting_evidence_ids = [fid for fid in cell.supporting_evidence_ids if fid in chosen]
            reset_keys.add(key)
        previous = next((b for b in records if b.evidence_id == binding.evidence_id), None)
        if previous is None:
            records.append(binding.model_copy(deep=True))
            added += 1
        elif previous != binding:
            records[records.index(previous)] = binding.model_copy(deep=True)
        if binding.evidence_id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(binding.evidence_id)
        touched.add(key)
    refresh_cells(state, touched)
    return added


@dataclass
class EvidenceCommit:
    """分开统计节点、挂载和覆盖率变化。"""

    nodes: list[EvidenceNode] = field(default_factory=list)
    added_nodes: list[EvidenceNode] = field(default_factory=list)
    associations_added: int = 0
    cells_filled: int = 0
    rejected: list[dict[str, str]] = field(default_factory=list)


def commit_table_facts(
    state: SearchState,
    candidates: list[EvidenceNode],
    *,
    validation_values: dict[str, Any] | None = None,
) -> EvidenceCommit:
    """自动表格抽取提交独立事实与投影；候选表字段只用于确定目标格。"""
    result = EvidenceCommit()
    cmap = state.coverage_map
    before = {key for key, cell in cmap.cells.items() if cell.status == CellStatus.FILLED}
    for candidate in candidates:
        tid = evidence_table_id(cmap, candidate)
        key = (
            cmap._resolve_cell_key(candidate.entity, candidate.attribute, table_id=tid)
            if tid
            else None
        )
        reason = ""
        if key is None:
            reason = "unresolved_cell"
        elif not evidence_source_allowed(state, candidate):
            reason = "source_out_of_scope"
        elif (
            not candidate.source.startswith(("https://", "http://", "local://", "skill://", "agent://"))
            or candidate.span is None
        ):
            reason = "unanchored_source"
        if reason:
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": reason}
            )
            continue
        fact = candidate.model_copy(
            update={"table_id": "", "entity": "", "attribute": "", "value": ""}
        )
        legacy = state.evidence_graph.find_duplicate(candidate)
        durable, added = (
            (legacy, False) if legacy is not None else state.evidence_graph.get_or_add(fact)
        )
        binding = CellEvidenceBinding(
            evidence_id=durable.id, value=candidate.value, alignment=candidate.alignment
        )
        checked = (validation_values or {}).get(candidate.id, candidate.value)
        try:
            links = bind_cell_evidence(
                state, [(key, binding)], validation_values={(key, durable.id): checked}
            )
        except ValueError as exc:
            # Binding validation precedes its writes. Retract only this new
            # candidate; a pre-existing shared fact must survive rejection.
            if added:
                state.evidence_graph.nodes.remove(durable)
                state.evidence_graph.invalidate_index()
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": str(exc)}
            )
            continue
        result.nodes.append(durable)
        if added:
            result.added_nodes.append(durable)
        result.associations_added += links
    result.cells_filled = sum(
        cell.status == CellStatus.FILLED and key not in before for key, cell in cmap.cells.items()
    )
    return result


def validate_row(schema: TableSchema, row: dict[str, Any]) -> list[dict[str, str]]:
    """手工行与抽取行共用类型化列约束。"""
    return [
        {"column": column, "reason": reason}
        for column, desc in schema.column_desc.items()
        if desc.check and (reason := desc.check.violation(row.get(column)))
    ]


def refresh_cells(state: SearchState, keys: set[str]) -> None:
    """只重建指定格的已有挂载，不扫描并补挂历史证据。"""
    cmap = state.coverage_map
    for key in keys:
        old = cmap.cells.get(key)
        if old is None:
            continue
        binding = cmap.cell_binding(key)
        if binding is None:
            continue
        tid, entity, attr = binding
        schema = cmap.tables[tid]
        cell = CoverageCell()
        if attr in schema.primary_key:
            values = entity.split("|")
            index = schema.primary_key.index(attr)
            cell.status = CellStatus.FILLED
            cell.best_alignment = "full"
            cell.display_hint = values[index] if index < len(values) else entity
        nodes = [
            projected
            for fid in dict.fromkeys(old.supporting_evidence_ids)
            if (node := state.evidence_graph.get_node(fid)) is not None
            and evidence_source_allowed(state, node)
            and (projected := project_cell_evidence(cmap, node, tid, entity, attr)) is not None
        ]
        if not nodes and old.status in {CellStatus.UNCERTAIN, CellStatus.HARD_CELL}:
            cell.status = old.status
        cmap.cells[key] = cell
        cmap.fill_from_evidence(nodes)
        cell.conflict_history_evidence_ids = list(dict.fromkeys([
            *old.conflict_history_evidence_ids, *old.conflict_evidence_ids,
        ]))
    from searchos.socm.conflicts import reconcile_conflicts

    reconcile_conflicts(state, keys)


def commit_evidence(
    state: SearchState,
    nodes: list[EvidenceNode],
    *,
    overwrite: bool = False,
    validation_values: dict[str, Any] | None = None,
) -> EvidenceCommit:
    """验证、去重、挂载一次完成；只有显式覆盖可重新启用旧证据。"""
    from searchos.socm.values import is_missing_value

    result = EvidenceCommit()
    cmap = state.coverage_map
    touched: set[str] = set()
    before_filled: set[str] = set()
    for candidate in nodes:
        tid = evidence_table_id(cmap, candidate)
        key = (
            cmap._resolve_cell_key(candidate.entity, candidate.attribute, table_id=tid)
            if tid
            else None
        )
        reason = ""
        if candidate.status != EvidenceStatus.ACTIVE:
            reason = "inactive_evidence"
        elif is_missing_value(candidate.value or candidate.finding):
            reason = "missing_value"
        elif not evidence_source_allowed(state, candidate):
            reason = "source_out_of_scope"
        elif key is None:
            reason = "unresolved_cell"
        else:
            entity = cmap.resolve_entity(candidate.entity, table_id=tid)
            attr = cmap.resolve_attribute(candidate.attribute, table_id=tid)
            desc = cmap.tables[tid].column_desc.get(attr)
            if desc and desc.check:
                value = (validation_values or {}).get(candidate.id, candidate.value)
                reason = desc.check.violation(value) or ""
        if reason:
            result.rejected.append(
                {"row": candidate.entity, "column": candidate.attribute, "reason": reason}
            )
            continue
        node, added = state.evidence_graph.get_or_add(
            candidate.model_copy(
                update={
                    "table_id": tid,
                    "entity": entity,
                    "attribute": attr,
                }
            )
        )
        if node.status != EvidenceStatus.ACTIVE and not overwrite:
            result.rejected.append({"row": entity, "column": attr, "reason": "inactive_duplicate"})
            continue
        existing_binding = next(
            (b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == node.id), None
        )
        if existing_binding is not None and existing_binding.status != EvidenceStatus.ACTIVE and not overwrite:
            result.rejected.append({"row": entity, "column": attr, "reason": "inactive_binding"})
            continue
        cell = cmap.cells[key]
        if key not in touched and cell.status == CellStatus.FILLED:
            before_filled.add(key)
        touched.add(key)
        if overwrite:
            prior_ids = set(cell.supporting_evidence_ids)
            for fid in prior_ids:
                previous = state.evidence_graph.get_node(fid)
                if previous is not None and previous.id != node.id:
                    if evidence_matches_cell(cmap, previous, tid, entity, attr):
                        records = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == fid]
                        if records:
                            for record in records:
                                record.status = EvidenceStatus.SUPERSEDED
                        else:
                            previous.status = EvidenceStatus.SUPERSEDED
            node.status = EvidenceStatus.ACTIVE
            if existing_binding is not None:
                existing_binding.status = EvidenceStatus.ACTIVE
                existing_binding.value = node.value or node.finding
                existing_binding.alignment = node.alignment or "loose"
            cell.supporting_evidence_ids = [
                fid for fid in cell.supporting_evidence_ids if fid == node.id
            ]
        if node.id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(node.id)
            result.associations_added += 1
        if added:
            result.added_nodes.append(node)
        result.nodes.append(node)
    refresh_cells(state, touched)
    result.cells_filled = sum(
        cmap.cells[key].status == CellStatus.FILLED for key in touched - before_filled
    )
    return result


def clear_cell_evidence(state: SearchState, table_id: str, entity: str, attribute: str) -> bool:
    cmap = state.coverage_map
    key = cmap._resolve_cell_key(entity, attribute, table_id=table_id)
    if key is None:
        return False
    cell = cmap.cells[key]
    if cell.status == CellStatus.MISSING and not cell.supporting_evidence_ids:
        return False
    ids = set(cell.supporting_evidence_ids)
    for fid in ids:
        node = state.evidence_graph.get_node(fid)
        if node is not None and evidence_matches_cell(cmap, node, table_id, entity, attribute):
            records = [b for b in cmap.evidence_bindings.get(key, []) if b.evidence_id == fid]
            if records:
                for record in records:
                    record.status = EvidenceStatus.REJECTED
            else:
                node.status = EvidenceStatus.REJECTED
    cmap.cells[key] = CoverageCell()
    return True


def audit_evidence_links(state: SearchState) -> list[dict[str, str]]:
    """历史数据只读检查；不推断或修改挂载。"""
    issues = []
    by_id = {node.id: node for node in state.evidence_graph.nodes}
    attached: set[str] = set()
    for key, cell in state.coverage_map.cells.items():
        binding = state.coverage_map.cell_binding(key)
        for fid in cell.supporting_evidence_ids:
            if fid not in by_id:
                issues.append({"cell": key, "evidence_id": fid, "reason": "dangling_id"})
            elif binding is None or not evidence_matches_cell(
                state.coverage_map, by_id[fid], *binding
            ):
                issues.append({"cell": key, "evidence_id": fid, "reason": "invalid_binding"})
            else:
                attached.add(fid)
    for node in answer_evidence(state):
        if node.entity and node.attribute and node.id not in attached:
            issues.append({"cell": "", "evidence_id": node.id, "reason": "unattached_evidence"})
    return issues
