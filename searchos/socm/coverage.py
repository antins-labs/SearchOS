"""SOCM · Coverage Map — entity × attribute fill tracker (paper §Coverage Map).

Multi-table: ``tables`` keyed by table_id; cell keys are
``"{table_id}/{entity}.{attribute}"``. Single-table mode uses table_id="_default".
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, ClassVar

from pydantic import Field, computed_field

from searchos.socm.evidence import EvidenceGraph, EvidenceNode, EvidenceStatus
from searchos.util.base_model import CamelModel


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
    ``display_hint`` is a short cached snippet for live summaries."""

    status: CellStatus = CellStatus.MISSING
    supporting_evidence_ids: list[str] = []
    best_alignment: str = ""           # full | partial | loose | ""
    best_confidence: float = 0.0       # confidence of the display_hint winner
    best_tier: int = 1                 # provenance tier of winner (2 anchored / 1 page / 0 derived)
    has_conflict: bool = False
    display_hint: str = ""
    primary_evidence_id: str = ""
    conflict_evidence_ids: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[misc]
    @property
    def value(self) -> str:
        return self.display_hint


class SchemaMode(str, Enum):
    # Both modes grow during search (orphan evidence promotes rows). The mode
    # only signals whether the initial row denominator is seeded — which
    # drives coverage scoring and writer-trigger gating, not growth.
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

    def _effective_table_id(self, table_id: str = "") -> str:
        return table_id or self.primary_table_id

    def cell_key(self, table_id: str, entity: str, attr: str) -> str:
        return f"{table_id}/{entity}.{attr}"

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
        tid = self._effective_table_id(table_id)
        # Apply alias maps from extraction auto-bind (row "Louise Glück"→"2020",
        # column "Designed by"→"Primary Creator").
        ts = self.tables.get(tid)
        if ts is not None:
            if entity in ts.entity_aliases:
                entity = ts.entity_aliases[entity]
            if attribute in ts.attribute_aliases:
                attribute = ts.attribute_aliases[attribute]
        key = self.cell_key(tid, entity, attribute)
        if key in self.cells:
            return key

        # Fuzzy match scoped to the table
        entity_low = entity.lower()
        attr_low = attribute.lower()
        prefix = f"{tid}/"
        scored: list[tuple[int, str]] = []
        for cell_key in self.cells:
            if not cell_key.startswith(prefix):
                continue
            rest = cell_key[len(prefix):]
            parts = rest.rsplit(".", 1)
            if len(parts) != 2:
                continue
            cell_ent, cell_attr = parts
            ent_score = self._fuzzy_name_score(entity_low, cell_ent.lower())
            attr_score = self._fuzzy_name_score(attr_low, cell_attr.lower())
            if ent_score > 0 and attr_score > 0:
                scored.append((ent_score + attr_score, cell_key))

        if not scored:
            return None
        scored.sort(reverse=True)
        best_score, best_key = scored[0]
        if len(scored) == 1:
            return best_key
        second_score, _ = scored[1]
        if best_score < second_score * self._FUZZY_AMBIGUITY_MARGIN:
            return None  # ambiguous
        return best_key

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
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        if schema is None:
            return None
        if entity in schema.entity_aliases:
            entity = schema.entity_aliases[entity]
        if entity in schema.entities:
            return entity
        norm = self._normalize_for_fuzzy(entity.lower())
        if not norm:
            return None
        for cand in schema.entities:
            if self._normalize_for_fuzzy(cand.lower()) == norm:
                return cand
        return None

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

    _ALIGNMENT_RANK = {"full": 3, "partial": 2, "loose": 1, "": 0}

    def fill(
        self, entity: str, attribute: str, *,
        finding_id: str, alignment: str = "loose",
        confidence: float = 0.5, tier: int = 1,
        display_hint: str = "", table_id: str = "",
    ) -> None:
        """Record a finding against a cell. Winner is lexicographic max of
        (tier, alignment, confidence); ANY value disagreement flags conflict."""
        key = self._resolve_cell_key(entity, attribute, table_id=table_id)
        if key is None:
            return
        cell = self.cells[key]

        if finding_id and finding_id not in cell.supporting_evidence_ids:
            cell.supporting_evidence_ids.append(finding_id)

        if display_hint and cell.display_hint and display_hint != cell.display_hint:
            cell.has_conflict = True
            for fid in (cell.primary_evidence_id, finding_id):
                if fid and fid not in cell.conflict_evidence_ids:
                    cell.conflict_evidence_ids.append(fid)

        new_key = (tier, self._ALIGNMENT_RANK.get(alignment, 0), confidence)
        old_key = (cell.best_tier, self._ALIGNMENT_RANK.get(cell.best_alignment, 0),
                   cell.best_confidence)
        if new_key > old_key or (bool(display_hint) and not cell.display_hint):
            cell.best_alignment = alignment
            cell.best_confidence = confidence
            cell.best_tier = tier
            if display_hint:
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
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        if schema is None or not schema.removed_entities:
            return False
        if entity in schema.removed_entities:
            return True
        norm = self._normalize_for_fuzzy(entity.lower())
        return any(
            self._normalize_for_fuzzy(r.lower()) == norm
            for r in schema.removed_entities
        )

    def remove_entity(self, entity: str, *, table_id: str = "", reason: str = "") -> bool:
        """Soft-delete a row: drop from entities, stash its cells. Evidence
        nodes stay in the graph for audit."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
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
        if schema is None or entity not in schema.removed_entities:
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
        if new_name in schema.entities:
            return False, f"target name {new_name!r} already exists", canonical
        if self.is_removed_entity(new_name, table_id=tid):
            return False, f"target name {new_name!r} is in removed_entities", canonical

        idx = schema.entities.index(canonical)
        schema.entities[idx] = new_name
        schema.entity_aliases[canonical] = new_name
        for attr in schema.attributes:
            old_key = self.cell_key(tid, canonical, attr)
            new_key = self.cell_key(tid, new_name, attr)
            cell = self.cells.pop(old_key, None)
            if cell is not None:
                if attr in (schema.primary_key or []):
                    pk = schema.primary_key
                    pk_values = new_name.split("|") if pk and "|" in new_name else [new_name]
                    pk_idx = pk.index(attr) if attr in pk else 0
                    cell.display_hint = pk_values[pk_idx] if pk_idx < len(pk_values) else new_name
                self.cells[new_key] = cell
        return True, f"renamed {canonical!r} → {new_name!r}", canonical

    def add_entity(self, entity: str, *, table_id: str = "") -> bool:
        """Add a new row with MISSING cells for all attributes."""
        tid = self._effective_table_id(table_id)
        schema = self.tables.get(tid)
        if schema is None:
            return False
        if entity in schema.entities:
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
        """Fill cells from evidence nodes, routed by EvidenceNode.table_id."""
        filled = 0
        for node in nodes:
            if node.status != EvidenceStatus.ACTIVE:
                continue
            if not node.entity or not node.attribute:
                continue
            tid = node.table_id or self.primary_table_id
            key = self._resolve_cell_key(node.entity, node.attribute, table_id=tid)
            if key is None:
                continue
            if node.id not in self.cells[key].supporting_evidence_ids:
                self.fill(
                    node.entity, node.attribute,
                    finding_id=node.id, alignment=self._fill_alignment(node),
                    confidence=self._effective_confidence(node), tier=self._fill_tier(node),
                    display_hint=(node.value or node.finding)[:120], table_id=tid,
                )
                filled += 1
        return filled

    def backfill_from_evidence(self, evidence_graph: EvidenceGraph, *, table_id: str = "") -> int:
        """Replay all active evidence into matching cells after schema expansion."""
        before_filled = self.filled_cells
        for node in evidence_graph.nodes:
            if node.status != EvidenceStatus.ACTIVE:
                continue
            if not node.entity or not node.attribute:
                continue
            tid = table_id or node.table_id or self.primary_table_id
            key = self._resolve_cell_key(node.entity, node.attribute, table_id=tid)
            if key is None:
                continue
            if node.id not in self.cells[key].supporting_evidence_ids:
                self.fill(
                    node.entity, node.attribute,
                    finding_id=node.id, alignment=self._fill_alignment(node),
                    confidence=self._effective_confidence(node), tier=self._fill_tier(node),
                    display_hint=(node.value or node.finding)[:120], table_id=tid,
                )
        return self.filled_cells - before_filled
