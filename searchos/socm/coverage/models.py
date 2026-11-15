"""Coverage Map 的表结构、单元格状态与实体解析。"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, ClassVar, Literal

from pydantic import Field, computed_field, model_validator

from searchos.socm.evidence.graph import EvidenceComparison, EvidenceNode, EvidenceStatus
from searchos.socm.refs import CellRef, cell_key, cell_parts, row_key, row_values
from searchos.utils.base_model import CamelModel


class CellStatus(str, Enum):
    MISSING = "missing"
    FILLED = "filled"
    UNCERTAIN = "uncertain"
    HARD_CELL = "hard_cell"  # confirmed unreachable


def cell_is_complete(cell: Any) -> bool:
    """完成统计要求值和证据比较均已确定。"""
    return bool(cell is not None and cell.status == "filled"
                and not cell.has_conflict and cell.conflict_status == "clear")


def cell_is_actionable(cell: Any, *, explicit_target: bool = False) -> bool:
    """待比较的证据先等待比较完成；不可获取字段单独保留。"""
    if cell is None:
        return True
    if cell.conflict_status == "pending" or (not explicit_target and not getattr(cell, "requires_search", True)):
        return False
    return bool(cell.has_conflict or cell.conflict_status in {"uncertain", "confirmed"}
                or cell.status in {"missing", "uncertain"})


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
    requires_search: bool = Field(default=True, strict=True)


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
    inferred: bool = False
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

    @model_validator(mode="after")
    def validate_row_keys(self):
        for entity in [*self.entities, *self.removed_entities, *self.entity_aliases, *self.entity_aliases.values()]:
            self.parse_entity_key(entity)
        return self

    @property
    def is_column_only(self) -> bool:
        return self.schema_mode == SchemaMode.COLUMN_ONLY or (
            not self.entities and bool(self.attributes)
        )

    @property
    def data_columns(self) -> list[str]:
        keys = set(self.primary_key)
        return [a for a in self.attributes if a not in keys]

    def requires_search(self, attribute: str) -> bool:
        desc = self.column_desc.get(attribute)
        return desc is None or desc.requires_search

    @staticmethod
    def make_entity_key(key_values: dict[str, str], primary_key: list[str]) -> str:
        return row_key([str(key_values[k]).strip() if key_values.get(k) is not None else ""
                        for k in primary_key])

    def parse_entity_key(self, entity: str) -> dict[str, str]:
        """按声明的字段顺序读取规范行键。"""
        values = row_values(entity)
        if not self.primary_key:
            return {}
        if len(values) != len(self.primary_key):
            raise ValueError("Row key must contain every primary-key field in schema order")
        return dict(zip(self.primary_key, values))


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
            pk_values = schema.parse_entity_key(entity)
            for attr in attributes:
                key = self.cell_key(tid, entity, attr)
                if pk and attr in pk:
                    val = pk_values[attr]
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
        """返回本次新增的列名。"""
        added, _, _ = self.upsert_columns(table_id, columns)
        return added

    def upsert_columns(
        self, table_id: str, columns: dict[str, ColumnDesc],
    ) -> tuple[list[str], list[str], int]:
        """原子新增列或修改指定字段，返回新增列、修改列和重新待查的推断格数。"""
        schema = self.tables.get(table_id)
        if schema is None:
            raise ValueError(f"Unknown table: {table_id}")
        if not columns:
            raise ValueError("At least one column is required")
        names = list(schema.attributes)
        added = []
        changes = {}
        require_evidence = []
        for name, description in columns.items():
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise ValueError("Column names must be non-empty and have no surrounding whitespace")
            if not isinstance(description, ColumnDesc):
                raise ValueError("Column descriptions must be validated ColumnDesc values")
            if name in schema.attributes:
                current = schema.column_desc.get(name, ColumnDesc())
                revised = ColumnDesc.model_validate({
                    **current.model_dump(), **description.model_dump(exclude_unset=True),
                })
                if revised == current:
                    continue
                if name in schema.primary_key:
                    raise ValueError(f"Cannot edit primary-key column: {name}")
                changes[name] = revised
                if revised.requires_search and not current.requires_search:
                    require_evidence.append(name)
                continue
            collision = self._resolve_name(name, names, schema.attribute_aliases)
            if collision is not None or name in schema.attribute_aliases:
                raise ValueError(f"Column {name!r} conflicts with an existing name or alias")
            names.append(name)
            added.append(name)
        new_cells = {self.cell_key(table_id, entity, name): CoverageCell()
                     for entity in schema.entities for name in added}
        if any(key in self.cells or key in self.removed_cells for key in new_cells):
            raise ValueError("New columns conflict with existing cell records")
        schema.attributes.extend(added)
        schema.column_desc.update({name: columns[name].model_copy(deep=True) for name in added})
        schema.column_desc.update(changes)
        self.cells.update(new_cells)
        reopened = 0
        for name in require_evidence:
            for entities, cells in ((schema.entities, self.cells), (schema.removed_entities, self.removed_cells)):
                for entity in entities:
                    cell = cells.get(self.cell_key(table_id, entity, name))
                    if cell and cell.inferred and not cell.supporting_evidence_ids:
                        cell.inferred = False
                        cell.status = CellStatus.MISSING
                        cell.full_value = None
                        cell.display_hint = ""
                        reopened += 1
        return added, list(changes), reopened

    def _effective_table_id(self, table_id: str = "") -> str:
        return table_id or self.primary_table_id

    def cell_key(self, table_id: str, entity: str, attr: str) -> str:
        return cell_key(table_id, entity, attr)

    def primary_key_values(self, entity: str, *, table_id: str = "") -> dict[str, str]:
        """读取已保存的主键字段原值。"""
        tid = self._effective_table_id(table_id)
        schema = self.tables[tid]
        values = {}
        for attr in schema.primary_key:
            key = self.cell_key(tid, entity, attr)
            cell = self.cells.get(key) or self.removed_cells.get(key)
            if cell is not None and cell.value:
                values[attr] = cell.value
        if len(values) < len(schema.primary_key):
            try:
                fallback = schema.parse_entity_key(entity)
            except ValueError:
                fallback = {}
            values = {attr: values.get(attr, fallback.get(attr, "")) for attr in schema.primary_key}
        return values

    def cell_binding(self, key: str) -> tuple[str, str, str] | None:
        """解码后验证表、行和字段归属。"""
        try:
            tid, entity, attr = cell_parts(key)
        except (ValueError, TypeError):
            return None
        schema = self.tables.get(tid)
        if schema is None:
            return None
        rows = {*schema.entities, *schema.removed_entities}
        return (tid, entity, attr) if entity in rows and attr in schema.attributes else None

    def resolve_cell_reference(self, reference: str | CellRef | dict, *, table_id: str = "") -> str | None:
        """工具边界接收 CellRef；内部调用使用规范编码。"""
        try:
            key = reference if isinstance(reference, str) else CellRef.model_validate(reference).cell_key()
            tid, entity, attr = cell_parts(key)
        except (ValueError, TypeError):
            return None
        if table_id and tid != table_id:
            return None
        return self._resolve_cell_key(entity, attr, table_id=tid)

    @staticmethod
    def parse_cell_key(key: str) -> tuple[str, str, str]:
        """Parse cell key → (table_id, entity, attribute)."""
        return cell_parts(key)

    def add_table(
        self, table_id: str, attributes: list[str], *,
        table_label: str = "", primary_key: list[str] | None = None,
        row_label: str = "", column_desc: dict[str, ColumnDesc] | None = None,
        entities: list[str] | None = None,
        entity_values: dict[str, dict[str, str]] | None = None,
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
            self.add_entity(ent, table_id=table_id, key_values=(entity_values or {}).get(ent))
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
    def _resolve_name(cls, raw: str, names: list[str], aliases: dict[str, str], *, row: bool = False) -> str | None:
        """归一化和显式别名共用同一规则，歧义时不匹配。"""
        def normalize(value: str):
            if row:
                return tuple(cls._normalize_for_fuzzy(part.lower()) for part in row_values(value))
            return cls._normalize_for_fuzzy(value.lower())

        seen: set[str] = set()
        while raw not in seen:
            seen.add(raw)
            if raw in names:
                return raw
            norm = normalize(raw)
            if not norm:
                return None
            target = aliases.get(raw)
            if target is None and raw not in names:
                matches = {v for k, v in aliases.items()
                           if normalize(k) == norm}
                if len(matches) > 1:
                    return None
                target = next(iter(matches), None)
            if target is not None and target != raw:
                raw = target
                continue
            matches = [n for n in names if normalize(n) == norm]
            return matches[0] if len(matches) == 1 else None
        return None

    def resolve_row(self, entity: str, *, table_id: str = "") -> tuple[str | None, str]:
        """返回规范名称及 active/excluded/missing 状态。"""
        schema = self.tables.get(self._effective_table_id(table_id))
        if schema is None:
            return None, "missing"
        try:
            schema.parse_entity_key(entity)
        except (ValueError, TypeError):
            return None, "missing"
        name = self._resolve_name(
            entity, [*schema.entities, *schema.removed_entities], schema.entity_aliases, row=True,
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
        if cell.inferred or new_key > old_key or (bool(display_hint) and not cell.display_hint):
            cell.inferred = False
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
        return sum(cell_is_complete(c) for c in self.cells.values())

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
        try:
            key_values = schema.parse_entity_key(new_name)
        except ValueError as exc:
            return False, str(exc), canonical
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
            if old_key in self.evidence_comparisons:
                self.evidence_comparisons[new_key] = self.evidence_comparisons.pop(old_key)
            cell = self.cells.pop(old_key, None)
            if cell is not None:
                if attr in (schema.primary_key or []):
                    cell.display_hint = key_values[attr]
                    cell.full_value = cell.display_hint
                self.cells[new_key] = cell
        return True, f"renamed {canonical!r} → {new_name!r}", canonical

    def add_entity(
        self, entity: str, *, table_id: str = "", key_values: dict[str, str] | None = None,
    ) -> bool:
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
        values = schema.parse_entity_key(entity) if key_values is None else key_values
        if schema.primary_key and (
            any(not values.get(attr) for attr in schema.primary_key)
            or schema.make_entity_key(values, schema.primary_key) != entity
        ):
            raise ValueError("Primary-key fields must match the row reference")
        schema.entities.append(entity)
        pk = schema.primary_key
        for attr in schema.attributes:
            key = self.cell_key(tid, entity, attr)
            if pk and attr in pk:
                val = values[attr]
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
        from searchos.socm.evidence.missing_values import is_missing_value

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


def validate_row(schema: TableSchema, row: dict[str, Any]) -> list[dict[str, str]]:
    """手工行与抽取行共用类型化列约束。"""
    return [
        {"column": column, "reason": reason}
        for column, desc in schema.column_desc.items()
        if desc.check and (reason := desc.check.violation(row.get(column)))
    ]
