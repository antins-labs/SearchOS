# GOV.UK UK House Price Index Access Skill

Fetch UK House Price Index data from GOV.UK, including collection pages, statistical data download pages, and direct CSV files from the Land Registry data portal.

## Overview

The UK House Price Index (UK HPI) is published monthly by HM Land Registry. This skill provides access to:

1. **Collection pages** - Listings of monthly reports and data download pages
2. **Statistical data sets pages** - Pages containing direct CSV download links
3. **CSV files** - Direct download from the Land Registry data portal

## URL Patterns

GOV.UK uses predictable URL patterns for UK HPI data:

- Main collection: `https://www.gov.uk/government/collections/uk-house-price-index-reports`
- Year collection: `https://www.gov.uk/government/collections/uk-house-price-index-reports-{year}`
- Data downloads: `https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-{month}-{year}`
- Statistics report: `https://www.gov.uk/government/statistics/uk-house-price-index-for-{month}-{year}`
- CSV files: `https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/{filename}.csv`

## Functions

### get_collection_items

Parse a GOV.UK collection page and extract document listings.

**Parameters:**
- `url` (required): Full URL of the collection page

**Example:**
```python
result = await execute({
    "function": "get_collection_items",
    "url": "https://www.gov.uk/government/collections/uk-house-price-index-reports"
})
```

**Returns:**
- `statistics`: List of statistics report items
- `data_downloads`: List of data download page items
- `collections`: List of sub-collection items (year archives)
- `publications`: List of publication items
- Each item has `title`, `url`, `date`, and `type`

### get_data_downloads

Get CSV download links from a statistical data sets page.

**Parameters:**
- `url` (required): Full URL of the data download page

**Example:**
```python
result = await execute({
    "function": "get_data_downloads",
    "url": "https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-february-2026"
})
```

**Returns:**
- `csv_downloads`: List of CSV files with `name`, `url`, and `filename`
- `xlsx_downloads`: List of Excel files (if any)
- `page_title`: Title of the page
- `description`: Meta description

### download_csv

Download a CSV file from the Land Registry data portal.

**Parameters:**
- `url` (required): Full URL of the CSV file
- `max_bytes` (optional): Maximum file size in bytes (default: 100MB)
- `include_data` (optional): Include raw CSV data (default: true)

**Example:**
```python
result = await execute({
    "function": "download_csv",
    "url": "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/Average-prices-2026-02.csv",
    "include_data": false  # Get metadata only
})
```

**Returns:**
- `success`: Boolean
- `size_bytes`: File size
- `row_count`: Number of data rows
- `headers`: Column headers
- `data`: Full CSV text (if `include_data=true`)
- `preview`: First 10 lines preview

### search_hpi_data

Search for UK HPI data by year and/or month.

**Parameters:**
- `year` (optional): Year to search (e.g., 2024)
- `month` (optional): Month number (1-12) or name ("january", etc.)
- `data_type` (optional): "downloads", "statistics", or "all" (default)

**Example:**
```python
# Search for February 2026 data
result = await execute({
    "function": "search_hpi_data",
    "year": 2026,
    "month": "february",
    "data_type": "downloads"
})

# Search for all 2024 releases
result = await execute({
    "function": "search_hpi_data",
    "year": 2024
})
```

**Returns:**
- `urls`: Constructed URLs for the search
- `validated`: Validation results with page status and content
- For collections: includes list of items found
- For data downloads: includes list of CSV files available

### get_latest_hpi_release

Get the most recent UK HPI release information.

**Example:**
```python
result = await execute({
    "function": "get_latest_hpi_release"
})
```

**Returns:**
- `latest_statistics`: Most recent statistics report item
- `latest_data_downloads`: Most recent data download page item
- `available_csvs`: CSV files from the latest data download page
- `all_statistics`: Last 12 statistics reports
- `all_data_downloads`: Last 12 data download pages

## Available CSV Files

The UK HPI data download pages typically include these CSV files:

1. **UK-HPI-full-file-{YY-MM}.csv** - Complete dataset
2. **Average-prices-{YY-MM}.csv** - Average prices by region
3. **Average-prices-Property-Type-{YY-MM}.csv** - Average prices by property type
4. **Sales-{YY-MM}.csv** - Sales volumes
5. **Cash-mortgage-sales-{YY-MM}.csv** - Sales by cash/mortgage
6. **First-Time-Buyer-Former-Owner-Occupied-{YY-MM}.csv** - Buyer type breakdown
7. **New-and-Old-{YY-MM}.csv** - New vs existing properties
8. **Indices-{YY-MM}.csv** - Price indices
9. **Indices-seasonally-adjusted-{YY-MM}.csv** - Seasonally adjusted indices
10. **Average-price-seasonally-adjusted-{YY-MM}.csv** - Seasonally adjusted prices
11. **Repossession-{YY-MM}.csv** - Repossession data

## Data Structure

CSV files typically contain:
- Date (monthly, starting from 1968 for some series)
- Region identifiers (nation, county, local authority)
- Price data (average prices, indices, changes)
- Volume data (sales counts)

## Notes

- All HTTP requests are made directly without browser automation
- UTM tracking parameters are automatically removed from URLs
- The Land Registry data portal allows direct CSV downloads without authentication
- Data files can be large (several MB for full datasets)
- Monthly data is typically published around the 3rd week of the following month