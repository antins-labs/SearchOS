# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# V&A Museum Directors Access Skill

This skill retrieves the list of Victoria and Albert Museum (V&A) directors from the official V&A website.

## Function: get_directors

Fetches a structured list of all V&A Museum directors throughout its history.

### Returns

A dictionary containing:
- `directors`: List of director objects, each containing:
  - `name`: Full name with titles/honors (e.g., "Dr Tristram Hunt", "Sir Henry Cole, CB")
  - `id`: URL-friendly identifier from the page (e.g., "dr-tristram-hunt")
  - `dates`: Birth/death years or birth year (e.g., "b. 1974", "1955 – 2017", "1808 – 82")
  - `title`: Official title during tenure (e.g., "Director of the Victoria and Albert Museum")
  - `tenure`: Years served (e.g., "2017 – present", "1852 – 73")
  - `has_bio`: Boolean indicating if a biography link is available
  - `bio_url`: URL to external biography (typically Oxford Dictionary of National Biography)
- `count`: Total number of directors
- `source_url`: The source page URL

### Example Usage

```python
result = await execute({"function": "get_directors"}, ctx)
# Returns all 16 directors from current (Dr Tristram Hunt, 2017–present)
# back to founding director Sir Henry Cole (1852–73)
```

### Notes

- Directors are returned in reverse chronological order (most recent first)
- The list spans multiple museum names:
  - Victoria and Albert Museum (current)
  - Art Museum (Division of the Victoria and Albert Museum)
  - South Kensington Museum (original name)
- Some directors have external biography links to the Oxford Dictionary of National Biography
- The current director (Dr Tristram Hunt) links to an internal V&A senior management page

### Data Source

- URL: https://www.vam.ac.uk/info/va-directors
- The page uses a "Sir Trevor" content block structure where each director's information
  is spread across multiple div blocks (name, dates, title/tenure, and optional bio link)
