# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Pharaoh.se Access Skill

Retrieves structured information about Ancient Egyptian pharaohs and dynasties from the pharaoh.se encyclopedia.

## Available Functions

### get_pharaoh
Get detailed information about a specific pharaoh by their URL slug.

**Parameters:**
- `pharaoh_slug` (required): The URL identifier for the pharaoh

**Example slugs:** `Qakara-Ibi`, `Narmer`, `Teti`, `Khufu`, `Ramses-II`

**Returns:**
- Title and introduction
- Royal titulary (throne name, birth name, Horus name, etc.) with hieroglyphs and transliterations
- Reign information (predecessor, successor, reign duration)
- Historical sections and bibliography

### get_dynasty
Get information about a specific dynasty including the list of pharaohs.

**Parameters:**
- `dynasty_number` (required): Dynasty number (1-31) or "predynastic"

**Returns:**
- Dynasty title and introduction
- List of pharaohs in chronological order with links
- King list comparisons (Abydos Canon, Turin King List, etc.)
- Historical sections

### list_dynasties
Get an overview of all Egyptian dynasties organized by period.

**Returns:**
- Dynasty groups by period (Old Kingdom, Middle Kingdom, etc.)
- Dynasty names with date ranges and capitals
- Links to individual dynasty pages

### list_pharaohs
Get a complete list of all pharaohs in the database.

**Returns:**
- Total count of pharaohs
- List of all pharaohs with names and URL slugs

## Data Sources

The skill extracts data from:
- Main article content and introductions
- Royal titulary sections with hieroglyphic representations
- Pharaoh chronology tables
- King list comparison tables (Turin, Abydos, Karnak, Saqqara canons)
- Bibliography sections

## Notes

- The site uses Tailwind CSS classes for styling, which are parsed to identify content sections
- Hieroglyphic data includes both visual representations and transliterations
- Dynasty pages include multiple king list sources for cross-referencing
- All URLs are relative to pharaoh.se domain
