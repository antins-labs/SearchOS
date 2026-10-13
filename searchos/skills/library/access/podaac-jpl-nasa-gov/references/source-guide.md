# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# PO.DAAC Dataset Access Skill

This skill extracts structured metadata and download links from PO.DAAC (Physical Oceanography Distributed Active Archive Center) dataset landing pages at `podaac.jpl.nasa.gov`.

## Features

### get_dataset
Fetches comprehensive metadata for a specific PO.DAAC dataset including:
- **Core Metadata**: Title, description, version, DOI, short name
- **Temporal Coverage**: Start/end dates
- **Processing Information**: Processing level, format
- **Platform/Sensor**: Satellite missions and instruments
- **Provider Information**: Creator, release date, contact
- **Data Access Links**:
  - Earthdata Search URL (for browsing granules)
  - CMR Virtual Directory (direct data access)
  - PO.DAAC Data Subscriber tool (for automated downloads)
- **JSON-LD**: Full schema.org Dataset structured data

### search_datasets
Searches PO.DAAC data holdings via NASA's Common Metadata Repository (CMR):
- Returns matching datasets with key metadata
- Includes concept IDs for direct CMR access
- Provides dataset URLs for further exploration

## Usage Examples

### Get Dataset Metadata
```json
{
  "function": "get_dataset",
  "url": "https://podaac.jpl.nasa.gov/dataset/NASA_SSH_GMSL_INDICATOR"
}
```

### Search Datasets
```json
{
  "function": "search_datasets",
  "query": "sea level altimetry",
  "limit": 5
}
```

## Data Access

PO.DAAC datasets are hosted on NASA's Earthdata Cloud. To download data:
1. Use the `earthdata_search` URL to browse and select granules
2. Use the `cmr_virtual_directory` for programmatic access
3. Use the PO.DAAC Data Subscriber tool for automated downloads: https://github.com/podaac/data-subscriber

## Notes

- Dataset pages use JavaScript rendering; this skill uses browser automation
- Page load timeouts may occur but partial content is still extracted
- CMR collection IDs (e.g., C3478934705-POCLOUD) can be used with NASA's CMR API
- All PO.DAAC data is freely accessible under Creative Commons BY 4.0 license
