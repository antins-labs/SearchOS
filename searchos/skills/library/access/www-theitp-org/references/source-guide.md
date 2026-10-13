# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ITP Journal Access Skill

This skill fetches journal volume data from The Institute of Telecommunications Professionals (ITP) website at www.theitp.org.

## Overview

The ITP publishes "The Journal" - a quarterly telecommunications industry publication. This skill extracts structured data about each journal volume/issue including:

- Volume/issue metadata (title, subtitle, publication date)
- PDF download links for full issues
- Page preview images (when available)

## Data Source

The skill uses the Storyblok CDN API (`api.storyblok.com`) which powers the ITP website, providing reliable access to publication metadata without requiring browser automation.

## Available Functions

### get_volume

Fetch a specific journal volume by URL or slug.

**Parameters:**
- `url` (optional): Full URL to a journal volume page
  - Example: `https://www.theitp.org/publications/the-journal/volume-16-part-4`
- `slug` (optional): Storyblok slug for the volume
  - Example: `publications/the-journal/volume-16-part-4`
- `include_previews` (optional, default: true): Include PDF preview image URLs

**Returns:**
```json
{
  "name": "Volume 16 Part 4",
  "title": "The Internet of Things",
  "subtitle": "Striving to meet demand and potential",
  "issue_number": "Volume 16 Part 4",
  "publication": "The Journal",
  "publication_date": "2022-12-01 11:38",
  "pdf_url": "https://a.storyblok.com/f/90633/x/3191a19f7f/tj_16-4.pdf",
  "preview_images": ["https://firebasestorage.googleapis.com/.../1.jpg", ...],
  "page_count": 7,
  "url": "https://www.theitp.org/publications/the-journal/volume-16-part-4"
}
```

### list_volumes

List all available journal volumes, optionally filtered by volume number.

**Parameters:**
- `volume` (optional): Filter to a specific volume number (e.g., "16", "20")
- `include_previews` (optional, default: false): Include preview images for each volume

**Returns:**
```json
{
  "total": 51,
  "volumes": [
    {
      "name": "Volume 20 Part 1",
      "title": "Synthetic Voices, Real Threats...",
      "issue_number": "Volume 19 Part 2",
      "publication_date": "2026-03-30 09:00",
      "pdf_url": "https://a.storyblok.com/f/90633/x/.../tj_20-1.pdf",
      "url": "https://www.theitp.org/publications/the-journal/volume-20-part-1"
    },
    ...
  ]
}
```

## Example Usage

```json
// Get a specific volume
{
  "function": "get_volume",
  "url": "https://www.theitp.org/publications/the-journal/volume-16-part-4"
}

// List all volumes
{
  "function": "list_volumes"
}

// List all parts of Volume 16
{
  "function": "list_volumes",
  "volume": "16"
}
```

## Notes

- The ITP Journal has been published since 1908 (historical index available)
- Modern volumes (Vol 8 onwards) have digital PDFs available
- Preview images are generated page-by-page and stored in Firebase Storage
- Volume numbering: Each year has 4 parts (Part 1 = March, Part 2 = June, Part 3 = September, Part 4 = December)
- The site uses Nuxt.js with Storyblok headless CMS
