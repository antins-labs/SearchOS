# DAERA-NI Areas of Outstanding Natural Beauty (AONB) Access Skill

This skill provides structured access to information about Northern Ireland's Areas of Outstanding Natural Beauty (AONBs) from the Department of Agriculture, Environment and Rural Affairs (DAERA) website.

## Overview

Northern Ireland has 7 designated Areas of Outstanding Natural Beauty, each with unique geological, natural, cultural, and built heritage. This skill fetches and structures the detailed articles published by DAERA about each AONB.

## Available Functions

### get_aonb_list

Returns a list of all Areas of Outstanding Natural Beauty in Northern Ireland.

**Example:**
```python
result = await execute({'function': 'get_aonb_list'})
```

**Returns:**
```json
{
  "aonbs": [
    {
      "title": "Antrim Coast and Glens AONB",
      "url": "https://www.daera-ni.gov.uk/articles/antrim-coast-and-glens-aonb",
      "slug": "antrim-coast-and-glens-aonb"
    },
    ...
  ],
  "count": 7,
  "source_url": "https://www.daera-ni.gov.uk/topics/land-and-landscapes/areas-outstanding-natural-beauty"
}
```

### get_aonb_article

Retrieves detailed content for a specific AONB, including sections on geology, natural heritage, cultural heritage, and built heritage.

**Parameters:**
- `slug` (string, optional): The URL slug for the AONB
- `url` (string, optional): Full URL to the AONB article (alternative to slug)

**Example:**
```python
# Using slug
result = await execute({
    'function': 'get_aonb_article',
    'slug': 'antrim-coast-and-glens-aonb'
})

# Using full URL
result = await execute({
    'function': 'get_aonb_article',
    'url': 'https://www.daera-ni.gov.uk/articles/causeway-coast-aonb'
})
```

**Returns:**
```json
{
  "url": "https://www.daera-ni.gov.uk/articles/antrim-coast-and-glens-aonb",
  "title": "Antrim Coast and Glens AONB",
  "description": "Antrim Coast and Glens AONB was designated in 1988...",
  "designated_year": 1988,
  "sections": [
    {
      "level": "h2",
      "title": "Geology",
      "paragraphs": [
        "In the past the land surfaces consisted of sedimentary rocks...",
        "This geological variation produces many contrasts..."
      ],
      "lists": [],
      "links": []
    },
    ...
  ],
  "downloads": [],
  "section_count": 12,
  "total_paragraphs": 23
}
```

### search_aonb_content

Searches across all AONB articles for content matching a query term.

**Parameters:**
- `query` (string, required): Search term (minimum 3 characters)

**Example:**
```python
result = await execute({
    'function': 'search_aonb_content',
    'query': 'geology'
})
```

**Returns:**
```json
{
  "query": "geology",
  "results": [
    {
      "aonb": "Antrim Coast and Glens AONB",
      "url": "...",
      "section": "Geology",
      "match_type": "section_title",
      "excerpt": "Geology"
    },
    {
      "aonb": "Causeway Coast AONB",
      "url": "...",
      "section": "Geology of the Causeway Coast AONB",
      "match_type": "content",
      "excerpt": "...the geology of the area is dominated by..."
    }
  ],
  "total_matches": 15,
  "aonbs_searched": 7
}
```

## Available AONBs

The following AONBs can be queried:

| Slug | Title | Designated |
|------|-------|------------|
| `antrim-coast-and-glens-aonb` | Antrim Coast and Glens AONB | 1988 |
| `binevenagh-aonb` | Binevenagh AONB | 2006 |
| `causeway-coast-aonb` | Causeway Coast AONB | 1989 |
| `lagan-valley-aonb` | Lagan Valley AONB | - |
| `mourne-aonb` | Mourne AONB | - |
| `ring-gullion-aonb` | Ring Of Gullion AONB | - |
| `strangford-and-lecale-aonb` | Strangford and Lecale AONB | - |

## Content Structure

Each AONB article typically contains sections covering:

- **Overview**: General description and designation history
- **Management Plan**: Administration and conservation plans
- **Geology**: Geological features and formation history
- **Natural Heritage**: Coast, moorland, woodland, wildlife
- **Cultural Heritage**: Farming, industry, traditions
- **Built Heritage**: Historical buildings, monuments, archaeological sites

## Data Source

Data is fetched directly from the Northern Ireland Department of Agriculture, Environment and Rural Affairs website:

- AONB Listing: https://www.daera-ni.gov.uk/topics/land-and-landscapes/areas-outstanding-natural-beauty
- Individual articles: https://www.daera-ni.gov.uk/articles/{slug}

## Technical Details

- Uses HTTP requests (aiohttp) for efficient data retrieval
- Parses HTML content using BeautifulSoup
- No authentication required
- Respects standard HTTP conventions
- Returns structured JSON data with error handling