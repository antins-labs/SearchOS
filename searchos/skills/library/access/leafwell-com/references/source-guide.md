# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Leafwell Marijuana Legal Status Scraper

This skill extracts structured legal status information from Leafwell's "Is Marijuana Legal in X?" articles.

## Features

- **Country-based lookup**: Query legal status by country name
- **URL-based lookup**: Extract data from a specific Leafwell article URL
- **Structured data extraction**: Returns normalized legal status for medical, recreational, CBD, and cultivation
- **Penalty information**: Extracts details about fines, prison sentences, and other penalties
- **Article metadata**: Includes author, publication date, and last modified date

## Usage

### Get legal status by country

```json
{
  "function": "get_by_country",
  "country": "Qatar"
}
```

### Get legal status by URL

```json
{
  "function": "get_by_url",
  "url": "https://leafwell.com/blog/is-marijuana-legal-in-albania"
}
```

### Search countries (limited functionality)

```json
{
  "function": "search",
  "query": "marijuana laws europe"
}
```

## Output Structure

```json
{
  "country": "Qatar",
  "url": "https://leafwell.com/blog/is-marijuana-legal-in-qatar",
  "title": "Is Marijuana Legal in Qatar? - Leafwell",
  "description": "Qatar upholds a strict stance against cannabis...",
  "author": "Emma Stone",
  "date_published": "2023-08-04T05:21:27",
  "date_modified": "2025-10-03T09:01:22",
  "legal_status": {
    "medical": "illegal",
    "recreational": "illegal",
    "cbd": null,
    "cultivation": "illegal"
  },
  "penalties": ["up to 20 years in prison", "heavy fines"],
  "key_facts": [
    "Medical and recreational marijuana is illegal in Qatar...",
    "Cannabis is considered an illicit narcotic..."
  ],
  "sections": [
    {
      "heading": "Medical Marijuana Laws in Qatar",
      "paragraphs": ["..."],
      "list_items": ["..."]
    }
  ]
}
```

## Supported Countries

Leafwell maintains articles for many countries worldwide. The URL pattern is:
```
https://leafwell.com/blog/is-marijuana-legal-in-{country-slug}
```

Examples:
- `is-marijuana-legal-in-qatar`
- `is-marijuana-legal-in-albania`
- `is-marijuana-legal-in-the-united-arab-emirates`
- `is-marijuana-legal-in-the-united-states`

## Data Extraction

The skill extracts:
1. **Legal status**: Medical, recreational, CBD, and cultivation legality
2. **Penalties**: Fines, prison sentences, deportation, death penalty
3. **Key facts**: Important information from the article introduction
4. **Full sections**: All article sections with headings, paragraphs, and list items

## Limitations

- The search function has limited functionality as Leafwell doesn't provide a public search API
- Legal status extraction relies on pattern matching and may not capture all nuances
- Some articles may have incomplete information for certain status types
