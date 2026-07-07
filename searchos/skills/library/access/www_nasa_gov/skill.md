# NASA Mission Details & History Article Extractor

This skill fetches and parses pages from NASA's official website (www.nasa.gov), extracting structured data from mission details pages and history articles.

## Supported Page Types

### Mission Details Pages
URLs like `https://www.nasa.gov/missions/apollo/apollo-8-mission-details/`

Extracts:
- **Title & Description**: Mission name and summary
- **Mission Objective**: Detailed objectives text
- **Mission Highlights**: Narrative of mission events
- **Crew**: Commander, pilots with roles
- **Backup Crew**: Backup astronauts with roles
- **Payload**: Spacecraft designation
- **Prelaunch Milestones**: Key dates before launch
- **Launch**: Date, time, pad, vehicle details
- **Orbit**: Altitude, inclination, duration, distance
- **Landing**: Date, time, location, recovery ship
- **Images**: Featured images with captions
- **Dates**: Publication and modification dates

### History Articles
URLs like `https://www.nasa.gov/history/50-years-ago-nasa-names-apollo-13-and-14-crews/`

Extracts:
- **Title**: Article headline
- **Description**: Meta description
- **Author**: Article author info
- **Content**: Full article text as paragraph array
- **Related Terms**: Tags/topics
- **Images**: Featured images with captions
- **Dates**: Publication and modification dates

## Functions

### fetch_mission_details
Parses NASA mission details pages and returns structured mission data.

**Parameters:**
- `url` (required): Full URL to a NASA mission details page

**Example:**
```json
{
  "function": "fetch_mission_details",
  "url": "https://www.nasa.gov/missions/apollo/apollo-8-mission-details/"
}
```

### fetch_history_article
Parses NASA history/news article pages.

**Parameters:**
- `url` (required): Full URL to a NASA history article

**Example:**
```json
{
  "function": "fetch_history_article",
  "url": "https://www.nasa.gov/history/50-years-ago-nasa-names-apollo-13-and-14-crews/"
}
```

### fetch_page_auto
Automatically detects page type and parses accordingly.

**Parameters:**
- `url` (required): Full URL to any NASA page

**Example:**
```json
{
  "function": "fetch_page_auto",
  "url": "https://www.nasa.gov/missions/apollo/apollo-11-mission-details/"
}
```

## Output Structure

### Mission Details Response
```json
{
  "title": "Apollo 8: Mission Details - NASA",
  "description": "'Round the moon and back...'",
  "url": "https://www.nasa.gov/missions/apollo/apollo-8-mission-details/",
  "date_published": "2009-07-08T16:26:00-04:00",
  "date_modified": "2023-12-14T17:58:36-05:00",
  "mission_objective": "The mission objectives for Apollo 8 included...",
  "mission_highlights": "Apollo 8 launched from Cape Kennedy on Dec. 21, 1968...",
  "crew": [
    {"name": "Frank Borman", "role": "Commander"},
    {"name": "William A. Anders", "role": "Lunar Module Pilot"},
    {"name": "James A. Lovell Jr.", "role": "Command Module Pilot"}
  ],
  "backup_crew": [
    {"name": "Neil Armstrong", "role": "Commander"},
    {"name": "Fred W. Haise Jr.", "role": "Lunar Module Pilot"},
    {"name": "Edwin E. Aldrin Jr.", "role": "Command Module Pilot"}
  ],
  "payload": "CSM-103",
  "prelaunch_milestones": ["12/24/67 – S-II stage ondock at Kennedy", ...],
  "launch": {
    "values": ["Dec. 21, 1968; 7:51 a.m. EST", "Launch Pad 39A", "Saturn-V AS-503", ...]
  },
  "orbit": {
    "Altitude": "118.82 miles",
    "Inclination": "32.509 degrees",
    "Orbits": "10 revolutions",
    "Duration": "six days, three hours, 42 seconds",
    "Distance": "579,606.9 miles"
  },
  "landing": {
    "values": ["Dec. 27, 1968; 10:52 a.m. EST", "Pacific Ocean"],
    "Recovery Ship": "USS Yorktown"
  },
  "images": [{"url": "...", "caption": "Apollo 8 Part 1"}],
  "page_type": "mission_details",
  "fetch_status": "success"
}
```

### History Article Response
```json
{
  "title": "50 Years Ago: NASA Names Apollo 13 and 14 Crews",
  "description": "On August 6, 1969, NASA formally announced...",
  "url": "https://www.nasa.gov/history/...",
  "date_published": "2019-08-06T...",
  "date_modified": "2023-...",
  "author": "John Uri, Johnson Space Center",
  "content": ["Paragraph 1...", "Paragraph 2...", ...],
  "related_terms": ["Apollo 13", "Apollo 14", ...],
  "images": [{"url": "...", "caption": "..."}],
  "page_type": "history_article",
  "fetch_status": "success"
}
```

## Error Handling

The skill returns structured error responses:

```json
{
  "error": "HTTP error: 404",
  "error_code": "HTTP_ERROR",
  "status_code": 404
}
```

Error codes:
- `MISSING_URL`: URL parameter not provided
- `MISSING_FUNCTION`: Function parameter not provided
- `UNKNOWN_FUNCTION`: Invalid function name
- `INVALID_DOMAIN`: URL is not from www.nasa.gov
- `HTTP_ERROR`: HTTP request failed
- `TIMEOUT`: Request timed out
- `NETWORK_ERROR`: Network connectivity issue
- `PARSE_ERROR`: Failed to parse page content

## Data Sources

This skill extracts data from:
- JSON-LD structured data embedded in pages
- HTML semantic markup (headings, paragraphs)
- Meta tags for descriptions
- Image schema data for images

## Limitations

- Only supports pages from www.nasa.gov domain
- Mission details extraction requires standard page structure
- Some dynamic content may not be captured
- Rate limiting may apply; use responsibly

## Tested URLs

- `https://www.nasa.gov/missions/apollo/apollo-8-mission-details/`
- `https://www.nasa.gov/missions/apollo/apollo-10-mission-details/`
- `https://www.nasa.gov/history/50-years-ago-nasa-names-apollo-13-and-14-crews/`