# Coca-Cola Coliseum Event Scraper

## Overview

This skill extracts event information from the Coca-Cola Coliseum venue website at [www.coca-colacoliseum.com](https://www.coca-colacoliseum.com). The venue hosts concerts, sporting events, and other entertainment in Toronto, Ontario.

## Capabilities

- **Event Listings**: Retrieve all upcoming events with dates, ticket availability, and Ticketmaster links
- **Event Details**: Get detailed information for specific events
- **Event Search**: Search events by title or keyword

## Data Extracted

### Event Information
- **Title**: Event name (may include status like "CANCELLED:")
- **Date**: Day, month, and year parsed into structured format
- **Time**: Event start time (when available)
- **Status**: active, cancelled, or postponed
- **Ticket URL**: Direct Ticketmaster purchase link
- **Ticket Status**: e.g., "Buy Tickets", "On Sale Soon"
- **Event Type**: concert or team event
- **Image**: Event promotional image URL
- **Slug**: URL-friendly event identifier

### Venue Information
- Venue name and URL
- Logo
- Social media links

## Functions

### get_events

Retrieves the complete list of upcoming events.

**Parameters:**
- `url` (optional): Defaults to the events listing page

**Example:**
```python
result = await execute({'function': 'get_events'})
# Returns: {events: [...], total_events: 25, venue: {...}}
```

### get_event_detail

Fetches detailed information for a specific event.

**Parameters:**
- `url` (required): Full URL to the event detail page

**Example:**
```python
result = await execute({
    'function': 'get_event_detail',
    'url': 'https://www.coca-colacoliseum.com/events/detail/gem-1'
})
# Returns: {title: 'G.E.M.', date_string: 'Apr 7, 2025', ...}
```

### search_events

Searches events by title or keyword.

**Parameters:**
- `query` (required): Search term

**Example:**
```python
result = await execute({
    'function': 'search_events',
    'query': 'tempo'
})
# Returns all Toronto Tempo basketball games
```

## Technical Details

### Implementation

The skill uses direct HTTP requests (aiohttp) and HTML parsing (BeautifulSoup) because:

1. **No Public API**: The site does not expose a JSON API for event data
2. **Server-Side Rendering**: All event data is embedded in the HTML
3. **Static Content**: Events are rendered server-side, not loaded via JavaScript

### HTML Structure

Events are structured with specific CSS classes:

```html
<div class="eventItem">
  <div class="date">
    <span class="m-date__month">Apr</span>
    <span class="m-date__day">7</span>
    <span class="m-date__year">, 2025</span>
  </div>
  <h3 class="title">
    <a href="/events/detail/gem-1">G.E.M.</a>
  </h3>
  <a class="tickets" href="https://ticketmaster.ca/...">
    Buy Tickets
  </a>
</div>
```

### Error Handling

The skill returns structured error responses rather than raising exceptions:
- Missing parameters return `{'error': 'message'}`
- HTTP failures return `{'error': 'description', 'url': url}`
- Parsing failures are logged but don't crash

## Rate Limiting

Default limits:
- 2 requests per second
- 30 requests per minute

## Caching Recommendations

- Event listings: 5 minutes (events change infrequently)
- Event details: 1 hour (rarely change once published)

## Sample Output

### Event Listing
```json
{
  "events": [
    {
      "title": "G.E.M.",
      "slug": "gem-1",
      "url": "https://www.coca-colacoliseum.com/events/detail/gem-1",
      "month": "Apr",
      "day": "7",
      "year": "2025",
      "date_string": "Apr 7, 2025",
      "ticket_url": "https://www.ticketmaster.ca/event/1000623CCE862DAD...",
      "ticket_status": "Buy Tickets",
      "status": "active",
      "event_type": "concert",
      "image_url": "https://www.coca-colacoliseum.com/assets/img/GEM_2025_event_880x500.jpg"
    }
  ],
  "total_events": 25,
  "venue": {
    "name": "Coca-Cola Coliseum",
    "url": "https://www.coca-colacoliseum.com/"
  }
}
```

## Limitations

1. **No Real-Time Availability**: Ticket availability shown is from page load, not live inventory
2. **Partial Details**: Some events may not have all fields populated
3. **Website Structure Changes**: If the site redesigns, selectors may need updating

## Use Cases

- Event discovery and aggregation
- Venue schedule monitoring
- Ticket link extraction for affiliate/bot purposes
- Event cancellation tracking
- Sports schedule tracking (Toronto Tempo WNBA games)