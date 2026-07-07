# EPFL Website Access Skill

Access structured information from the EPFL (École Polytechnique Fédérale de Lausanne) official website at www.epfl.ch.

## Overview

This skill provides programmatic access to EPFL's public website content, including:
- **Contact Information**: Phone numbers, emails, addresses, and department contacts
- **Campus Locations**: Addresses and public transport directions for all EPFL campuses
- **Page Content**: Structured extraction of any EPFL page
- **Search**: Basic search functionality across EPFL pages

## Available Functions

### 1. get_contact_info

Retrieves EPFL's central contact information including:
- General information phone line
- Welcome Desk location and hours
- Student Desk information
- Media Services contacts
- Emergency contacts (24/7)
- IT Support Desk information
- Online directory links

**Parameters:**
- `lang` (optional, default: "en"): Language code
  - "en" - English
  - "fr" - French
  - "de" - German

**Example:**
```python
result = await execute({
    "function": "get_contact_info",
    "lang": "en"
})
```

**Returns:**
```json
{
    "success": true,
    "url": "https://www.epfl.ch/about/contact-en/",
    "title": "Contact ‒ About ‐ EPFL",
    "h1": "Contact",
    "language": "en",
    "contact": {
        "phones": ["+41 (0)21 693 11 11", "+41 21 693 30 00"],
        "emails": ["info.sample@epfl.ch"],
        "addresses": ["CH-1015 Lausanne"],
        "departments": [
            {
                "name": "General Information",
                "description": "For information or any questions about EPFL...",
                "phones": ["+41 (0)21 693 11 11"]
            }
        ]
    },
    "sections": [...]
}
```

### 2. get_campus_location

Retrieves location and transport information for EPFL campuses:
- **Lausanne (Main Campus)**: Ecublens location with metro, bus, train, and walking access
- **EPFL Geneva**: Campus Biotech location
- **EPFL Fribourg**: Smart Living Lab in bluefactory
- **EPFL Neuchâtel**: Microcity innovation cluster
- **EPFL Valais Wallis**: Sion campus

**Parameters:**
- `campus` (optional, default: "all"): Campus to retrieve info for
  - "lausanne" - Main campus
  - "geneva" - Geneva campus
  - "fribourg" - Fribourg campus
  - "neuchatel" - Neuchâtel campus
  - "valais" - Valais campus
  - "all" - All campuses

**Example:**
```python
result = await execute({
    "function": "get_campus_location",
    "campus": "lausanne"
})
```

**Returns:**
```json
{
    "success": true,
    "url": "https://www.epfl.ch/campus/visitors/coming-to-epfl/",
    "campuses": {
        "lausanne": {
            "name": "EPFL Lausanne (Main Campus)",
            "location": "Ecublens, Lausanne",
            "address": "CH-1015 Lausanne, Switzerland",
            "description": "EPFL's main campus is located in the commune of Ecublens...",
            "transport": {
                "metro": ["m1 metro towards Renens gare: EPFL stop", ...],
                "bus": ["tl1 direct route towards EPFL/Colladon", ...],
                "train": ["From Renens train station (2.7 km)..."],
                "walking": [...]
            }
        }
    }
}
```

### 3. get_page_content

Retrieves structured content from any EPFL page.

**Parameters:**
- `path` (required): URL path to the page
  - Example: "/about/en/about/", "/education/", "/research/"

**Example:**
```python
result = await execute({
    "function": "get_page_content",
    "path": "/about/en/about/"
})
```

**Returns:**
```json
{
    "success": true,
    "url": "https://www.epfl.ch/about/en/about/",
    "title": "About EPFL",
    "h1": "About",
    "description": "EPFL is Europe's most cosmopolitan technical university...",
    "content": {
        "headings": [...],
        "paragraphs": [...],
        "lists": [...],
        "links": [...]
    },
    "contact": {...}
}
```

### 4. search_pages

Searches EPFL website pages.

**Parameters:**
- `query` (required): Search query
- `limit` (optional, default: 10): Maximum number of results

**Example:**
```python
result = await execute({
    "function": "search_pages",
    "query": "computer science",
    "limit": 5
})
```

**Returns:**
```json
{
    "success": true,
    "query": "computer science",
    "total": 5,
    "results": [
        {
            "title": "Computer Science Section",
            "url": "https://www.epfl.ch/schools/ic/",
            "snippet": "The School of Computer and Communication Sciences..."
        }
    ]
}
```

## Error Handling

All functions return structured error responses:

```json
{
    "success": false,
    "error": "Missing required parameter: path",
    "error_type": "validation"
}
```

Error types:
- `validation`: Invalid or missing parameters
- `execution`: Runtime errors during request or parsing

## Important Contacts

- **General Information**: +41 (0)21 693 11 11 (8am-5pm, Mon-Fri)
- **Emergency**: 115 (from EPFL landline) / +41 21 693 30 00 (mobile)
- **Main Address**: EPFL, CH-1015 Lausanne, Switzerland

## Campus Addresses

| Campus | Address |
|--------|---------|
| Lausanne | CH-1015 Lausanne |
| Geneva | Chemin des Mines 9, 1202 Geneva |
| Fribourg | Passage du Cardinal 13b, 1700 Fribourg |
| Neuchâtel | Rue de la Maladière 71, 2000 Neuchâtel |
| Valais | Rue de l'Industrie 17, 1950 Sion |

## Data Source

All information is extracted from the official EPFL website at https://www.epfl.ch/
using HTTP requests and HTML parsing. The skill respects the website's content
and structure while providing programmatic access to public information.