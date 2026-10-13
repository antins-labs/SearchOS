# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Bundestag.de Access Skill

This skill retrieves structured information from the German Bundestag (Federal Diet) official website at [bundestag.de](https://www.bundestag.de).

## Features

### Seat Distribution
Retrieves the current distribution of seats in the German Bundestag, including:
- Total number of seats
- Seats per political party/fraction
- Electoral term information
- Historical comparison with previous elections

### Text Archive Articles
Extracts content from Bundestag text archive articles, which contain:
- Official election results
- Legislative news and updates
- Parliamentary documentation
- Detailed analysis of political developments

### General Page Content
Extracts structured content from any Bundestag webpage, including:
- Title and headline
- Main article content
- Metadata (description, keywords)

## Available Functions

### `get_seat_distribution`
Get the current seat distribution in the Bundestag.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "data": {
    "title": "Distribution of seats in the German Bundestag's 21st electoral term",
    "electoral_term": 21,
    "total_seats": 630,
    "seat_distribution": {
      "CDU": 164,
      "CSU": 44,
      "SPD": 120,
      "AfD": 152,
      "Greens": 85,
      "Left Party": 64
    },
    "description": "...",
    "sources": {
      "main_page": "https://www.bundestag.de/en/parliament/plenary/distributionofseats",
      "archive_article": "https://www.bundestag.de/en/documents/textarchive/kw09-election-1055556"
    }
  }
}
```

### `get_text_archive_article`
Get content from a specific text archive article.

**Parameters:**
- `url` (required): The URL of the text archive article

**Example:**
```json
{
  "function": "get_text_archive_article",
  "url": "https://www.bundestag.de/en/documents/textarchive/kw09-election-1055556"
}
```

### `get_page_content`
Get general content from any Bundestag page.

**Parameters:**
- `url` (required): The URL of the page to fetch

**Example:**
```json
{
  "function": "get_page_content",
  "url": "https://www.bundestag.de/en/parliament/plenary/distributionofseats"
}
```

## Notes

- The Bundestag website uses JavaScript for interactive charts, but the underlying data is available in the HTML content
- Seat distribution data is extracted from both the main visualization page and related text archive articles
- The skill uses direct HTTP requests for reliability and speed
- All URLs must be under the `bundestag.de` domain

## Data Sources

- **Seat Distribution Page**: `/en/parliament/plenary/distributionofseats`
- **Text Archive**: `/en/documents/textarchive/`
- **Election Results**: Articles in the text archive contain detailed election statistics

## German Political Parties

The skill recognizes the following major parties:
- **CDU** - Christian Democratic Union
- **CSU** - Christian Social Union (Bavaria)
- **SPD** - Social Democratic Party
- **AfD** - Alternative for Germany
- **Greens** - Alliance 90/The Greens
- **Left Party** - The Left
- **FDP** - Free Democratic Party
- **BSW** - Sahra Wagenknecht Alliance
- **SSW** - South Schleswig Voters' Association (minority party)
