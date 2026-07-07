# GovInfo Access Skill

Access government budget tables and documents from [www.govinfo.gov](https://www.govinfo.gov).

## Overview

This skill provides programmatic access to the GovInfo repository of U.S. government publications, with specialized support for budget documents and historical tables. It can retrieve MODS metadata, parse XLSX spreadsheets, and provide direct download URLs for government documents.

## Key Features

- **MODS Metadata Retrieval**: Fetch comprehensive metadata about packages and their constituent granules
- **XLSX Parsing**: Download and parse budget spreadsheet data into structured JSON
- **Granule Search**: Search for specific tables within budget packages by title or section number
- **Direct URLs**: Get direct links to PDF, XLSX, and other file formats

## Supported Document Collections

The GovInfo API supports various collections including:

- **Budget Documents**: Historical Tables, Budget of the United States
- **Congressional Records**: Congressional Record, Federal Register
- **Statutes**: United States Code, Public Laws
- **Regulations**: Code of Federal Regulations

## Examples

### Get Package Metadata

```json
{
  "function": "get_package_metadata",
  "package_id": "BUDGET-2025-TAB"
}
```

Returns titles, identifiers, genres, and a complete list of all granules (individual tables) in the package.

### List Package Contents

```json
{
  "function": "list_package_contents",
  "package_id": "BUDGET-2025-TAB"
}
```

Returns a simplified list of all granules with their granule IDs, titles, and direct URLs.

### Search for Tables

Search for tables containing "receipts":

```json
{
  "function": "search_budget_tables",
  "package_id": "BUDGET-2025-TAB",
  "query": "receipts"
}
```

Filter by section:

```json
{
  "function": "search_budget_tables",
  "package_id": "BUDGET-2025-TAB",
  "section": "1",
  "max_results": 10
}
```

### Parse a Budget Table

Parse Table 1.1 (Summary of Receipts, Outlays, and Surpluses or Deficits):

```json
{
  "function": "get_granule_xlsx",
  "package_id": "BUDGET-2025-TAB",
  "granule_id": "BUDGET-2025-TAB-2-1",
  "max_rows": 50
}
```

Returns:
- Parsed spreadsheet rows with cells
- Column headers from the first rows
- Numeric values converted to numbers
- Text values preserved

### Get PDF Download URL

```json
{
  "function": "get_granule_pdf_url",
  "package_id": "BUDGET-2025-TAB",
  "granule_id": "BUDGET-2025-TAB-2-1"
}
```

Returns the direct PDF URL and checks accessibility.

### Get Raw XLSX Data

For clients that want to parse the XLSX themselves:

```json
{
  "function": "get_granule_xlsx",
  "package_id": "BUDGET-2025-TAB",
  "granule_id": "BUDGET-2025-TAB-2-1",
  "raw_data": true
}
```

Returns base64-encoded XLSX bytes.

## Data Sources

### MODS Metadata

Metadata is retrieved from the MODS (Metadata Object Description Schema) endpoint:
```
https://www.govinfo.gov/metadata/pkg/{package_id}/mods.xml
```

This provides structured bibliographic information including titles, identifiers, subjects, and relationships between packages and granules.

### XLSX Spreadsheets

Budget tables are available as Excel spreadsheets:
```
https://www.govinfo.gov/content/pkg/{package_id}/xls/{granule_id}.xlsx
```

These are parsed directly into structured JSON for easy consumption.

### PDF Documents

Most granules also have PDF versions:
```
https://www.govinfo.gov/content/pkg/{package_id}/pdf/{granule_id}.pdf
```

## Common Package IDs

- `BUDGET-2025-TAB`: Historical Tables, Budget FY 2025
- `BUDGET-2024-TAB`: Historical Tables, Budget FY 2024
- `BUDGET-{year}-TAB`: Historical Tables for any fiscal year

Granule IDs within budget packages follow the pattern:
- `BUDGET-{year}-TAB-{section}-{table}`: e.g., `BUDGET-2025-TAB-2-1` for Section 1, Table 1.1

Note: Section numbers in granule IDs don't always match section numbers in titles due to the introduction being section 1 in the package.

## Rate Limits and Best Practices

The GovInfo service is generally accessible without API keys for basic access. For heavy usage:
- Implement rate limiting of 10-20 requests per second
- Cache metadata responses locally
- Use PREMIS metadata for preservation information

## Error Handling

All functions return structured error objects:
```json
{
  "error": "Missing required parameter: package_id",
  "function": "get_package_metadata"
}
```

Check for the `error` key in responses before processing data.