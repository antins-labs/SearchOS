# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Berlinale (Berlin International Film Festival) Access Skill

This skill retrieves structured data from the Berlin International Film Festival (Berlinale) website at www.berlinale.de.

## Available Functions

### 1. awards_by_year

Fetches all awards for a specific year of the Berlin International Film Festival.

**Parameters:**
- `year` (required): The festival year (e.g., 2024, 2000, 1980)
- `page` (optional): Page number (default: 1)
- `results_per_page` (optional): Number of results per page (default: 100)

**Returns:**
- Award name (e.g., "Golden Bear for Best Film")
- Film title
- Film URL (link to film details)
- Director
- Recipients (for acting awards, etc.)
- Image URL
- Ex aequo status (if award was shared)

**Example:**
```json
{
  "function": "awards_by_year",
  "year": 2024
}
```

### 2. juries

Fetches information about festival juries across different years.

**Parameters:** None

**Returns:**
- Jury names and years
- Jury member information (when available)
- Jury descriptions

**Example:**
```json
{
  "function": "juries"
}
```

### 3. biographies

Fetches a list of festival staff and jury member biographies.

**Parameters:** None

**Returns:**
- Name
- Role/position
- Biography URL

**Example:**
```json
{
  "function": "biographies"
}
```

### 4. biography_detail

Fetches detailed information about a specific person.

**Parameters:**
- `biography_url` (required): The biography page URL (can be relative or absolute)

**Returns:**
- Full name
- Role/title
- Complete biography text
- Photo URL

**Example:**
```json
{
  "function": "biography_detail",
  "biography_url": "/en/festival/biographies/tricia-tuttle.html"
}
```

## Data Sources

The skill extracts data from:
- Awards Archive: `/en/archive/awards-juries/awards.html`
- Juries Page: `/en/archive/awards-juries/juries.html`
- Biographies: `/en/festival/biographies/all-biographies.html`

## Notes

- The Berlinale awards database covers festivals from 1951 to present
- Award categories have evolved over the years; the skill captures all available awards for each year
- Some jury pages may have limited member information depending on the year
- Biography pages are primarily for current festival staff and recent jury members

## Error Handling

All functions return a `success` field indicating whether the operation completed successfully. On failure, an `error` field contains the error message.
