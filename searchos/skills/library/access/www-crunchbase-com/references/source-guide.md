# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Crunchbase Access Skill

This skill retrieves company and person profile data from Crunchbase (www.crunchbase.com).

## Features

- **Person Profiles**: Fetch detailed information about individuals including name, title, organizations, and social links
- **Organization Profiles**: Fetch company data including name, description, funding, employees, location, and industry

## Important Limitations

**Crunchbase employs aggressive Cloudflare anti-bot protection.** This skill uses Playwright with stealth techniques to attempt access, but you may encounter blocking that requires CAPTCHA solving. When blocked, the skill returns:

```json
{
  "success": false,
  "blocked": true,
  "error": "Access blocked by Cloudflare anti-bot protection..."
}
```

## Functions

### get_person

Fetches profile data for a person.

**Parameters:**
- `url` (optional): Full Crunchbase URL (e.g., `https://www.crunchbase.com/person/georges-clement`)
- `slug` (optional): Person's URL slug (e.g., `georges-clement`)

**Example:**
```json
{
  "function": "get_person",
  "slug": "georges-clement"
}
```

Or with full URL:
```json
{
  "function": "get_person",
  "url": "https://www.crunchbase.com/person/georges-clement"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "name": "Georges Clement",
    "title": "Co-Founder & CEO",
    "description": "...",
    "organizations": ["JustFix.nyc"],
    "location": "New York, NY",
    "social_links": ["https://linkedin.com/in/..."],
    "url": "https://www.crunchbase.com/person/georges-clement"
  }
}
```

### get_organization

Fetches profile data for a company or organization.

**Parameters:**
- `url` (optional): Full Crunchbase URL (e.g., `https://www.crunchbase.com/organization/justfix-nyc`)
- `slug` (optional): Organization's URL slug (e.g., `justfix-nyc`)

**Example:**
```json
{
  "function": "get_organization",
  "slug": "justfix-nyc"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "name": "JustFix.nyc",
    "description": "...",
    "metrics": {
      "funding": "$2.5M",
      "employees": "11-50",
      "founded": "2015",
      "location": "New York, NY",
      "industries": ["Civic Tech", "Real Estate"]
    },
    "website": "https://justfix.nyc",
    "social_links": [...],
    "url": "https://www.crunchbase.com/organization/justfix-nyc"
  }
}
```

## Error Handling

The skill returns structured error responses:

- **Blocked by Cloudflare**: `{ "success": false, "blocked": true, "error": "..." }`
- **Invalid parameters**: `{ "success": false, "error": "Missing required parameter: url or slug" }`
- **Extraction failure**: `{ "success": false, "error": "Failed to extract data from page" }`

## Technical Details

The skill uses Playwright with extensive stealth techniques:
- Custom user agent and headers
- WebDriver property masking
- Browser fingerprint randomization
- Session establishment via homepage visit
- Automatic wait for dynamic content

However, Cloudflare's protection is sophisticated and may still block automated requests. For production use, consider:
1. Using residential proxies
2. Implementing CAPTCHA solving services
3. Using Crunchbase's official API (requires subscription)
