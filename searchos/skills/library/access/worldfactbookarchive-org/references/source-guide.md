# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# World Factbook Archive Access Skill

This skill retrieves historical field data from the CIA World Factbook Archive at [worldfactbookarchive.org](https://worldfactbookarchive.org).

## Overview

The World Factbook Archive contains 36 years of CIA World Factbook data (1990-2025) with over 1 million parsed fields across 281 entities. This skill provides structured access to the historical data for any country and field.

## Functions

### get_field_history

Retrieves historical data records for a specific country and field across all available editions.

**Parameters:**
- `country_code` (required): Two-letter country code (e.g., 'CN' for China, 'US' for United States, 'RU' for Russia)
- `field_name` (required): Field name as it appears in the archive (e.g., 'Land boundaries', 'Coastline', 'Population')
- `start_year` (optional): Filter to only include editions from this year onwards
- `end_year` (optional): Filter to only include editions up to this year

**Returns:**
- `success`: Boolean indicating if the operation succeeded
- `country_code`: The country code queried
- `field_name`: The field name queried
- `url`: The archive URL that was accessed
- `total_entries`: Number of records returned
- `entries`: Array of records, each containing:
  - `edition`: Year of the CIA World Factbook edition
  - `series`: Data series name (often same as field name or 'total')
  - `value`: Parsed numeric value
  - `source_text`: Original CIA source text

**Example:**
```json
{
  "function": "get_field_history",
  "country_code": "CN",
  "field_name": "Land boundaries",
  "start_year": 2020
}
```

### get_field_metadata

Retrieves metadata about a field for a country, including edition counts and date ranges.

**Parameters:**
- `country_code` (required): Two-letter country code
- `field_name` (required): Field name

**Returns:**
- `success`: Boolean indicating if the operation succeeded
- `country_code`: The country code queried
- `country_name`: Full country name
- `field_name`: The field name as displayed on the page
- `url`: The archive URL
- `page_title`: Page title
- `stats`: Object containing:
  - `source_editions`: Total number of CIA editions with data
  - `first_record`: Year of first available record
  - `latest_record`: Year of most recent record
  - `distinct_runs`: Number of distinct text variations
  - `missing_editions`: Number of editions without data
  - `total_observations`: Number of data points

**Example:**
```json
{
  "function": "get_field_metadata",
  "country_code": "CN",
  "field_name": "Coastline"
}
```

## Common Field Names

Some commonly available fields include:
- Population
- Land boundaries
- Coastline
- Area
- GDP (purchasing power parity)
- Life expectancy at birth
- Military expenditures
- Internet users
- And many more...

## Country Codes

The archive uses two-letter country codes. Some examples:
- CN: China
- US: United States
- RU: Russia
- IN: India
- BR: Brazil
- JP: Japan
- DE: Germany
- FR: France
- GB: United Kingdom

## Notes

- The archive contains data from 1990 to 2025 (36 editions)
- Some fields may have "distinct runs" indicating different text formats across years
- The `source_text` field contains the original CIA wording which may include additional context
- Pagination is handled automatically to retrieve all available records
- The skill uses browser automation to handle the site's dynamic content loading
