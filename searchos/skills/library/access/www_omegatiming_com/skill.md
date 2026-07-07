# Omega Timing Live Results Extractor

Extract official timing and results data from Omega Timing (www.omegatiming.com), the official timekeeper for the Olympic Games and major international sporting events.

## Overview

Omega Timing provides comprehensive live timing and results for:
- **Olympic Games** (Summer and Winter)
- **World Aquatics Championships** (Swimming, Diving, Water Polo, Artistic Swimming)
- **World Athletics Championships**
- **Diamond League** Athletics
- **Other major international competitions** (Bobsleigh, Skeleton, etc.)

## Features

### 1. List Events (`list_events`)
Retrieve all available events or filter by year.

**Example:**
```python
# List all events
result = await execute({"function": "list_events"})

# List events for a specific year
result = await execute({
    "function": "list_events",
    "year": 2026
})
```

**Returns:**
```json
{
  "success": true,
  "count": 17,
  "events": [
    {
      "year": 2026,
      "slug": "world-aquatics-diving-world-cup-1",
      "name": "World Aquatics Diving World Cup 2026",
      "url": "https://www.omegatiming.com/2026/world-aquatics-diving-world-cup-1-live-results"
    },
    ...
  ]
}
```

### 2. Get Event Files (`get_event_files`)
Get all available files (PDFs, XML results) for a specific event.

**Example:**
```python
result = await execute({
    "function": "get_event_files",
    "event_url": "https://www.omegatiming.com/2026/world-aquatics-diving-world-cup-1-live-results"
})
```

**Returns:**
```json
{
  "success": true,
  "event_title": "All World Aquatics Diving World Cup 2026 Results By OMEGA",
  "url": "https://www.omegatiming.com/2026/world-aquatics-diving-world-cup-1-live-results",
  "files": {
    "pdf": [
      {
        "url": "https://www.omegatiming.com/File/00011A0100FFFFFFFFFFFFFFFFFFFF01.pdf",
        "filename": "00011A0100FFFFFFFFFFFFFFFFFFFF01.pdf",
        "description": "Competition Schedule"
      },
      ...
    ],
    "xml": [
      {
        "url": "https://www.omegatiming.com/File/00011A0100FFFFFFFFFFFFFFFFFFFFC0.xml",
        "filename": "00011A0100FFFFFFFFFFFFFFFFFFFFC0.xml",
        "description": "RESULTS IN XML FORMAT"
      }
    ]
  },
  "schedule": ["Thursday, 26 February 2026", "Friday, 27 February 2026", ...],
  "disciplines": [
    {"value": "10m Platform", "name": "10m Platform"},
    {"value": "3m Springboard", "name": "3m Springboard"},
    ...
  ]
}
```

### 3. Get XML Results (`get_xml_results`)
Fetch and parse detailed results from XML files. Currently supports diving events with full structured data extraction.

**Example:**
```python
result = await execute({
    "function": "get_xml_results",
    "xml_url": "https://www.omegatiming.com/File/00011A0100FFFFFFFFFFFFFFFFFFFFC0.xml"
})
```

**Returns (for diving events):**
```json
{
  "success": true,
  "sport": "diving",
  "metadata": {
    "title": "World Aquatics Diving World Cup 2026",
    "startdate": "2026-02-26",
    "enddate": "2026-03-01",
    "website": "www.omegatiming.com",
    "creator": "SwissTiming Ltd."
  },
  "timetable": [
    {
      "code": "M10OP",
      "phase": "Preliminaries",
      "height": "Platform",
      "gender": "M",
      "timestamp": "26-02-26 14:30"
    },
    ...
  ],
  "events": [
    {
      "code": "M10OP",
      "fullname": "Men's 10m Platform Preliminary",
      "phase": "Preliminaries",
      "height": "Platform",
      "gender": "M",
      "diver_count": "28",
      "divers": [
        {
          "id": "202432",
          "name": "YUMING",
          "surname": "BAI",
          "nation": "CHN",
          "score": "498.55",
          "rank": "2",
          "dives": [
            {
              "id": "5253B",
              "difficulty": "3.2",
              "points": "81.60",
              "scores": [
                {"judge": "1", "score": "8.0"},
                {"judge": "2", "score": "8.5"},
                ...
              ]
            },
            ...
          ]
        },
        ...
      ],
      "judges": [...]
    },
    ...
  ]
}
```

### 4. Search Events (`search_events`)
Search for events by keyword.

**Example:**
```python
# Search for swimming events
result = await execute({
    "function": "search_events",
    "query": "swimming"
})

# Search for Olympic events
result = await execute({
    "function": "search_events",
    "query": "olympiad"
})
```

## Supported Sports

### Full Parsing Support (XML)
- **Diving** - Complete results including:
  - Diver information (name, nation, birth year)
  - Dive details (code, difficulty, scores per judge)
  - Rankings and total scores
  - Judge assignments

### Partial Support (PDF Files Only)
- Swimming
- Athletics
- Bobsleigh & Skeleton
- Other sports

## Data Availability

- **Historical Results**: Olympic Games dating back to 2004
- **Current Events**: Major competitions from current and recent years
- **File Formats**: 
  - XML (structured results with detailed scores)
  - PDF (start lists, results books, detailed reports)

## Notes

1. **XML Availability**: Not all events provide XML results. Historical events (pre-2010s) typically only have PDF files.

2. **Sport-Specific Parsing**: Full XML parsing is currently implemented for diving events. Other sports return raw XML or metadata only.

3. **Rate Limiting**: The skill implements reasonable request timeouts and follows standard HTTP practices.

4. **Data Freshness**: Results are sourced from the official Omega Timing website, which is updated during live competitions.

## Example Workflows

### Get all results for a diving event:
```python
# 1. Search for the event
events = await execute({"function": "search_events", "query": "diving world cup 2026"})

# 2. Get files for the first result
event_files = await execute({
    "function": "get_event_files",
    "event_url": events["results"][0]["url"]
})

# 3. Parse the XML results
if event_files["files"]["xml"]:
    results = await execute({
        "function": "get_xml_results",
        "xml_url": event_files["files"]["xml"][0]["url"]
    })
    # Process structured results...
```

### Find all Olympics swimming results:
```python
# 1. Search for Olympics events
events = await execute({"function": "search_events", "query": "olympiad"})

# 2. Filter for swimming
swimming_events = [e for e in events["results"] if "swim" in e["name"].lower()]

# 3. Get files for each event
for event in swimming_events:
    files = await execute({"function": "get_event_files", "event_url": event["url"]})
    # Access PDF start lists and results...
```

## Technical Details

- **Base URL**: https://www.omegatiming.com
- **Data Source**: SwissTiming Ltd. (official Omega Timing partner)
- **Response Format**: Structured JSON
- **Error Handling**: All errors are returned as structured error messages with descriptive text