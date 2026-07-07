# IMDb Awards Access Skill

Extract comprehensive awards and nominations data from IMDb for both people (actors, directors, etc.) and titles (movies, TV shows).

## Overview

This skill bypasses IMDb's AWS WAF anti-bot protection to reliably extract structured awards data that would otherwise be blocked or return 402/403 errors. It provides detailed information about:

- Award events (Academy Awards, Golden Globes, etc.)
- Individual nominations and wins
- Categories and years
- Associated works and people
- Win/nomination status

## Features

- **Anti-Bot Bypass**: Uses Playwright with stealth settings to overcome AWS WAF challenges
- **Structured Data**: Returns parsed, easy-to-use JSON instead of raw HTML
- **Dual Support**: Works for both names (nm...) and titles (tt...)
- **Rich Details**: Includes images, captions, event links, and more
- **Summary Stats**: Provides aggregate counts of wins and nominations

## Functions

### get_name_awards

Get awards for an IMDb name (person).

```python
result = await execute({
    "function": "get_name_awards",
    "name_id": "nm0000149"  # Jodie Foster
})
```

**Parameters:**
- `name_id` (required): IMDb name ID (e.g., 'nm0000149')

### get_title_awards

Get awards for an IMDb title (movie/TV show).

```python
result = await execute({
    "function": "get_title_awards",
    "title_id": "tt0944835"  # Salt (2010)
})
```

**Parameters:**
- `title_id` (required): IMDb title ID (e.g., 'tt0944835')

### get_awards

Auto-detect entity type and get awards.

```python
result = await execute({
    "function": "get_awards",
    "imdb_id": "nm0000149"  # Auto-detects name vs title
})
```

**Parameters:**
- `imdb_id` (required): IMDb ID (nm... or tt...)

## Response Structure

### Successful Response

```json
{
  "success": true,
  "entity_id": "nm0000149",
  "entity_type": "name",
  "entity_name": "Jodie Foster",
  "primary_image": "https://m.media-amazon.com/images/...",
  "summary": {
    "category_count": 88,
    "total_wins": 62,
    "total_nominations": 156
  },
  "categories": [
    {
      "event_id": "ev0000003",
      "event_name": "Academy Awards, USA",
      "event_href": "/event/ev0000003/?ref_=nmawd",
      "total_awards": 5,
      "awards": [
        {
          "id": "an0049441",
          "year": 1992,
          "status": "Winner",
          "award_name": "Oscar",
          "category": "Best Actress in a Leading Role",
          "title": "The Silence of the Lambs",
          "title_id": "tt0102926",
          "names": [],
          "image_url": "https://m.media-amazon.com/images/...",
          "image_caption": "Jodie Foster in The Silence of the Lambs (1991)"
        }
      ]
    }
  ]
}
```

### Error Response

```json
{
  "success": false,
  "error": "Timeout waiting for page to load",
  "error_code": "TIMEOUT",
  "url": "https://www.imdb.com/name/nm0000149/awards/"
}
```

## Error Codes

| Code | Description |
|------|-------------|
| `MISSING_PARAM` | Required parameter not provided |
| `INVALID_PARAM` | Parameter format is invalid |
| `INVALID_FUNCTION` | Unknown function name |
| `NO_DATA` | No __NEXT_DATA__ found on page |
| `TIMEOUT` | Page load timed out |
| `FETCH_ERROR` | General fetch/parse error |

## Examples

### Example 1: Get awards for an actor

```python
# Jodie Foster - Academy Award winner
result = await execute({
    "function": "get_name_awards",
    "name_id": "nm0000149"
})

print(f"{result['entity_name']}: {result['summary']['total_wins']} wins, {result['summary']['total_nominations']} nominations")

# Find Oscar wins
for category in result['categories']:
    if category['event_name'] == 'Academy Awards, USA':
        for award in category['awards']:
            if award['status'] == 'Winner':
                print(f"  {award['year']}: {award['category']} - {award['title']}")
```

Output:
```
Jodie Foster: 62 wins, 156 nominations
  1992: Best Actress in a Leading Role - The Silence of the Lambs
  1989: Best Actress in a Leading Role - The Accused
```

### Example 2: Get awards for a movie

```python
# The Silence of the Lambs
result = await execute({
    "function": "get_title_awards",
    "title_id": "tt0102926"
})

print(f"{result['entity_title']} ({result['release_year']}): {result['summary']['total_wins']} wins")

# Print all awards by event
for category in result['categories']:
    print(f"\n{category['event_name']}: {category['total_awards']} nominations")
    for award in category['awards'][:3]:  # First 3
        print(f"  {award['year']} {award['status']}: {award['category']}")
```

### Example 3: Filter by award status

```python
result = await execute({"function": "get_awards", "imdb_id": "nm0000149"})

# Get only wins
wins = []
for category in result['categories']:
    for award in category['awards']:
        if award['status'] == 'Winner':
            wins.append({
                'event': category['event_name'],
                'year': award['year'],
                'category': award['category'],
                'work': award.get('title', 'N/A')
            })

print(f"Total wins: {len(wins)}")
for win in sorted(wins, key=lambda x: x['year'], reverse=True)[:5]:
    print(f"  {win['year']}: {win['event']} - {win['category']}")
```

### Example 4: Count nominations by event

```python
from collections import Counter

result = await execute({"function": "get_name_awards", "name_id": "nm0000149"})

event_counts = Counter()
for category in result['categories']:
    event_counts[category['event_name']] = category['total_awards']

print("Nominations by event:")
for event, count in event_counts.most_common(5):
    print(f"  {event}: {count}")
```

## Technical Details

### Anti-Bot Bypass

IMDb uses AWS WAF (Web Application Firewall) with JavaScript challenges. Direct HTTP requests return HTTP 202 with a JavaScript challenge page. This skill uses:

- **Playwright**: Headless browser automation
- **Stealth Mode**: Disables automation detection
- **Realistic Headers**: Mimics real browser behavior
- **JavaScript Rendering**: Executes JS to solve WAF challenges

### Data Source

Data is extracted from the `__NEXT_DATA__` script tag, which contains Next.js server-side props in JSON format. This is more reliable and structured than HTML scraping.

### Rate Limiting

IMDb may rate-limit excessive requests. Recommendations:
- Add 2-3 second delays between requests
- Cache results (awards data changes infrequently)
- Limit concurrent requests
- Respect `requests_per_minute: 20` guideline

## Use Cases

1. **Award History Research**: Track an actor's or film's award history
2. **Competitive Analysis**: Compare award wins between films/actors
3. **Content Enrichment**: Add award data to movie databases
4. **Statistical Analysis**: Analyze award patterns and trends
5. **Biographical Research**: Build comprehensive actor profiles

## Limitations

- Requires JavaScript execution (uses Playwright, not simple HTTP)
- Slower than pure HTTP APIs due to browser overhead
- May encounter rate limits with excessive requests
- Award data is limited to what IMDb displays on awards pages
- Some older or obscure awards may not be fully detailed

## Testing

```python
# Test the executor
import asyncio
from executor import execute

async def test():
    # Test name awards
    result1 = await execute({"function": "get_name_awards", "name_id": "nm0000149"})
    assert result1['success']
    assert result1['entity_type'] == 'name'
    assert len(result1['categories']) > 0
    print(f"✓ Name awards: {result1['entity_name']}")
    
    # Test title awards
    result2 = await execute({"function": "get_title_awards", "title_id": "tt0944835"})
    assert result2['success']
    assert result2['entity_type'] == 'title'
    print(f"✓ Title awards: {result2['entity_title']}")
    
    # Test auto-detect
    result3 = await execute({"function": "get_awards", "imdb_id": "nm0000149"})
    assert result3['success']
    print("✓ Auto-detect works")
    
    print("\nAll tests passed!")

asyncio.run(test())
```

## Changelog

### v1.0.0 (Initial Release)
- First release with name and title award extraction
- AWS WAF bypass using Playwright
- Structured JSON output with categories and awards
- Error handling and validation