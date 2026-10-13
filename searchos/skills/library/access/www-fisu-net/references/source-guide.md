# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# FISU.net Access Skill

This skill extracts structured data from the FISU (International University Sports Federation) website at www.fisu.net.

## Features

### 1. Event Pages (`get_event`)
Extracts comprehensive information from FISU event pages including:
- **Event Details**: Title, event type (Summer/Winter Games, Championships, etc.), host country
- **Key Facts**: Number of participating nations, athletes, sports, and other statistics
- **Sports List**: Complete list of sports featured in the event
- **Description**: Brief summary/description of the event
- **Dates**: Publication and modification dates

Example event URLs:
- `https://www.fisu.net/events/11th-summer-universiade/` (Bucharest 1981)
- `https://www.fisu.net/events/chungcheong-2027-fisu-world-university-games/` (Future event)

### 2. Spotlight Articles (`get_spotlight`)
Extracts content from FISU spotlight articles (historical retrospectives):
- **Article Metadata**: Title, headline, author, publication date
- **Content**: Full article text organized by paragraphs
- **Summary**: First paragraph as a summary
- **Historical Data**: Years, nations, and athlete numbers mentioned in the text
- **Related Articles**: Links to related content

Example spotlight URLs:
- `https://www.fisu.net/2019/11/01/spotlight-take-a-look-back-to-the-torino-1959-summer-universiade/`
- `https://www.fisu.net/2020/07/20/spotlight-remembering-the-duisburg-1989-summer-universiade/`

### 3. Events Listing (`list_events`)
Retrieves a list of current and upcoming FISU events with titles and URLs.

## Usage Examples

### Get Event Information
```python
params = {
    'function': 'get_event',
    'url': 'https://www.fisu.net/events/11th-summer-universiade/'
}
```

Returns:
```json
{
  "success": true,
  "type": "event",
  "data": {
    "title": "11th Summer Universiade",
    "event_type": "Summer Games",
    "country": "Romania",
    "sports": ["Artistic Gymnastics", "Athletics", "Basketball", ...],
    "key_facts": {
      "Nations participating": "86",
      "Athletes participating": "2912",
      "Sports": "10"
    },
    "description": "The significance of the 1981 Bucharest Universiade..."
  }
}
```

### Get Spotlight Article
```python
params = {
    'function': 'get_spotlight',
    'url': 'https://www.fisu.net/2019/11/01/spotlight-take-a-look-back-to-the-torino-1959-summer-universiade/'
}
```

Returns:
```json
{
  "success": true,
  "type": "spotlight",
  "data": {
    "title": "Spotlight: Take a look back to the Torino 1959 Summer Universiade",
    "author": "mathieu",
    "date_published": "2019-10-31T22:00:00+00:00",
    "years_mentioned": ["1959", "1961", "1999"],
    "nations_mentioned": ["43"],
    "athletes_mentioned": ["985"],
    "summary": "With a decade of discord between..."
  }
}
```

### List Events
```python
params = {
    'function': 'list_events'
}
```

Returns:
```json
{
  "success": true,
  "type": "events_list",
  "data": {
    "events": [
      {
        "title": "Chungcheong 2027 FISU World University Games",
        "url": "https://www.fisu.net/events/chungcheong-2027-fisu-world-university-games/"
      },
      ...
    ]
  }
}
```

## Technical Details

- Uses direct HTTP requests with aiohttp for fast, reliable data retrieval
- Parses HTML using BeautifulSoup for structured data extraction
- Extracts data from multiple sources:
  - Article element classes (event type, country, sports)
  - `wp-block-keyNumbers` divs (Key Facts)
  - JSON-LD structured data
  - Meta tags
  - Article content

## Limitations

- The events listing page at `/events/` primarily shows upcoming events; past events may require direct URLs
- Some very old event pages may have different HTML structures
- Spotlight articles require text pattern matching for historical data, which may not capture all information
