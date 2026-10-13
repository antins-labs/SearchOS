# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# GameIndustry.be Company Directory Access Skill

This skill provides access to the Belgian game industry company directory at [gameindustry.be](https://gameindustry.be). It fetches structured data about game development studios, publishers, service providers, and other companies in the Belgian gaming ecosystem.

## Available Functions

### list_companies
List companies with pagination and filtering options.

**Parameters:**
- `page` (integer, default: 1) - Page number for pagination
- `limit` (integer, default: 20, max: 100) - Results per page
- `region` (string) - Filter by region: `flanders`, `brussels`, or `wallonia`
- `category` (string) - Filter by category: `Developer`, `Publisher`, `Service Provider`, `Person`, etc.
- `verified` (boolean) - Filter to verified companies only
- `active_only` (boolean) - Filter to active companies only
- `defunct` (boolean) - Filter to defunct/closed companies
- `search` (string) - Search term for company name

**Returns:**
- `companies` - Array of company objects
- `pagination` - Object with page info, total count, and navigation flags
- `summary` - Statistics including counts by region

**Example:**
```json
{
  "function": "list_companies",
  "region": "flanders",
  "verified": true,
  "limit": 10
}
```

### get_company
Get detailed information for a specific company.

**Parameters:**
- `slug` (string, required) - Company slug identifier (e.g., `larian-studios`)

**Returns:**
- `company` - Detailed company object including description, contact info, founding year, logo URL, game count, etc.

**Example:**
```json
{
  "function": "get_company",
  "slug": "larian-studios"
}
```

### search_companies
Search for companies by name.

**Parameters:**
- `query` (string, required) - Search query
- `limit` (integer, default: 20) - Maximum results

**Returns:**
- Same structure as `list_companies`

**Example:**
```json
{
  "function": "search_companies",
  "query": "larian"
}
```

### get_summary
Get summary statistics about the directory.

**Parameters:** None

**Returns:**
- `summary` - Statistics including counts by region
- `pagination` - Total company count

**Example:**
```json
{
  "function": "get_summary"
}
```

### list_by_region
List companies in a specific region.

**Parameters:**
- `region` (string, required) - Region name: `flanders`, `brussels`, or `wallonia`
- `limit` (integer, default: 50) - Maximum results

**Example:**
```json
{
  "function": "list_by_region",
  "region": "brussels"
}
```

### list_verified
List verified companies.

**Parameters:**
- `limit` (integer, default: 50) - Maximum results

**Example:**
```json
{
  "function": "list_verified",
  "limit": 30
}
```

### list_defunct
List defunct/closed companies.

**Parameters:**
- `limit` (integer, default: 50) - Maximum results

**Example:**
```json
{
  "function": "list_defunct"
}
```

## Company Data Structure

Each company object includes:
- `id` - Unique identifier
- `name` - Company name
- `slug` - URL-friendly identifier
- `description` - Full description (HTML)
- `shortDescription` - Brief tagline
- `url` - Company website
- `logo` - Logo image URL
- `region` - Geographic region (Flanders, Brussels, Wallonia)
- `city` - City location
- `address` - Full address
- `category` - Company category (Developer, Publisher, etc.)
- `foundingYear` - Year founded
- `verified` - Whether the listing is verified
- `defunct` - Whether the company is closed
- `isActive` - Whether the company is active
- `gameCount` - Number of games (in detail view)
- `email`, `phone`, `jobPageUrl` - Contact information
- `website` - Official website

## Notes

- The directory contains approximately 426 companies across Belgium
- Distribution: Flanders (~234), Wallonia (~113), Brussels (~39), plus ~40 without region
- API is public and requires no authentication
- All data is returned in JSON format
