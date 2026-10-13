# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Cato Institute People Profile Scraper

This skill extracts biographical and professional information from Cato Institute expert profile pages at `www.cato.org/people/`.

## Features

### Get Person Profile (`get_person_profile`)

Extracts comprehensive profile data for a specific Cato Institute expert, including:

- **Basic Information**: Name, first name, last name, position/title
- **Contact Information**: Email, phone (when available)
- **Biography**: Full bio text from the profile page
- **Image**: Profile photo URL
- **Social Links**: Twitter, LinkedIn, and other social media profiles
- **Publications**: Recent publications and articles by the expert
- **Expertise Areas**: Topics and policy areas the expert focuses on

#### Usage Examples

**Using full URL:**
```json
{
  "function": "get_person_profile",
  "url": "https://www.cato.org/people/chelsea-follett"
}
```

**Using slug:**
```json
{
  "function": "get_person_profile",
  "slug": "chelsea-follett"
}
```

**Sample Response:**
```json
{
  "success": true,
  "url": "https://www.cato.org/people/chelsea-follett",
  "name": "Chelsea Follett",
  "first_name": "Chelsea",
  "last_name": "Follett",
  "position": "Research Fellow",
  "email": "cfollett@cato.org",
  "description": "Research Fellow, HumanProgress.org, Cato Institute",
  "image_url": "https://www.cato.org/sites/cato.org/files/styles/optimized/public/2021-01/Chelsea%20Follett.jpg",
  "social_links": ["https://x.com/chellivia"],
  "bio": "Chelsea Follett is a research fellow at the Cato Institute's Center for Global Liberty & Prosperity...",
  "recent_publications": [
    {
      "title": "Centers of Progress: 40 Cities That Changed the World",
      "url": "https://www.cato.org/publications/..."
    }
  ]
}
```

### Search People (`search_people`)

Search for experts on the Cato Institute website.

#### Usage Example

```json
{
  "function": "search_people",
  "query": "trade policy"
}
```

**Sample Response:**
```json
{
  "query": "trade policy",
  "search_url": "https://www.cato.org/search?keys=trade%20policy",
  "total": 15,
  "results": [
    {
      "title": "Daniel J. Ikenson",
      "url": "https://www.cato.org/people/daniel-j-ikenson",
      "description": "Former Director, Herbert A. Stiefel Center for Trade Policy Studies",
      "type": "person"
    }
  ]
}
```

## Data Sources

This skill extracts data from:

1. **JSON-LD Structured Data**: The primary source for name, title, email, image, and social links
2. **Meta Tags**: Backup source for name and profile image
3. **Visible Page Content**: Biography text, publications list, and expertise areas

## Notes

- The Cato Institute website uses Incapsula security protection. The skill implements browser automation with realistic headers to access the content.
- Some profile pages may have limited information if the expert is no longer active at Cato.
- The skill extracts up to 10 recent publications when available.
- Social links include Twitter/X, LinkedIn, Facebook, and other profiles listed in the structured data.
