# CAAC Statistics Bulletins Access Skill

Fetches aviation statistical bulletins from the Civil Aviation Administration of China (CAAC) website at www.caac.gov.cn.

## Overview

This skill provides access to CAAC's statistical publications including:

- **Monthly Production Statistics** (月度运输生产统计) - Monthly indicators of civil aviation production
- **Annual Development Reports** (年度民航发展报告) - Comprehensive yearly development statistics  
- **Annual Airport Production Bulletins** (年度机场生产公报) - Yearly airport throughput statistics

All documents are published as PDF or Excel attachments on individual bulletin pages.

## Available Functions

### 1. list_bulletins

List available bulletins by category.

**Parameters:**
- `category` (optional, default: "monthly_production")

**Categories:**
- `monthly_production` - Monthly transport production statistics
- `annual_development` - Annual civil aviation development reports
- `annual_airport` - Annual airport production bulletins

**Returns:**
- List of bulletins with titles, URLs, and publication dates
- Most recent bulletins appear first (up to 50)

**Example:**
```python
{
  "function": "list_bulletins",
  "category": "annual_airport"
}
```

### 2. get_bulletin

Get details of a specific bulletin including metadata and attachment URLs.

**Parameters:**
- `url` (required) - URL of the bulletin page

**Returns:**
- Title and metadata (publication date, source, etc.)
- List of attachments (PDFs, Excel files) with download URLs
- Content preview

**Example:**
```python
{
  "function": "get_bulletin",
  "url": "https://www.caac.gov.cn/XXGK/XXGK/TJSJ/202503/t20250314_226932.html"
}
```

### 3. download_attachment

Download a file attachment and return as base64.

**Parameters:**
- `url` (required) - URL of the file to download
- `max_size_mb` (optional, default: 10) - Maximum file size limit

**Returns:**
- File content as base64-encoded string
- Filename and content type
- File size information

**Example:**
```python
{
  "function": "download_attachment",
  "url": "https://www.caac.gov.cn/XXGK/XXGK/TJSJ/202503/P020250314353469776556.pdf",
  "max_size_mb": 20
}
```

### 4. search_bulletins

Search for bulletins by keywords and/or year across all categories.

**Parameters:**
- `keywords` (optional) - Keywords to search (matched against title)
- `year` (optional) - Year to filter by

**Returns:**
- Matching bulletins from all categories
- Up to 50 results

**Example:**
```python
{
  "function": "search_bulletins",
  "year": "2024"
}
```

## Data Structure

## Sample Documents

### Monthly Production Statistics
- 中国民航2026年4月份主要生产指标统计 (April 2026)
- Contains passenger traffic, cargo volume, flight operations

### Annual Development Reports  
- 2025年民航行业发展统计公报 (FY2025 report)
- Comprehensive industry statistics and analysis

### Annual Airport Production Bulletins
- 2024年全国民用运输机场生产统计公报
- Includes passenger throughput rankings (Excel attachment)
- Airport operations data and trends

## Notes

- All documents are in Chinese
- PDFs contain the main statistical report
- Excel files provide detailed data tables (e.g., airport rankings)
- Bulletins are typically published with a few months delay
- Historical data goes back to 2006 for airport production stats

## Technical Details

- Uses direct HTTP requests (no JavaScript rendering needed)
- PDF/Excel files downloaded as binary content
- All content accessed through official CAAC website
- No authentication required