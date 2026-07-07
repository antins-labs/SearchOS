# Fortune.com Access Skill

This skill provides programmatic access to Fortune.com's Global 500 rankings and company profile data.

## Overview

Fortune.com publishes various rankings including the Fortune Global 500, Fortune 500, and other business rankings. This skill extracts data from:

- **Global 500 Rankings**: Annual list of the world's 500 largest companies by revenue (available for years 1995-2025)
- **Company Profiles**: Detailed profiles with financial metrics, rankings history, and company information

## Data Source

Data is extracted from server-side rendered pages:
1. **HTML Table Parsing**: Full ranking tables are parsed directly from the rendered HTML
2. **__NEXT_DATA__ JSON**: Embedded JSON data provides additional metadata, available years, and company details

## Functions

### get_global500_ranking

Get the complete Fortune Global 500 ranking list.

**Parameters:**
- `year` (string, optional): Year of ranking. Default: "latest". Available: 1995-2025
- `limit` (integer, optional): Maximum results. Default: 500, Max: 500
- `offset` (integer, optional): Skip N results for pagination. Default: 0

**Example:**
```python
# Get latest Global 500
result = await execute({
    "function": "get_global500_ranking"
})

# Get 2024 ranking, top 10
result = await execute({
    "function": "get_global500_ranking",
    "year": "2024",
    "limit": 10
})
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "current_year": 2025,
    "available_years": ["2025", "2024", "2023", ...],
    "title": "Fortune Global 500",
    "description": "The corporations on our annual list...",
    "total_companies": 500,
    "rankings": [
      {
        "rank": 1,
        "name": "Walmart",
        "company_slug": "/company/walmart/",
        "company_url": "https://fortune.com/company/walmart/",
        "revenue": "$680,985",
        "revenue_change": "5.1%",
        "profit": "$19,436",
        "profit_change": "25.3%",
        "assets": "$260,823",
        "employees": "2,100,000",
        "rank_change": "-",
        "years_on_list": "31"
      }
    ]
  }
}
```

### get_company_profile

Get detailed company profile with financial data and ranking history.

**Parameters:**
- `company` (string, required): Company slug, path, or full URL
  - Examples: "walmart", "state-grid", "/company/amazon-com/", "https://fortune.com/company/apple/"

**Example:**
```python
result = await execute({
    "function": "get_company_profile",
    "company": "walmart"
})
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "name": "Walmart",
    "slug": "/company/walmart/",
    "description": "Walmart is the world's second-largest retailer...",
    "company_info": {
      "Country": "U.S.",
      "Headquarters": "Bentonville, Ark.",
      "Industry": "General Merchandisers",
      "CEO": "John R. Furner",
      "Revenues ($M)": "$713,163",
      "Profits ($M)": "$21,893",
      "Market value ($M)": "$990,810",
      "Number of employees": "2,100,000",
      "Ticker": "WMT",
      "Company type": "Public"
    },
    "rankings": [
      {
        "title": "Fortune 500",
        "year": "2026",
        "rank": 2,
        "permalink": "..."
      },
      {
        "title": "Fortune Global 500",
        "year": "2025",
        "rank": 1,
        "permalink": "..."
      }
    ],
    "data_tables": [...]
  }
}
```

### search_companies

Search for companies in the Global 500 by name.

**Parameters:**
- `query` (string, optional): Company name search query
- `year` (string, optional): Ranking year. Default: "latest"
- `limit` (integer, optional): Maximum results. Default: 50

**Example:**
```python
result = await execute({
    "function": "search_companies",
    "query": "tech",
    "limit": 10
})
```

## Use Cases

1. **Market Research**: Analyze top global companies by revenue
2. **Competitive Intelligence**: Track company rankings over time
3. **Financial Analysis**: Get key financial metrics for major corporations
4. **Lead Generation**: Build lists of target companies by industry or size

## Data Notes

- Revenue and profit figures are in millions of USD ($M)
- Rankings are updated annually
- Historical data available from 1995
- Company profiles include data from multiple Fortune rankings (Global 500, Fortune 500, Best Companies, etc.)

## Rate Limits

- 2 requests per second
- 30 requests per minute

No authentication required for public data.