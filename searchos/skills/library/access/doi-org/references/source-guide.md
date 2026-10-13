# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# DOI.org Metadata Access Skill

This skill retrieves structured metadata from DOI (Digital Object Identifier) landing pages using content negotiation.

## Capabilities

### 1. Get Metadata (`get_metadata`)

Retrieve comprehensive metadata for any DOI, including:
- Title and description/summary
- Authors and contacts
- Publication dates
- Keywords and subjects
- Related links
- Citation information

**Example:**
```json
{
  "function": "get_metadata",
  "doi": "10.5066/P13XCP3R"
}
```

**Returns:**
```json
{
  "success": true,
  "doi": "10.5066/P13XCP3R",
  "title": "U.S. Geological Survey Mineral Commodity Summaries 2025 Data Release",
  "summary": "This database contains the United States salient statistics...",
  "authors": ["National Minerals Information Center"],
  "contacts": [...],
  "dates": {
    "publication": "2025-01-31",
    "start": "2024-01-01",
    "end": "2024-12-31"
  },
  "keywords": ["industrial minerals", "metals", "nonfuel minerals"],
  "links": [...],
  "source_type": "sciencebase"
}
```

### 2. List Files (`list_files`)

List all downloadable files associated with a DOI, particularly useful for dataset DOIs hosted on platforms like ScienceBase.

**Example:**
```json
{
  "function": "list_files",
  "doi": "10.5066/P13XCP3R"
}
```

**Returns:**
```json
{
  "success": true,
  "doi": "10.5066/P13XCP3R",
  "title": "U.S. Geological Survey Mineral Commodity Summaries 2025 Data Release",
  "file_count": 5,
  "files": [
    {
      "name": "World_Data_Release_MCS_2025.zip",
      "content_type": "application/zip",
      "size_bytes": 22615,
      "url": "https://www.sciencebase.gov/catalog/file/get/...",
      "date_uploaded": "2025-01-29T15:26:45Z",
      "checksum": {
        "value": "e118dee17775f593724ee7da8b91acc4",
        "type": "MD5"
      }
    },
    ...
  ]
}
```

### 3. Resolve DOI (`resolve_doi`)

Resolve a DOI to its final landing page URL.

**Example:**
```json
{
  "function": "resolve_doi",
  "doi": "10.5066/P13XCP3R"
}
```

**Returns:**
```json
{
  "success": true,
  "doi": "10.5066/P13XCP3R",
  "doi_url": "https://doi.org/10.5066/P13XCP3R",
  "resolved_url": "https://www.sciencebase.gov/catalog/item/677eaf95d34e760b392c4970",
  "status": 200,
  "content_type": "application/json;charset=UTF-8"
}
```

## Supported DOI Types

### Publication DOIs
- Returns metadata from CrossRef in CSL JSON format
- Includes journal information, volume, issue, pages
- Citation counts when available
- Example: `10.1038/nature12373`

### Dataset DOIs
- Returns rich metadata from hosting platforms
- File listings with download URLs and checksums
- Extended provenance and contact information
- Example: `10.5066/P13XCP3R` (USGS ScienceBase)

## DOI Format

The skill accepts DOIs in multiple formats:
- `10.5066/P13XCP3R` (standard)
- `doi:10.5066/P13XCP3R` (with prefix)
- `DOI:10.5066/P13XCP3R` (uppercase prefix)

## Technical Details

- Uses HTTP content negotiation to request JSON metadata
- Follows redirects from doi.org to the canonical landing page
- Normalizes metadata from different sources into a consistent format
- Handles both ScienceBase (datasets) and CrossRef (publications) responses

## Error Handling

All functions return structured error responses:
```json
{
  "success": false,
  "error": "Description of the error",
  "doi": "10.xxxx/xxxxx"
}
```

Common errors:
- Invalid or non-existent DOI
- Network connectivity issues
- Unsupported DOI type or format
