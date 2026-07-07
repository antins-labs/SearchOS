# White House OMB Historical Tables

Access U.S. federal budget historical tables from the White House Office of Management and Budget (OMB). This skill provides programmatic access to download and search through 57+ Excel tables containing comprehensive historical data on government receipts, outlays, debt, and other budget metrics.

## Overview

The Historical Tables provide data from 1789 to the present, covering:
- Budget totals and surpluses/deficits
- Government receipts by source
- Outlays by function, agency, and category
- Budget authority
- Federal debt
- GDP and economic indicators
- Social Security and health programs
- Federal employment

## Available Functions

### list_tables
List all available historical tables with complete metadata including table numbers, descriptions, URLs, and fiscal year.

```python
result = await execute({"function": "list_tables"})
# Returns: count, fiscal_year, sections[], tables[]
```

### get_table_info
Get detailed information for a specific table by its number.

```python
result = await execute({
    "function": "get_table_info",
    "table_number": "7.1"  # Federal Debt table
})
```

### download_table
Download an Excel table by table number. Optionally return the file content as base64.

```python
# Get download URL and metadata
result = await execute({
    "function": "download_table",
    "table_number": "1.1"
})

# Include file content (base64 encoded)
result = await execute({
    "function": "download_table",
    "table_number": "1.1",
    "return_content": True
})
```

### search_tables
Search for tables by keyword in their description or section topic.

```python
result = await execute({
    "function": "search_tables",
    "query": "debt"
})
# Returns tables matching "debt" sorted by relevance
```

### get_tables_by_section
Get all tables within a specific section category.

```python
result = await execute({
    "function": "get_tables_by_section",
    "section": "07"  # Federal Debt section
})
```

### get_sections
List all section categories with their topics and table counts.

```python
result = await execute({"function": "get_sections"})
# Returns: count, fiscal_year, sections[{section_number, topic, table_count, table_numbers}]
```

### get_intro_pdf
Get the introduction PDF that explains the tables and methodology.

```python
result = await execute({
    "function": "get_intro_pdf",
    "return_content": False  # Set True to get base64 content
})
```

## Table Sections

The tables are organized into 16 sections:

| Section | Topic |
|---------|-------|
| 01 | Budget Totals |
| 02 | Receipts |
| 03 | Outlays by Function |
| 04 | Outlays by Agency |
| 05 | Budget Authority |
| 06 | Composition of Outlays |
| 07 | Federal Debt |
| 08 | Budget Enforcement Act Categories |
| 09 | Investment and R&D |
| 10 | GDP and Deflators |
| 11 | Payments for Individuals |
| 12 | Grants to State/Local Governments |
| 13 | Social Security Trust Funds |
| 14 | Total Government Finances |
| 15 | Health Programs |
| 16 | Federal Employment |

## Common Use Cases

### Find tables about federal debt
```python
result = await execute({"function": "search_tables", "query": "debt"})
# or
result = await execute({"function": "get_tables_by_section", "section": "07"})
```

### Download the summary budget table
```python
result = await execute({
    "function": "download_table",
    "table_number": "1.1",
    "return_content": True
})
# Table 1.1: Summary of Receipts, Outlays, and Surpluses or Deficits: 1789-2025
```

### Get GDP and economic indicators
```python
result = await execute({"function": "get_table_info", "table_number": "10.1"})
# Table 10.1: Gross Domestic Product and Deflators Used in the Historical Tables
```

## Response Format

All functions return a structured dictionary with:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (only present if success is False)
- Function-specific data fields

Download responses include:
- `table`: Metadata about the downloaded table
- `content_base64`: Base64-encoded file content (if return_content=True)

## Data Notes

- Tables are Excel files in .xlsx format
- Data typically spans from 1789 to current fiscal year projections
- Tables are updated annually with each budget release
- URLs follow the pattern: `hist{section}z{subsection}_fy{year}.xlsx`
- Fiscal year typically reflects the budget year (e.g., FY2027 for the 2027 budget)

## Source

Data sourced from: https://www.whitehouse.gov/omb/information-resources/budget/historical-tables/