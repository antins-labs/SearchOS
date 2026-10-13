# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Tony Awards Access Skill

This skill extracts structured data from the official Tony Awards website (www.tonyawards.com), providing access to winners, nominees, press releases, and committee information.

## Features

### Winners
Retrieve Tony Award winners with detailed information:
- Year and category
- Show/production name
- Recipient attributes (Author, Book, Music & Lyrics, For, etc.)
- Show detail page URL
- Image URL

Example: Get all winners from 2026:
```json
{
  "function": "winners",
  "year": "2026"
}
```

### Nominees
Retrieve nominees with winner status marked:
- Full list of nominees per category
- Winner indication (★ WINNER)
- Show details and attributes
- Summary statistics (total nominees, total winners)

Example: Get nominees for Best Play:
```json
{
  "function": "nominees",
  "category": "Best Play"
}
```

### Press Releases
List recent press releases from the Tony Awards:
- Title and date
- Full URL to the release

Example:
```json
{
  "function": "press_releases"
}
```

### Press Release Content
Get detailed content from a specific press release:
- Title and date
- Full text content
- Structured lists (e.g., committee members with "new member" markers)

Example:
```json
{
  "function": "press_release",
  "url": "/press/the-tony-awards-announce-the-2025-2026-nominating-committee/"
}
```

## Data Structure

### Winner Object
```json
{
  "year": "2026",
  "category": "Best Play",
  "show": "Liberation",
  "attributes": {
    "Author": "Bess Wohl"
  },
  "show_url": "https://www.tonyawards.com/shows/liberation/",
  "image_url": "https://www.tonyawards.com/media/images/..."
}
```

### Nominee Object
```json
{
  "show": "Liberation",
  "is_winner": true,
  "attributes": {
    "Author": "Bess Wohl"
  },
  "show_url": "https://www.tonyawards.com/shows/liberation/"
}
```

### Press Release Object
```json
{
  "title": "THE TONY AWARDS ANNOUNCE THE 2025-2026 NOMINATING COMMITTEE",
  "date": "July 10, 2025",
  "content": "New York, NY (July 10, 2025) – The Tony Awards Administration Committee...",
  "list_items": [
    {
      "name": "Bob Balaban–Actor / Producer / Director / Writer",
      "is_new_member": false
    },
    {
      "name": "Mark Bennett–Composer / Sound Designer / Educator",
      "is_new_member": true
    }
  ]
}
```

## Notes

- The website shows the most recent awards season by default
- Category filtering uses partial matching (case-insensitive)
- Press release URLs can be relative or absolute paths
- Committee member lists are extracted from press releases when available
- New committee members are marked with `is_new_member: true` based on the ** marker in the source
