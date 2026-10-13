# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# BuzzJack Forums Chart Data Access Skill

This skill extracts music chart data from BuzzJack forums (www.buzzjack.com), a community site that posts structured text tables of Billboard chart data.

## Features

### get_chart_data
Extracts chart data from a BuzzJack topic URL. Returns structured data including:
- Chart title (e.g., "BILLBOARD HOT 100")
- Chart date (e.g., "August 2, 2025")
- Tracking period (e.g., "7/18–7/24")
- All chart entries with:
  - Position (This Week)
  - Last Week position
  - Peak position
  - Weeks on chart
  - Artist name
  - Song title

**Example:**
```python
params = {
    'function': 'get_chart_data',
    'url': 'https://www.buzzjack.com/forums/topic/281197-us-hot-100-08022025/'
}
```

### get_topic_posts
Retrieves all posts from a topic URL, including:
- Post IDs and timestamps
- Full text content of each post
- Pagination info if multiple pages exist

**Example:**
```python
params = {
    'function': 'get_topic_posts',
    'url': 'https://www.buzzjack.com/forums/topic/281197-us-hot-100-08022025/',
    'page': 1  # optional
}
```

### list_forum_topics
Lists topics from a BuzzJack forum section, including:
- Topic IDs, titles, and URLs
- Last post timestamps
- Pinned status

**Example:**
```python
params = {
    'function': 'list_forum_topics',
    'url': 'https://www.buzzjack.com/forums/forum/8-hot-100/',
    'page': 1  # optional
}
```

## Chart Data Format

BuzzJack forum posts contain chart data in a structured text format:

```
TW LW PP WC Artist – Song
01 01 01 23 Alex Warren ‒ Ordinary
02 04 02 04 HUNTR/X: EJAE, Audrey Nuna & REI AMI ‒ Golden
...
```

Where:
- TW = This Week position
- LW = Last Week position
- PP = Peak Position
- WC = Weeks on Chart

This skill parses these tables into structured JSON data.

## Common Forum URLs

- Hot 100: `https://www.buzzjack.com/forums/forum/8-hot-100/`
- UK Charts: `https://www.buzzjack.com/forums/forum/5-uk-charts/`
- Music Genres: `https://www.buzzjack.com/forums/forum/4-music-genres/`

## Notes

- The site uses Invision Power Board (IPS4) forum software
- Chart data is posted in plain text within forum posts
- Posts may contain multiple charts or additional commentary
- The skill extracts the first chart found in the topic's posts
