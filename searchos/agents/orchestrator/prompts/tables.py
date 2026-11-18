"""表格建模、成员维护及固定结构、定向修复的工作范围。"""

TABLE_DESIGN = """## Organize results

Create a schema with `create_schema` when tracking entities and attributes helps comparison, collection, deduplication, or gap assessment. Define entities and useful dimensions before table-bound retrieval. Derive them from the request and observed sources. Internal tables organize evidence; join them for the user's requested presentation.

### Table granularity and attribute ownership

Each table represents one entity type at a consistent granularity. Its columns consist of primary keys, foreign keys, and attributes determined by its primary key. Assign each attribute to the smallest key that determines it within the task's scope:
- Entity attributes belong in the entity table; category, period, and relationship attributes belong in tables keyed by those combinations.
- Use multiple tables for different entity types or granularities, such as company + product, restaurant + dish, or university + subject. For example, company headquarters belongs to Company; annual revenue belongs to (Company, Year); a product specification belongs to Product.
- For top-N per category, separate entity facts from category/period-specific ranks. Use a single table only when the same primary key determines all requested attributes.
- Store each fact at its own granularity to avoid duplicate retrieval and conflicting copies. Declare relations through shared keys when creating related tables, including reusable identity-mapping tables.

### Primary keys

Create and discover rows as objects with a separate value for every primary-key field. For exact operations, form RowRef {table_id, key: [values in primary_key order]} from the table header and row. Add the column name as attribute to form a CellRef. A single-column key still uses an array. Preserve punctuation inside field values.

Choose the smallest stable key that uniquely identifies a row and is recognizable to the user. Prefer, in order:
1. A canonical name when it is unique within the requested scope.
2. (Name, Short ID) when disambiguation is needed, such as company + ticker or hotel + identifying label; keep the name first.
3. A scoped sequence or rank, such as (Year, Rank) or (Category, Year, Rank). Include every dimension needed for uniqueness; a bare Rank or Sequence is not a stable identity.
4. A stable ISO code, ticker, or slug when names are missing or unsuitable.

Do not use bare numeric IDs as primary keys when a readable name is available. Prices, Resolution, Weight, Score, and Duration are attributes to retrieve, not primary keys. Percentages, free-form dates, punctuation-sensitive long titles, and fields requiring normalization to compare are forbidden as primary keys.

For bilingual names, use the dominant source language for the primary key and retain the alternate name as an attribute. Apply the user's language requirement in the final presentation without changing row identity.

### Column definitions and extension

Give each data column a `column_desc` with its type, meaning, required format, units, precision, and time basis. Resolve semantic ambiguity: total-score cutoff versus subject-score cutoff; earliest release across all regions/platforms versus one regional release. Record explicit formats such as YYYY, MM-DD-YYYY, or USD with commas. Keep URLs and excerpts in evidence metadata unless the user requests them as data.
When creating a table or adding columns, explicitly choose requires_search for every non-primary-key column. Set requires_search=false for stable fields inferable from an established row identity or known facts. For example, a university's home province may follow from its identity; a program's cutoff for a given year requires a source. Keep requires_search=true for variable facts and fields the user wants sourced.

Use `add_columns` to add an attribute or revise an existing data column by exact name. Send just the fields that change. If established row facts reliably determine a column, you can set requires_search=false and fill its values with `edit_entities`. Keep a user-requested source requirement in force. Reuse existing tables and create another table only when a distinct entity type or granularity requires it.
"""

FIXED_TABLES = """## Fixed schema

Use the declared tables, columns, keys, and relationships as given. Discover eligible rows, use `add_entities` to include them, and retrieve facts for the existing columns. Exploration uses these table boundaries. Structure changes are outside this task's scope.
"""

VALUE_CONTRACT = """### Value conventions

Carry the requested field meanings and formats into exploration and retrieval briefs. The user's convention governs layout, precision, language, and units; convert source values to it while preserving meaning. A column named Mass (kg) takes 70, not 70 kg. Follow the declared `column_desc` consistently, and resolve any conflict with the requested meaning before filling values.
"""

TABLE_WORK = """### Members and table work

Schema tools create and extend tables; they do not drop tables or columns. Row identity is an entity addressed as RowRef {table_id, key}. Use `read_table` for coverage and value distributions; use `exec` only for offline formulas on values already returned by tools.

Include every eligible entity explicitly named by the user or established by source evidence, including candidates verified by exploration. User-named targets establish identity and scope, not verified attribute values. Never invent seeds from parametric knowledge. Leave seeds empty when no grounded or user-specified identities are available and dispatch focused discovery. Retry failed discovery only with a concrete new route or reason to expect progress.

After each result batch, review the rows in the latest SOCM update. Use `add_entities` for established in-scope row keys still missing from the table. Set `target_table` to focus retrieval on a particular table. Supply exact `target_cells` for targeted fill or backfill. Leave cell targets open when discovering new members.
Fill requires_search=false fields inline with seed_entities or add_entities, or use edit_entities without evidence_ids for existing rows. Leave ambiguous campus or other uncertain mappings null. Dispatch searches for source-required fields.

Check source evidence when resolving conflicting claims or membership. Use `edit_entities` to correct row-key typos or replace values while preserving attribution; clear a disproved value to leave an explicit gap. Use `remove_entities` only when authoritative evidence positively excludes a row, such as absence from a complete official inventory, or when it fails an explicit task filter. Missing attributes do not justify removal; keep unresolved in-scope rows marked as missing.

Coverage measures filled cells among declared rows. Compare actual identities with the source-backed collection boundary: full known-row coverage, equal counts, and guessed lists do not prove completeness or correctness. Check both missing and extra members before claiming an exhaustive result.
"""

EXTRACTION = """Evidence Extraction checks each observation against the current schema and writes source-supported rows and cells. An empty declared table is ready for discovery. Without a schema, it records independent findings."""

REPAIR = """## Selected-cell repair

The selected cells in the user message define the allowed scope. Dispatch retrieval tasks for those cells with explicit `target_table` and `target_cells`. Group work by evidence needs and dependencies. When reports arrive, review the selected cells in the latest SOCM update, and report changes and remaining gaps. Keep the declared tables, columns, and entity set fixed.
"""


def render_tables(*, fixed: bool, repair: bool) -> str:
    if repair:
        return "\n\n".join(section.strip() for section in (REPAIR, VALUE_CONTRACT))
    sections = [FIXED_TABLES if fixed else TABLE_DESIGN, EXTRACTION, VALUE_CONTRACT, TABLE_WORK]
    return "\n\n".join(section.strip() for section in sections)
