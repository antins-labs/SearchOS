# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# report.az Access Skill

This skill retrieves articles from **report.az**, an Azerbaijani news and information portal.

## ⚠️ Important Notes

### Cloudflare Protection

report.az uses aggressive Cloudflare bot protection that actively blocks automated access. This skill implements:

- **Stealth browser automation** with anti-detection measures
- **Extended wait times** for Cloudflare challenge resolution (up to 120 seconds by default)
- **Multiple content extraction strategies** for various page layouts

### Limitations

- **Success rates vary**: Cloudflare's protection may block access even with stealth measures
- **Slow performance**: May require waiting up to 2 minutes for challenge resolution
- **Search functionality**: Limited due to the same protection measures

## Functions

### get_article

Retrieves a specific article by URL.

**Parameters:**
- `url` (required): The full article URL from report.az
- `max_wait` (optional): Maximum seconds to wait for Cloudflare bypass (default: 120)

**Example:**
```json
{
  "function": "get_article",
  "url": "https://report.az/en/foreign-politics/article-slug-here"
}
```

**Returns:**
- `title`: Article headline
- `content`: Full article text
- `author`: Article author (if available)
- `date`: Publication date (if available)
- `url`: Canonical URL

### search_articles

Searches for articles on report.az.

**Parameters:**
- `query` (required): Search terms
- `max_wait` (optional): Maximum wait time (default: 90)

**Example:**
```json
{
  "function": "search_articles",
  "query": "Azerbaijan economy"
}
```

**Returns:**
- `results`: Array of search results with title, URL, and snippet
- `count`: Number of results found

## URL Patterns

report.az uses the following URL patterns:

- English articles: `https://report.az/en/{category}/{article-slug}`
- Azerbaijani articles: `https://report.az/az/{category}/{article-slug}`
- AMP versions: `https://report.az/en/amp/{category}/{article-slug}`

Common categories include:
- `foreign-politics` - International relations
- `politics` - Domestic politics
- `economy` - Economic news
- `society` - Social issues
- `sports` - Sports news
- `culture` - Cultural events

## Error Handling

The skill returns structured error responses:

```json
{
  "error": "Failed to bypass Cloudflare protection",
  "message": "The site's bot protection is particularly aggressive...",
  "url": "https://report.az/..."
}
```

## Technical Details

The skill uses Playwright with:
- Chromium browser in headless mode
- Anti-fingerprinting scripts (webdriver detection bypass, plugin spoofing)
- Realistic browser headers and viewport settings
- Multiple content extraction selectors for robustness

## Troubleshooting

If you encounter persistent Cloudflare blocks:

1. **Increase wait time**: Set `max_wait` to 180 or higher
2. **Try different URLs**: Some pages may have weaker protection
3. **Retry later**: Cloudflare settings may change over time
4. **Use AMP versions**: AMP pages sometimes have less aggressive protection

## Source

- Website: https://report.az
- Language: English (en), Azerbaijani (az), Russian (ru)
- Content Type: News, politics, economy, culture
