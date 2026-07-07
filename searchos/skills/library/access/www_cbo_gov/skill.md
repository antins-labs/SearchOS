# CBO (Congressional Budget Office) Data Access

## Overview

This skill provides programmatic access to the Congressional Budget Office's budget and economic data. The CBO website (www.cbo.gov) is protected by DataDome anti-bot protection that blocks automated requests with 403 Forbidden responses. This skill works around that limitation by using the Internet Archive's cached snapshots.

## Data Categories Available

The CBO provides extensive budget and economic projections:

1. **10-Year Budget Projections** - Monthly projections of federal revenues, spending, and deficits
2. **Long-Term Budget Projections** - 30-year budget outlook
3. **Historical Budget Data** - Historical budget tables and data
4. **10-Year Trust Fund Projections** - Social Security, Medicare, and other trust fund projections
5. **Revenue Projections, by Category** - Detailed revenue projections by tax type
6. **Spending Projections, by Budget Account** - Detailed spending projections
7. **Estimates of Automatic Stabilizers** - Economic stabilizer estimates
8. **Tax Parameters and Effective Marginal Tax Rates** - Tax policy data
9. **Economic Projections** - GDP, inflation, unemployment projections
10. **Potential GDP and Underlying Inputs** - Economic potential estimates
11. **Long-Term Economic Projections** - 30-year economic outlook
12. **Demographic Projections** - Population and demographic projections

## Functions

### list_categories

List all available data categories.

```python
result = await execute({"function": "list_categories"})
```

Returns:
- List of categories with file counts and latest update date
- Total number of files available

### get_category_files

Get all downloadable files for a specific category.

```python
result = await execute({
    "function": "get_category_files",
    "category": "Budget Projections"
})
```

Returns:
- List of files with download URLs
- Date/version information for each file
- File format (typically XLSX)

### get_publication

Get data files for a specific CBO publication by ID.

```python
result = await execute({
    "function": "get_publication",
    "publication_id": "59710"  # The Budget and Economic Outlook: 2024 to 2034
})
```

Returns:
- Publication title and date
- Associated downloadable files (PDF, XLSX, etc.)

### download_file

Download and parse an XLSX data file.

```python
result = await execute({
    "function": "download_file",
    "url": "https://web.archive.org/web/.../Budget-Projections.xlsx",
    "parse_content": true
})
```

Returns:
- File size and status
- Sheet names in the workbook
- Preview of content (first 100 text strings)

### get_catalog

Get the complete data catalog with all categories and files.

```python
result = await execute({"function": "get_catalog"})
```

### search_sitemap

Search the CBO sitemap for URLs (the sitemap is accessible without DataDome blocking).

```python
result = await execute({
    "function": "search_sitemap",
    "pattern": "budget"
})
```

## Example Usage

### Get latest budget projections

```python
# List available categories
categories = await execute({"function": "list_categories"})

# Get budget projection files
files = await execute({
    "function": "get_category_files",
    "category": "10-Year Budget Projections"
})

# Download the most recent file
if files["matched_categories"][0]["files"]:
    latest_file = files["matched_categories"][0]["files"][0]
    data = await execute({
        "function": "download_file",
        "url": latest_file["url"]
    })
    print(f"Sheets: {[s['name'] for s in data['sheets']]}")
```

### Get publication data

```python
# Get data for the 2024 Budget Outlook
pub = await execute({
    "function": "get_publication",
    "publication_id": "59710"
})

print(f"Title: {pub['title']}")
print(f"Files: {[f['name'] for f in pub['files']]}")
```

## File Formats

CBO data files are primarily provided in:
- **XLSX** - Excel format with multiple sheets
- **PDF** - Reports and documentation
- **ZIP** - Compressed collections

XLSX files contain structured data tables with:
- Table names (e.g., "Table 1-1", "Table 3-1")
- Data organized by fiscal year
- Historical data and projections
- Various economic and budget metrics

## Data Variables

Typical variables available in CBO data files:
- Revenues (individual income taxes, corporate taxes, payroll taxes)
- Outlays (mandatory, discretionary)
- Deficits/Surpluses
- Debt held by the public
- GDP projections
- Inflation projections
- Unemployment projections
- Trust fund balances
- Population projections

## Notes

### DataDome Protection

The main CBO website (www.cbo.gov) uses DataDome bot protection which:
- Returns 403 Forbidden for automated requests
- Requires JavaScript challenge solving
- Blocks standard HTTP clients

This skill bypasses the protection by using Internet Archive snapshots which:
- Provide full access to historical and current data
- Cache XLSX files for direct download
- Are updated regularly with new snapshots

### Data Freshness

- Internet Archive snapshots are typically 1-6 months old
- For the most current data, check the archive timestamp
- CBO typically updates major datasets monthly or quarterly
- Annual major reports (Budget Outlook, Economic Outlook) in January/February

### Rate Limits

- Be respectful when downloading large files
- The skill implements a 2 requests/second rate limit
- Consider caching results locally

## Source URLs

- Main data page: https://www.cbo.gov/data/budget-economic-data
- Publications: https://www.cbo.gov/publication/{id}
- Sitemap (accessible): https://www.cbo.gov/sitemap.xml
- Archive: https://web.archive.org/web/{timestamp}/https://www.cbo.gov/...