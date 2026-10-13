# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# legislation.gov.uk Access Skill

Access UK legislation data from [legislation.gov.uk](https://www.legislation.gov.uk), the official UK government legislation repository managed by The National Archives.

## Features

- **Legislation Details**: Retrieve metadata, titles, descriptions, and links for specific acts, regulations, and other legislation
- **Index Listings**: Get lists of legislation by type and year/range
- **Atom Feeds**: Access structured XML feeds for legislation lists
- **XML Data**: Retrieve full XML data exports for legislation items
- **Search**: Search legislation by query, title, year, and type

## Legislation Types

Common legislation type codes:

| Code | Description |
|------|-------------|
| `ukpga` | UK Public General Acts |
| `ukla` | UK Local Acts |
| `ukppa` | UK Private and Personal Acts |
| `asp` | Acts of the Scottish Parliament |
| `mwa` | Acts of Senedd Cymru (Wales) |
| `anaw` | Acts of the National Assembly for Wales |
| `mnia` | Measures of the Northern Ireland Assembly |
| `aep` | Acts of the English Parliament |
| `aosp` | Acts of the Old Scottish Parliament |
| `ukcm` | Church Measures |
| `uksi` | UK Statutory Instruments |
| `wsi` | Welsh Statutory Instruments |
| `ssi` | Scottish Statutory Instruments |
| `nisr` | Northern Ireland Statutory Rules |

## Usage Examples

### Get Legislation Details

```json
{
  "function": "get_legislation",
  "url": "/ukpga/Geo6/14-15/27"
}
```

Or with components:
```json
{
  "function": "get_legislation",
  "legislation_type": "ukpga",
  "year": "Geo6",
  "chapter": "14-15/27"
}
```

### Get Index Listing

```json
{
  "function": "get_index",
  "legislation_type": "ukla",
  "year": "1951"
}
```

For a year range:
```json
{
  "function": "get_index",
  "legislation_type": "ukpga",
  "year": "1950-1959"
}
```

### Get Atom Feed

```json
{
  "function": "get_feed",
  "legislation_type": "ukla",
  "year": "1951"
}
```

With pagination:
```json
{
  "function": "get_feed",
  "legislation_type": "ukpga",
  "year": "2023",
  "page": 2
}
```

### Get XML Data

```json
{
  "function": "get_xml",
  "legislation_type": "ukpga",
  "year": "Geo6",
  "chapter": "14-15/27"
}
```

### Search Legislation

```json
{
  "function": "search",
  "query": "fire safety",
  "year": "2023"
}
```

## Response Structure

### get_legislation Response

```json
{
  "success": true,
  "url": "https://www.legislation.gov.uk/ukpga/Geo6/14-15/27",
  "title": "Fire Services Act 1951 (repealed)",
  "h1": "Fire Services Act 1951 (repealed)",
  "metadata": {
    "DC.title": "Fire Services Act 1951 (repealed)",
    "DC.description": "An Act to amend sections twenty-six and twenty-seven...",
    "Legislation.year": "1951"
  },
  "links": {
    "contents": "...",
    "data_xml": "...",
    "data_pdf": "..."
  }
}
```

### get_feed Response

```json
{
  "success": true,
  "url": "https://www.legislation.gov.uk/ukla/1951/data.feed",
  "feed_info": {
    "title": "Search Results",
    "total_results": 40,
    "items_per_page": 20
  },
  "entries": [
    {
      "title": "Liverpool Extension Act 1951",
      "id": "http://www.legislation.gov.uk/ukla/1951/cxlvi",
      "links": [...]
    }
  ],
  "count": 20
}
```

## Notes

- The site uses AWS WAF protection; browser automation is required
- Some content may be generated asynchronously (202 status)
- CSV downloads are available but trigger browser downloads
- Atom feeds (`data.feed`) provide the most reliable structured data for listings
- XML exports (`data.xml`) provide full legislative content in structured format
- Regnal years (e.g., "Geo6") are used for older legislation

## Data Sources

- Legislation detail pages: `/ukpga/Geo6/14-15/27`
- Index pages: `/ukla/1951`
- Atom feeds: `/ukla/1951/data.feed`
- XML data: `/ukpga/Geo6/14-15/27/data.xml`
- PDF exports: `/ukpga/Geo6/14-15/27/data.pdf`
- HTML snippets: `/ukpga/Geo6/14-15/27/data.xht`
