# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IDEA Special Voting Arrangements Data Access Skill

This skill extracts structured data from International IDEA's Special Voting Arrangements (SVA) database, available at [www.idea.int/data-tools/tools/special-voting-arrangements](https://www.idea.int/data-tools/tools/special-voting-arrangements).

## About the Data

International IDEA maintains a comprehensive database on Special Voting Arrangements (SVAs) used in elections worldwide. SVAs are mechanisms that allow voters to cast their ballots outside of standard in-person voting at a polling station on election day.

### SVA Types Covered

1. **In-Country Postal Voting** (`postal_in_country`) - Voters can vote by mail from within their country
2. **Early Voting** (`early_voting`) - Voters can cast ballots before election day at designated locations
3. **In-Country Proxy Voting** (`proxy_voting`) - Voters can authorize another person to vote on their behalf
4. **Mobile Voting** (`mobile_voting`) - Mobile ballot boxes brought to voters (e.g., hospitals, nursing homes)
5. **Data Explorer** (`data_explorer`) - Interactive tool to explore all SVA data
6. **Case Decisions** (`case_decisions`) - Database of court decisions related to SVAs

### Data Sources

- **Primary Source**: Legal provisions in electoral legislation and regulations of electoral management bodies
- **Data Collection**: Desk research methodology
- **Data Date**: Infographics based on data from March 2021
- **Verification**: Legal provisions checked against real-life implementation where possible

## Functions

### `get_overview`

Returns an overview of all available SVA data, including:
- Page title and description
- Methodology information
- List of available SVA types
- Data Studio embed information
- Related links

**Example:**
```python
result = await execute({"function": "get_overview"}, ctx)
```

### `get_sva_type`

Returns detailed data for a specific SVA type.

**Parameters:**
- `sva_type`: One of `overview`, `postal_in_country`, `early_voting`, `proxy_voting`, `mobile_voting`, `data_explorer`, `case_decisions`

**Example:**
```python
result = await execute({"function": "get_sva_type", "sva_type": "postal_in_country"}, ctx)
```

**Returns:**
- Title and description
- Methodology specific to the SVA type
- Content sections with explanations
- Data Studio embed URLs
- Related links

### `get_all`

Returns data for all SVA types in a single call.

**Example:**
```python
result = await execute({"function": "get_all"}, ctx)
```

### `get_datastudio_info`

Returns information about the Google Data Studio (Looker Studio) embeds used to visualize the data.

**Parameters:**
- `sva_type` (optional): Get embeds for a specific SVA type only

**Example:**
```python
result = await execute({"function": "get_datastudio_info"}, ctx)
result = await execute({"function": "get_datastudio_info", "sva_type": "early_voting"}, ctx)
```

### `search`

Search across all SVA content for specific terms.

**Parameters:**
- `query`: Search term

**Example:**
```python
result = await execute({"function": "search", "query": "methodology"}, ctx)
result = await execute({"function": "search", "query": "court"}, ctx)
```

## Data Structure

Each SVA type page contains:

```json
{
  "url": "https://www.idea.int/data-tools/tools/special-voting-arrangements/...",
  "title": "Page title",
  "description": "Meta description",
  "methodology": "Detailed methodology text",
  "sections": [
    {
      "heading": "Section heading",
      "content": "Section content"
    }
  ],
  "datastudio_embeds": [
    {
      "src": "https://datastudio.google.com/embed/reporting/...",
      "title": "Embed title",
      "report_id": "Google Data Studio report ID"
    }
  ],
  "related_links": [
    {
      "text": "Link text",
      "url": "https://..."
    }
  ],
  "types_of_svas": ["List of SVA types if applicable"]
}
```

## Data Visualization

The actual data visualizations are provided through Google Data Studio (now Looker Studio) embeds. These interactive dashboards show:

- **Maps**: Country-level implementation status
- **Tables**: Detailed country-by-country data
- **Charts**: Regional and global overviews

The embed URLs are provided in the skill output for direct access to these visualizations.

## Methodology Notes

From International IDEA:

> The global data was collected using desk research. Researchers coded the data based on specific regulations providing for SVAs in the electoral legislation and the regulations of electoral management bodies. Whenever possible, those legal provisions were checked against the real-life implementation of SVAs.

Key points:
- Data derived from legal texts (laws and regulations)
- Researchers made judgment calls where provisions were ambiguous
- Focus on legal provisions rather than implementation in some cases
- Data reflects status as of March 2021

## Use Cases

1. **Research**: Understand which countries use specific SVAs
2. **Legal Analysis**: Access case decisions database for SVA-related jurisprudence
3. **Comparative Studies**: Compare SVA implementation across countries/regions
4. **Policy Development**: Learn from international SVA practices

## Limitations

- The actual data tables are embedded via Google Data Studio and require JavaScript rendering
- Data is from March 2021 and may not reflect recent changes
- Case decisions database is a non-representative sample
- Some legal provisions may differ from actual implementation

## Related Resources

International IDEA also provides:
- Handbook on Special Voting Arrangements
- Regional reports (e.g., SVAs in Europe)
- Out-of-Country Voting publications
- Electoral management guidance
