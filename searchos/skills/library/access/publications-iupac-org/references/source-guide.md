# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IUPAC Publications Access Skill

This skill retrieves content from IUPAC's Chemistry International newsmagazine at publications.iupac.org.

## Overview

Chemistry International is IUPAC's newsmagazine, publishing news about IUPAC activities, nomenclature recommendations, project updates, and chemistry community information. The magazine is organized by volume and issue number.

## Available Functions

### get_article

Fetches and parses a single article from the IUPAC publications website.

**Parameters:**
- `url` (required): The full URL of the article

**Returns:**
- Article title
- Publication metadata (volume, number, date, section)
- Article content as a list of paragraphs
- Images (if any)
- Content length

**Example:**
```
URL: https://publications.iupac.org/ci/2012/3404/iw1_periodic_table.html
```

This returns information about the naming of flerovium and livermorium elements.

### get_issue_toc

Fetches the table of contents for a specific issue of Chemistry International.

**Parameters:**
- `url` (optional): The full URL of the issue index page
- `volume` (optional): The volume number (e.g., "34")
- `number` (optional): The issue number (e.g., "4")

Note: Either `url` or both `volume` and `number` must be provided.

**Returns:**
- Issue metadata (volume, number, date)
- List of articles with titles, URLs, and sections
- Article count

**Example:**
```
Volume: 34, Number: 4
```

This returns the table of contents for the July-August 2012 issue.

### search_articles

Searches for articles by title keyword within a specific issue.

**Parameters:**
- `query` (required): Search keyword to match against article titles
- `volume` (required): The volume number
- `number` (required): The issue number

**Returns:**
- Matching articles with titles and URLs
- Search metadata

**Example:**
```
Query: "periodic", Volume: 34, Number: 4
```

This returns articles about the periodic table from the specified issue.

## URL Patterns

IUPAC Chemistry International follows these URL patterns:

- Issue index: `https://publications.iupac.org/ci/{volume}/{volume}{number}/index.html`
- Articles: `https://publications.iupac.org/ci/{volume}/{volume}{number}/{filename}.html`

Article filenames follow conventions:
- `iw*.html` - IUPAC Wire articles
- `pp*.html` - Project Place articles
- `pac*.html` - Making an imPACt articles
- `cc*.html` - Conference Call articles
- `si.html` - Stamps International
- `nn.html` - Nomenclature Notes
- `ud.html` - Up for Discussion

## Content Sections

Chemistry International includes these regular sections:
- From the Editor
- Features
- IUPAC Wire
- Project Place
- Making an imPACt
- Nomenclature Notes
- Stamps International
- Conference Call
- Where 2B & Y

## Notes

- The site uses ISO-8859-1 encoding, which is handled automatically
- Article content is extracted from paragraph elements
- Navigation and metadata are filtered out automatically
- The skill handles special characters in chemistry-related content
