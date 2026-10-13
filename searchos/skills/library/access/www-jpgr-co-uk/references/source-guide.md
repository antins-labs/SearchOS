# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# JPGR Beatles UK Discography Access Skill

This skill retrieves structured discography information from www.jpgr.co.uk, a comprehensive database of Beatles UK releases and solo member discographies.

## Available Functions

### 1. get_release

Retrieve detailed information about a specific release by its catalogue number.

**Parameters:**
- `catalogue_number` (string, required): The catalogue number of the release

**Supported catalogue number formats:**
- Parlophone singles: `R 5389`, `R5389`, `r5389`
- Lyntone releases: `LYN 492`, `lyn492`
- Polydor releases: `NH 66833`, `nh66833`
- Double-sided releases: `DP 562`, `dp562`

**Example:**
```python
result = await execute({
    'function': 'get_release',
    'catalogue_number': 'R 5389'
}, ctx)
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.jpgr.co.uk/r5389.html",
  "data": {
    "artist": "The Beatles",
    "title": "Day Tripper",
    "label": "Parlophone",
    "catalogue_number": "R 5389",
    "release_date": "3rd December 1965",
    "recording_details": "Day Tripper : 3 Takes on 16th October 1965...",
    "uk_chart": {
      "entry_date": "9th December 1965",
      "highest_position": 1,
      "weeks_in_chart": 12
    },
    "notes": "...",
    "images": [...]
  }
}
```

### 2. get_index

Retrieve a listing of all releases in a category.

**Parameters:**
- `page_type` (string, optional): Type of listing to retrieve (default: `beatles_singles`)

**Available page types:**

**Beatles Band:**
- `beatles_singles` - Beatles UK singles (by date)
- `beatles_eps` - Beatles EPs (by date)
- `beatles_albums` - Beatles albums (by date)
- `beatles_all` - All Beatles releases (by date)

**Solo Members:**
- `john_singles`, `john_eps`, `john_albums`, `john_all` - John Lennon
- `paul_singles`, `paul_eps`, `paul_albums`, `paul_all` - Paul McCartney
- `george_singles`, `george_eps`, `george_albums`, `george_all` - George Harrison
- `ringo_singles`, `ringo_eps`, `ringo_albums`, `ringo_all` - Ringo Starr

**All Artists:**
- `all_singles`, `all_eps`, `all_albums`, `all_all`

**Other:**
- `bootlegs` - Bootleg releases
- `imports` - Import releases
- `apple_singles`, `apple_albums` - Apple label releases
- `collaborations` - Beatles collaborations

**Example:**
```python
result = await execute({
    'function': 'get_index',
    'page_type': 'beatles_singles'
}, ctx)
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.jpgr.co.uk/i_beatles7_date.html",
  "data": {
    "page_title": "The Beatles Singles (by Date)",
    "releases": [
      {
        "date": "5/10/62",
        "format": "7\"",
        "label": "Parlophone",
        "catalogue_number": "R 4949",
        "title": "Love Me Do",
        "b_side": "P.S. I Love You",
        "detail_url": "r4949.html"
      },
      ...
    ]
  }
}
```

### 3. search

Search for releases by title, catalogue number, label, or B-side.

**Parameters:**
- `query` (string, required): Search query

**Example:**
```python
result = await execute({
    'function': 'search',
    'query': 'Strawberry'
}, ctx)
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "query": "Strawberry",
    "total_matches": 2,
    "releases": [
      {
        "date": "17/02/67",
        "format": "7\"",
        "label": "Parlophone",
        "catalogue_number": "R 5570",
        "title": "Strawberry Fields Forever",
        "b_side": "Penny Lane",
        "detail_url": "r5570.html"
      },
      ...
    ]
  }
}
```

## Data Fields

### Release Details
- `title`: Release title
- `artist`: Artist name
- `label`: Record label (e.g., Parlophone, Polydor, Lyntone)
- `catalogue_number`: Official catalogue number
- `release_date`: UK release date
- `recording_details`: Recording session information
- `uk_chart`: Chart performance data (if applicable)
  - `entry_date`: Date entered UK charts
  - `highest_position`: Peak chart position
  - `weeks_in_chart`: Total weeks on chart
- `notes`: Additional release notes and historical context
- `images`: Associated images (sleeve, label scans)

### Index Listings
- `date`: Release date
- `format`: Format (e.g., 7", LP, EP)
- `label`: Record label
- `catalogue_number`: Catalogue number
- `title`: Release title
- `b_side`: B-side track (for singles)
- `detail_url`: URL to detailed release page

## Source

All data is retrieved from www.jpgr.co.uk, a dedicated Beatles UK discography reference site maintained by JPGR (John P. Gray Reading).
