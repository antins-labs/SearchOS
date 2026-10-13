# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Miracle Hunter - Marian Apparitions Database

This skill retrieves structured information about Marian apparitions from [Miracle Hunter](https://www.miraclehunter.com), a comprehensive database of documented Marian apparitions throughout history.

## Features

The skill extracts and structures the following information from apparition pages:

- **Summary**: Overview of the apparition event
- **Timeline**: Chronological list of key events with dates
- **Visionaries**: Information about the seers/visionaries
- **Messages**: Messages received during the apparition
- **Description of the Virgin**: Physical description of the Marian apparition
- **Miracles and Signs**: Associated miraculous events
- **Approval Status**: Church approval and recognition status
- **Shrines**: Information about related shrines and pilgrimage sites

## Available Functions

### 1. get_apparition

Retrieve detailed information about a specific Marian apparition.

**Parameters:**
- `url` (required): Full URL to the apparition page
- `include_messages` (optional): Set to `true` to fetch full messages from the dedicated messages page

**Example:**
```json
{
  "function": "get_apparition",
  "url": "https://www.miraclehunter.com/marian_apparitions/approved_apparitions/pontmain/index.html",
  "include_messages": true
}
```

### 2. list_apparitions

List Marian apparitions by approval category.

**Parameters:**
- `category` (optional): One of `approved`, `unapproved`, or `all` (default: `approved`)

**Example:**
```json
{
  "function": "list_apparitions",
  "category": "approved"
}
```

### 3. search_apparitions

Search for apparitions by name or location.

**Parameters:**
- `query` (required): Search term (e.g., "Fatima", "Lourdes", "France")

**Example:**
```json
{
  "function": "search_apparitions",
  "query": "Fatima"
}
```

### 4. get_messages

Retrieve messages from a dedicated messages page.

**Parameters:**
- `url` (required): URL to the messages page

**Example:**
```json
{
  "function": "get_messages",
  "url": "https://www.miraclehunter.com/marian_apparitions/messages/ruedubac_messages.html"
}
```

## Data Structure

### Apparition Record

```json
{
  "title": "Pontmain, France (1871)",
  "subtitle": "Our Lady of Hope / Madonna of the Crucifix",
  "location": "Pontmain, France",
  "year": "1871",
  "summary": "During the devastation of the Franco-Prussian War...",
  "timeline": [
    {
      "date": "Jan 17, 1871",
      "event": "Eugene Barbedette (12) encounters a beautiful lady..."
    }
  ],
  "visionaries": "Names and details of the visionaries...",
  "messages": "Messages received during the apparition...",
  "description_of_virgin": "Physical description of the apparition...",
  "miracles_and_signs": "Associated miraculous events...",
  "approval": "Church approval status and declarations...",
  "shrines": "Related shrine information...",
  "url": "https://www.miraclehunter.com/..."
}
```

## Common Apparition URLs

Here are some well-known apparitions you can query:

- **Pontmain, France (1871)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/pontmain/index.html
- **Rue du Bac, France (1830)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/ruedubac/index.html
- **Lourdes, France (1858)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/lourdes/index.html
- **Fatima, Portugal (1917)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/fatima/index.html
- **Guadalupe, Mexico (1531)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/guadalupe/index.html
- **Kibeho, Rwanda (1981)**: https://www.miraclehunter.com/marian_apparitions/approved_apparitions/kibeho_rwanda/index.html

## Notes

- The site uses a structured template for apparition records, making data extraction reliable
- Timeline entries are parsed with date recognition for various formats (e.g., "Jan 17, 1871", "1871", "October 1900")
- Some apparitions may have dedicated messages pages linked from the main apparition page
- The approval status distinguishes between Vatican-approved, bishop-approved, and other categories
- For apparitions with extensive messages, use the `include_messages` parameter to fetch the full content
