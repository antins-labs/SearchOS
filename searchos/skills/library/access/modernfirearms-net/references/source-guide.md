# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Modern Firearms Access Skill

This skill extracts technical specifications from firearm record pages on modernfirearms.net.

## Features

- **Firearm Specifications Extraction**: Extracts structured technical data from dedicated firearm pages including:
  - Caliber/Cartridge
  - Action type
  - Overall length
  - Barrel length
  - Weight
  - Magazine capacity
  - Rate of fire
  - And other specifications

- **Multi-format Support**: Handles both table-based and paragraph-based specification formats used on the site

- **Image Extraction**: Extracts firearm images from the page

## Available Functions

### get_firearm_specifications

Extracts specifications from a specific firearm page URL.

**Parameters:**
- `url` (required): Full URL to a firearm page on modernfirearms.net

**Example:**
```
https://modernfirearms.net/en/assault-rifles/russia-assault-rifles/ak-47-akm-eng/
https://modernfirearms.net/en/assault-rifles/russia-assault-rifles/ak-102104105-eng/
```

**Returns:**
- `title`: Firearm name/title
- `specifications`: Normalized specification dictionary
- `description`: Page description text
- `images`: List of firearm images with URLs and alt text
- `raw_specifications`: Raw extracted data from tables and bold tags

### search_firearms

**Note**: Direct search functionality is limited. The site doesn't provide a public search API. Users should browse the site to find specific firearm pages.

## Data Extraction Methods

The skill uses two primary methods to extract specifications:

1. **Table Extraction**: Parses HTML tables containing specification data (common on older pages)
2. **Bold Tag Extraction**: Extracts label-value pairs from paragraphs where specifications are marked with `<b>` tags

## Normalized Fields

Specifications are normalized to standard field names:
- `caliber`: Caliber or cartridge information
- `action`: Action type (e.g., "Gas operated, rotating bolt")
- `overall_length`: Overall length measurement
- `barrel_length`: Barrel length measurement
- `weight`: Weight specification
- `magazine_capacity`: Magazine capacity
- `rate_of_fire`: Rate of fire (rounds per minute)

## Limitations

- Some pages may have specifications in formats not yet covered
- Multi-variant specifications (e.g., different stock types) may be stored with variant-specific keys
- Search functionality requires manual browsing of the site
