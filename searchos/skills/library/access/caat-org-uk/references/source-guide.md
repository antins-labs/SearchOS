# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CAAT Company Data Access Skill

This skill fetches arms company data from the Campaign Against Arms Trade (CAAT) website at caat.org.uk.

## Overview

CAAT maintains a comprehensive database of arms companies with information including:
- Company activities (military equipment types)
- Aliases and subsidiary names
- SIPRI rankings (top arms companies)
- UK MoD procurement data
- Destination countries of concern
- Arms fair participation history

## Data Source

The skill uses two data sources:
1. **CAAT Data Hub API** (`data.caat.org.uk/data-hub/api/`) - Provides structured company data
2. **CAAT Website** (`caat.org.uk/data/companies/`) - Provides company descriptions and additional links

## Functions

### get_company

Get detailed data for a specific company using its URL slug.

**Parameters:**
- `slug` (required): The company's URL identifier

**Example:**
```json
{
  "function": "get_company",
  "slug": "thyssenkrupp"
}
```

**Returns:**
```json
{
  "slug": "thyssenkrupp",
  "company_name": "Thyssenkrupp",
  "id": 3322,
  "address_count": 84,
  "address_count_uk": 11,
  "activities": [
    "Bombs and missiles",
    "Weapon targeting and control",
    "Armoured vehicles",
    "Warships",
    "Aircraft",
    "Submarines",
    "Communications"
  ],
  "aliases": [
    {"name": "ATLAS ELEKTRONIK GmbH"},
    {"name": "Atlas Elektronik UK"},
    ...
  ],
  "sipri_ranking": {
    "rank": 61,
    "period": "2024",
    "value": "2290000000"
  },
  "destination_countries": [
    {"name": "United Arab Emirates", "slug": "united-arab-emirates", "score": "76"},
    ...
  ]
}
```

### get_company_by_name

Get company data by company name. The skill automatically converts the name to a URL slug.

**Parameters:**
- `name` (required): The company name

**Example:**
```json
{
  "function": "get_company_by_name",
  "name": "BAE Systems"
}
```

### search_companies

Search for companies by keyword (not yet implemented - placeholder for future functionality).

**Parameters:**
- `query` (required): Search keyword
- `limit` (optional): Maximum results (default: 20)

## Common Company Slugs

Here are some common arms company slugs you can use:
- `bae-systems` - BAE Systems
- `lockheed-martin` - Lockheed Martin
- `boeing` - Boeing
- `raytheon` - Raytheon
- `northrop-grumman` - Northrop Grumman
- `airbus` - Airbus
- `thales` - Thales
- `thyssenkrupp` - ThyssenKrupp
- `rolls-royce` - Rolls-Royce
- `general-dynamics` - General Dynamics

## Data Fields

| Field | Description |
|-------|-------------|
| `company_name` | Official company name |
| `activities` | Military equipment/activity types |
| `aliases` | Alternative names and subsidiaries |
| `sipri_ranking` | SIPRI Top 100 arms company ranking |
| `mod_procurement` | UK Ministry of Defence procurement data |
| `destination_countries` | Countries of concern receiving arms |
| `arms_fair_count` | Number of arms fairs attended |
| `address_count` | Total known addresses |
| `address_count_uk` | UK addresses |

## Notes

- The skill uses a direct API call when possible for faster, more reliable data retrieval
- Page scraping provides additional context like company descriptions
- Company slugs can be found in the URL pattern: `caat.org.uk/data/companies/{slug}/`
- Some companies may have limited data depending on CAAT's research
