# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Indochine UQAM Historical Dictionary Access Skill

This skill fetches dictionary entries from **indochine.uqam.ca**, a scholarly resource on the Indochina War (1945-1956) maintained by the Université du Québec à Montréal (UQAM).

## Overview

The Indochine UQAM website provides a comprehensive historical dictionary covering events, people, and concepts related to the Indochina War. The site offers content in both French (`/fr/le-dictionnaire/`) and English (`/en/historical-dictionary/`).

## Features

### `get_entry`

Fetches a specific dictionary entry by URL.

**Parameters:**
- `url` (required): Full URL to the dictionary entry

**Returns:**
- `article_id`: Numeric identifier from the URL
- `slug`: URL-friendly title slug
- `title`: Entry title (e.g., "COUP DE FORCE OF 9 MARCH 1945")
- `content`: Full article text content
- `cross_references`: List of terms highlighted in the text (e.g., "Tonkin", "Hanoi", "Viet Minh")
- `see_also`: Related dictionary entries with titles and URLs
- `language`: Detected language ("fr" or "en")
- `source`: Always "indochine.uqam.ca"

**Example:**

```json
{
  "function": "get_entry",
  "url": "https://indochine.uqam.ca/en/historical-dictionary/320-coup-de-force-of-9-march-1945.html"
}
```

**Response:**

```json
{
  "success": true,
  "url": "https://indochine.uqam.ca/en/historical-dictionary/320-coup-de-force-of-9-march-1945.html",
  "data": {
    "article_id": 320,
    "slug": "coup-de-force-of-9-march-1945",
    "title": "COUP DE FORCE OF 9 MARCH 1945",
    "content": "Because of Vichy France's collaboration with Nazi Germany...",
    "cross_references": ["Tonkin", "Hanoi", "Paul Mus", "Viet Minh"],
    "see_also": [
      {"title": "AUGUST REVOLUTION", "url": "https://indochine.uqam.ca/en/historical-dictionary/88-august-revolution-cach-mng-thang-tam-1945.html"},
      {"title": "CIVIL WAR", "url": "https://indochine.uqam.ca/en/historical-dictionary/289-civil-war.html"}
    ],
    "language": "en",
    "source": "indochine.uqam.ca"
  }
}
```

## URL Patterns

The dictionary entries follow these URL patterns:

- **French**: `https://indochine.uqam.ca/fr/le-dictionnaire/{id}-{slug}.html`
- **English**: `https://indochine.uqam.ca/en/historical-dictionary/{id}-{slug}.html`

## Content Structure

Each dictionary entry contains:

1. **Title**: The main heading (e.g., "COUP DE FORCE OF 9 MARCH 1945")
2. **Content**: Scholarly article text explaining the topic
3. **Cross-references**: Terms marked with `<strong>` tags within the text, indicating important related concepts
4. **See also**: Links to related dictionary entries at the end of the article

## Use Cases

- Retrieve detailed historical information about Indochina War topics
- Access cross-referenced terms for building knowledge graphs
- Navigate between related entries via the "see also" links
- Compare French and English versions of the same entry

## Notes

- The skill extracts structured content from the `.article` container element
- Cross-references are terms highlighted in bold within the article text
- The "See also" section provides navigation to related entries
- Language is auto-detected from the URL path if not specified
