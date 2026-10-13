# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# kpopping.com Company Database Access Skill

This skill retrieves K-pop entertainment company information from kpopping.com's comprehensive company database.

## Available Functions

### get_company_profile

Fetches detailed information about a specific K-pop entertainment company.

**Parameters:**
- `slug` (required): Company URL slug (e.g., 'sm-entertainment', 'jyp-entertainment', 'bighit-music')

**Returns:**
- `company`: Basic company information
  - `name`: Company name
  - `founder`: Founder name(s)
  - `ceo`: CEO name(s)
  - `country`: Country code (e.g., 'KR' for South Korea)
  - `website`: Official website URL
  - `description`: Company description
  - `logo`: Logo image URL
  - `banner`: Banner image URL
  - `socials`: Object with social media links (instagram, twitter, youtube, tiktok, facebook, spotify, weverse, etc.)
  - `bioSections`: Array of company history/biography sections
- `groups`: Array of idol groups under the company, each with:
  - `id`: Group ID
  - `name`: Group name
  - `slug`: Group slug for URL
  - `image`: Profile image URL
  - `isActive`: Whether the group is currently active
  - `startDate`/`endDate`: Activity period
- `idols`: Array of solo artists/idols under the company, each with:
  - `id`: Idol ID
  - `stageName`: Stage name
  - `slug`: Idol slug for URL
  - `image`: Profile image URL

**Example:**
```json
{
  "function": "get_company_profile",
  "slug": "sm-entertainment"
}
```

### list_companies

Lists K-pop companies in the database, optionally filtered by first letter.

**Parameters:**
- `letter` (optional): Filter companies by first letter (A-Z)

**Returns:**
- `companies`: Dictionary keyed by letter, each containing array of company entries
  - Each entry includes: `id` (slug), `name`, `image`, `popularity`, `ceo`, `foundedYear`
- `total_count`: Total number of companies returned
- `note`: Information about data availability

**Note:** The site only loads companies starting with A-D initially. Specify a letter to get companies starting with that letter.

**Example:**
```json
{
  "function": "list_companies",
  "letter": "S"
}
```

### search_companies

Searches for companies by name (case-insensitive partial match).

**Parameters:**
- `query` (required): Search query (partial or full company name)

**Returns:**
- `matches`: Array of matching company entries
- `count`: Number of matches found
- `note`: Information about search scope

**Note:** Search only covers initially loaded companies (A-D by default). Use `list_companies` with a specific letter for complete results.

**Example:**
```json
{
  "function": "search_companies",
  "query": "Cube"
}
```

## Data Source

All data is retrieved from kpopping.com's company database pages. The site uses Next.js with embedded JSON data that this skill extracts and parses.

## Common Company Slugs

Here are some commonly requested company slugs:
- `sm-entertainment` - SM Entertainment
- `jyp-entertainment` - JYP Entertainment  
- `yg-entertainment` - YG Entertainment
- `bighit-music` - BIGHIT MUSIC
- `cube-entertainment` - Cube Entertainment
- `starship-entertainment` - Starship Entertainment
- `woollim-entertainment` - Woollim Entertainment
- `source-music` - SOURCE MUSIC
- `pledis-entertainment` - PLEDIS Entertainment

Use `list_companies` or `search_companies` to discover more company slugs.

## Error Handling

The skill returns error objects in the following cases:
- Missing required parameters
- Non-existent company slug (404 error)
- Network/HTTP errors

Example error response:
```json
{
  "error": "Failed to fetch page: 404, message='Not Found'",
  "slug": "non-existent-company"
}
```
