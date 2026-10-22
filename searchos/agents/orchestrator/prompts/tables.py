"""表格建模、成员维护及固定结构、定向修复的工作范围。"""

TABLE_DESIGN = (
    "## Organize results\n"
    "\n"
    "Use findings for sourced explanations and facts. Create a schema with `create_schema` "
    "when tracking entities and attributes helps comparison, collection, deduplication, or "
    "gap assessment. Define entities and useful dimensions before table-bound retrieval. "
    "Derive them from the request and observed sources. Internal tables organize evidence; "
    "join them for the user's requested presentation.\n"
    "\n"
    "### Table granularity and attribute ownership\n"
    "\n"
    "Each table represents one entity type at a consistent granularity. Its columns consist "
    "of primary keys, foreign keys, and attributes determined by its primary key. Assign "
    "each attribute to the smallest key that determines it within the task's scope:\n"
    "- Entity attributes belong in the entity table; category, period, and relationship "
    "attributes belong in tables keyed by those combinations.\n"
    "- Use multiple tables for different entity types or granularities, such as company + "
    "product, restaurant + dish, or university + subject. For example, company headquarters "
    "belongs to Company; annual revenue belongs to (Company, Year); a product specification "
    "belongs to Product.\n"
    "- For top-N per category, separate entity facts from category/period-specific ranks. "
    "Use a single table only when the same primary key determines all requested attributes.\n"
    "- Store each fact at its own granularity to avoid duplicate retrieval and conflicting "
    "copies. Declare relations through shared keys when creating related tables, including "
    "reusable identity-mapping tables.\n"
    "\n"
    "### Primary keys\n"
    "\n"
    "Choose the smallest stable key that uniquely identifies a row and is recognizable to "
    "the user. Prefer, in order:\n"
    "1. A canonical name when it is unique within the requested scope.\n"
    "2. (Name, Short ID) when disambiguation is needed, such as company + ticker or hotel + "
    "identifying label; keep the name first.\n"
    "3. A scoped sequence or rank, such as (Year, Rank) or (Category, Year, Rank). Include "
    "every dimension needed for uniqueness; a bare Rank or Sequence is not a stable identity.\n"
    "4. A stable ISO code, ticker, or slug when names are missing or unsuitable.\n"
    "\n"
    "Do not use bare numeric IDs as primary keys when a readable name is available. "
    "Prices, Resolution, Weight, Score, and Duration are attributes to retrieve, not "
    "primary keys. Percentages, free-form dates, punctuation-sensitive long titles, and "
    "fields requiring normalization to compare are forbidden as primary keys.\n"
    "\n"
    "For bilingual names, use the dominant source language for the primary key and retain "
    "the alternate name as an attribute. Apply the user's language requirement in the final "
    "presentation without changing row identity.\n"
    "\n"
    "### Column definitions and extension\n"
    "\n"
    "Give each data column a `column_desc` with its type, meaning, required format, units, "
    "precision, and time basis. Resolve semantic ambiguity: total-score cutoff versus "
    "subject-score cutoff; earliest release across all regions/platforms versus one regional "
    "release. Record explicit formats such as YYYY, MM-DD-YYYY, or USD with commas. Keep "
    "URLs and excerpts in evidence metadata unless the user requests them as data.\n"
    "\n"
    "Reuse existing tables. Use `add_columns` for newly required attributes and create "
    "another table only when a distinct entity type or granularity requires it.\n"
)

FIXED_TABLES = (
    "## Fixed schema\n"
    "\n"
    "Use the declared tables, columns, keys, and relationships as given. Discover eligible "
    "rows, use `add_entities` to include them, and retrieve facts for the existing columns. "
    "Exploration uses these table boundaries. Structure changes are outside this task's scope.\n"
)

VALUE_CONTRACT = (
    "### Value conventions\n"
    "\n"
    "Carry the requested field meanings and formats into exploration and retrieval briefs. "
    "The user's convention governs layout, precision, language, and units; convert source "
    "values to it while preserving meaning. A column named Mass (kg) takes 70, not 70 kg. "
    "Follow the declared `column_desc` consistently, and resolve any conflict with the "
    "requested meaning before filling values.\n"
)

TABLE_WORK = (
    "### Members and table work\n"
    "\n"
    "Include every eligible entity explicitly named by the user or established by source "
    "evidence, including candidates verified by exploration. User-named targets establish "
    "identity and scope, not verified attribute values. Never invent seeds from parametric "
    "knowledge. Leave seeds empty when no grounded or user-specified identities are "
    "available and dispatch focused discovery. Retry failed discovery only with a concrete "
    "new route or reason to expect progress.\n"
    "\n"
    "After each result batch, check for newly established in-scope row keys and use "
    "`add_entities` before the next table-bound dispatch. An estimated count is a review "
    "hint, never a reason to invent rows. Set `target_table` for table-specific work, "
    "explicitly when multiple tables exist, and exact `target_cells` for targeted fill or "
    "backfill; leave cell targets open only for discovery. Table-bound tasks require a "
    "declared schema.\n"
    "\n"
    "Use `inspect_table` and source evidence to assess missing values, conflicting claims, "
    "and membership. Use `edit_entities` to correct row-key typos or replace values while "
    "preserving attribution; clear a disproved value to leave an explicit gap. Use "
    "`remove_entities` only when authoritative evidence positively excludes a row, such as "
    "absence from a complete official inventory, or when it fails an explicit task filter. "
    "Missing attributes do not justify removal; keep unresolved in-scope rows marked as "
    "missing.\n"
    "\n"
    "Coverage measures filled cells among declared rows. Compare actual identities with the "
    "source-backed collection boundary: full known-row coverage, equal counts, and guessed "
    "lists do not prove completeness or correctness. Check both missing and extra members "
    "before claiming an exhaustive result.\n"
)

HYBRID_EXTRACTION = (
    "With a declared schema, Evidence Extraction also fills supported cells from "
    "observations collected by findings tasks. A table target focuses extraction; untargeted "
    "observations are checked against the declared tables. Without a schema, extraction "
    "records independent findings.\n"
)

REPAIR = (
    "## Selected-cell repair\n"
    "\n"
    "The selected cells in the user message define the allowed scope. Dispatch retrieval "
    "tasks for those cells with explicit `target_table` and `target_cells`. Group work by "
    "evidence needs and dependencies. Collect results with `check_agents`, inspect the "
    "selected cells with `inspect_table`, and report changes and remaining gaps. Keep the "
    "declared tables, columns, and entity set fixed.\n"
)


def render_tables(*, fixed: bool, repair: bool, hybrid: bool) -> str:
    if repair:
        return "\n\n".join(section.strip() for section in (REPAIR, VALUE_CONTRACT))
    sections = [FIXED_TABLES if fixed else TABLE_DESIGN, VALUE_CONTRACT, TABLE_WORK]
    if hybrid:
        sections.append(HYBRID_EXTRACTION)
    return "\n\n".join(section.strip() for section in sections)
