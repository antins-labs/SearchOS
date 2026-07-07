# CG Oncology Investor Relations Access Skill

## Overview

This skill retrieves press releases from CG Oncology's investor relations website (`ir.cgoncology.com`). Due to site access restrictions that block automated fetchers with HTTP/2 protocol errors, this skill uses the Internet Archive's Wayback Machine as its primary data source.

## Site Information

- **Host**: `ir.cgoncology.com`
- **Platform**: Drupal-based Nasdaq Investor Relations (NIR)
- **Content Type**: Press releases, investor news
- **Access Method**: Wayback Machine (archived pages)

## Why Wayback Machine?

The main site (`ir.cgoncology.com`) consistently blocks automated access:
- HTTP/2 protocol errors (`ERR_HTTP2_PROTOCOL_ERROR`)
- Connection timeouts
- Stream reset errors for programmatic requests

The Wayback Machine provides reliable access to archived versions of the site's content.

## Functions

### `list_press_releases`

Retrieve a list of recent press releases.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 20 | Maximum number of results |

**Example:**
```python
result = await execute({
    "function": "list_press_releases",
    "limit": 10
})
```

**Returns:**
```json
{
  "success": true,
  "press_releases": [
    {
      "title": "CG Oncology Announces Pricing of Upsized Initial Public Offering",
      "date": "Jan 24, 2024",
      "url": "https://ir.cgoncology.com/news-releases/news-release-details/cg-oncology-announces-pricing-upsized-initial-public-offering",
      "slug": "cg-oncology-announces-pricing-upsized-initial-public-offering",
      "wayback_url": "http://web.archive.org/web/20240301204725/https://..."
    }
  ],
  "total_found": 5,
  "wayback_timestamp": "20240301220038",
  "source": "wayback"
}
```

### `get_press_release`

Retrieve the full content of a specific press release.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | No* | Full URL or slug of the press release |
| `slug` | string | No* | Alternative parameter for URL slug |

*One of `url` or `slug` is required.

**Examples:**
```python
# Using full URL
result = await execute({
    "function": "get_press_release",
    "url": "https://ir.cgoncology.com/news-releases/news-release-details/cg-oncology-announces-pricing-upsized-initial-public-offering"
})

# Using slug only
result = await execute({
    "function": "get_press_release",
    "slug": "cg-oncology-announces-pricing-upsized-initial-public-offering"
})
```

**Returns:**
```json
{
  "success": true,
  "title": "CG Oncology Announces Pricing of Upsized Initial Public Offering",
  "date": "Jan 24, 2024",
  "body": "IRVINE, Calif.--(BUSINESS WIRE)--Jan. 24, 2024--CG Oncology, Inc. (Nasdaq: CGON)...",
  "body_html": "<div class=\"field--name-body\">...</div>",
  "original_url": "https://ir.cgoncology.com/news-releases/news-release-details/...",
  "wayback_url": "http://web.archive.org/web/20240301204725/https://...",
  "wayback_timestamp": "20240301204725",
  "pdf_url": null,
  "source": "wayback"
}
```

## Error Handling

The skill returns structured error responses rather than raising exceptions:

| Error Code | Description |
|------------|-------------|
| `missing_function` | The required `function` parameter was not provided |
| `unknown_function` | The specified function is not supported |
| `missing_url` | Neither `url` nor `slug` was provided for `get_press_release` |
| `no_archived_version` | No Wayback Machine snapshot exists for the requested URL |
| `all_snapshots_failed` | All archived snapshots failed to load |

**Error Response Example:**
```json
{
  "success": false,
  "error": "no_archived_version",
  "error_message": "No archived version found for: https://ir.cgoncology.com/news-releases/news-release-details/nonexistent-article",
  "original_url": "https://ir.cgoncology.com/news-releases/news-release-details/nonexistent-article"
}
```

## URL Patterns

The site uses the following URL structure:
- Press releases: `/news-releases/news-release-details/{slug}`
- Press releases list: `/news-events/press-releases`

Where `{slug}` is a URL-friendly version of the title, e.g.:
- `cg-oncology-announces-pricing-upsized-initial-public-offering`
- `cg-oncology-announces-first-patient-dosed-pivot-006-phase-3-0`

## Limitations

1. **Archived Content Only**: The skill can only retrieve press releases that have been archived by the Wayback Machine. Recent articles may not be available immediately.

2. **Lag Time**: There may be a delay between when content is published and when it appears in the Wayback Machine.

3. **Incomplete Archives**: Not all press releases may be archived. The skill returns an error if no archived version exists.

4. **View Version Timestamps**: Content is retrieved from historical snapshots, so there may be slight variations from the current live version.

## Dependencies

- `httpx` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `lxml` - XML/HTML parser (used by BeautifulSoup)

## Technical Notes

- The site uses Drupal's field-based content structure
- Press release titles are typically in `<h2>` elements within `<article>` tags
- Body content is in elements with class `field--name-body`
- Dates are in `<time>` elements or fields with `date` in the class name