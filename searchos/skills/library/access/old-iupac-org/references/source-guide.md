# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IUPAC News Archive Access Skill

This skill retrieves news articles and press releases from the IUPAC (International Union of Pure and Applied Chemistry) archive at old.iupac.org.

## Why This Skill is Needed

The IUPAC archive uses legacy HTML with table-based layouts that can cause generic content readers to fail. The site structure includes:

- **Table-based layout**: Content is organized in `<td valign="top">` elements rather than modern semantic HTML
- **Nested font tags**: Dates and titles use deprecated `<font>` elements with size attributes
- **Mixed inline styles**: No CSS classes for reliable content targeting
- **Meta refresh redirects**: Year archive pages redirect to the main news index

This skill specifically handles these legacy patterns to reliably extract article content.

## Functions

### get_article

Fetches and parses a single news article from the IUPAC archive.

**Parameters:**
- `url` (required): The full URL of the article page

**Returns:**
- `title`: Article headline
- `date`: Publication date (and revision date if present)
- `content`: Full article text with normalized whitespace
- `paragraphs`: List of individual paragraphs
- `links`: Links found in the article with URLs, link text, and external link indicator
- `last_modified`: Page last modified date if available
- `metadata`: Source information

**Example:**
```json
{
  "function": "get_article",
  "url": "https://old.iupac.org/news/archives/2003/naming110.html"
}
```

**Sample output:**
```json
{
  "success": true,
  "title": "Element 110 is named darmstadtium",
  "date": "16 August 2003; revised 25 August 2003",
  "content": "Press Release, 16 August 2003...",
  "paragraphs": ["Press Release...", "Element 110 is named darmstadtium..."],
  "links": [{"url": "...", "text": "...", "is_external": false}],
  "last_modified": "7 October 2003"
}
```

### get_archive_listing

Fetches an archive index page and extracts links to individual articles.

**Parameters:**
- `url` (required): The full URL of an archive index page

**Returns:**
- `articles`: List of article links with URLs and titles
- `count`: Number of articles found
- `note`: (Optional) Information about redirects or special handling

**Example:**
```json
{
  "function": "get_archive_listing",
  "url": "https://old.iupac.org/news/archives-notes.html"
}
```

**Sample output:**
```json
{
  "success": true,
  "articles": [
    {"url": "...", "title": "Element 111 is named roentgenium"},
    {"url": "...", "title": "Element 110 is named darmstadtium"}
  ],
  "count": 102
}
```

## Content Structure

The skill extracts content from the second `<td valign="top">` element, which contains:

1. **Date information**: From the first `<font size="-1">` element
2. **Title**: From the first `<b>` (bold) tag
3. **Body content**: All `<p>` paragraphs
4. **Links**: All hyperlinks (excluding navigation and email protection links)
5. **Metadata**: Last modified date from footer text

## Recommended URLs

### For Article Listings:
- `https://old.iupac.org/news/archives.html` - Main archives index (yearly archives)
- `https://old.iupac.org/news/archives-notes.html` - News and press releases index

### For Individual Articles:
- `https://old.iupac.org/news/archives/2003/naming110.html` - Element 110 named darmstadtium
- `https://old.iupac.org/news/archives/2004/naming111.html` - Element 111 named roentgenium
- Various other articles under `/news/archives/{year}/`

## Notes

- Year archive pages (e.g., `/news/archives/2003/`) use meta refresh redirects; the skill detects this and returns a helpful note
- The skill uses BeautifulSoup with the `html.parser` for robust HTML parsing
- Whitespace is normalized throughout the output
- External links are identified in the `links` array
- Error responses include descriptive error messages for debugging
- Navigation links and email protection links are filtered out from listings
