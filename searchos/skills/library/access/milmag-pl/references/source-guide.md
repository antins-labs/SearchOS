# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Milmag.pl Defense Industry News Access Skill

This skill provides access to defense industry news and analysis from **milmag.pl**, a Polish military and defense magazine covering global arms industry developments.

## Features

### Get Article Content
Fetches full article content with structured extraction:
- **Title and metadata** - Article title, publication date, description
- **Full text content** - Complete article text organized by paragraphs
- **Company mentions** - Defense companies mentioned with contextual excerpts
- **Revenue data** - Extracted financial figures (total revenue, growth rates)
- **Regional statistics** - Revenue breakdown by region (US, Europe, Asia, etc.)
- **Source links** - PDF reports and external references (e.g., SIPRI reports)

### Search Articles
Search the milmag.pl archive for articles on specific topics.

## Supported Content Types

The skill is optimized for:
- **SIPRI Top 100 Arms Producers** annual reports
- Defense industry analysis and market reports
- Company-specific news and financial updates
- Regional defense industry developments
- Military procurement and contracts news

## Companies Tracked

The skill automatically extracts mentions of major defense companies including:
- Lockheed Martin, Northrop Grumman, General Dynamics, Boeing, Raytheon/RTX
- BAE Systems, Airbus, Rheinmetall, Thales, Leonardo
- Hanwha, PGZ (Polish Armaments Group), Czechoslovak Group
- Rostec, NORINCO, SpaceX Defense, and others

## Usage Examples

### Fetch a specific article
```json
{
  "function": "get_article",
  "url": "https://milmag.pl/en/sipri-the-worlds-100-largest-arms-producers-see-revenue-growth-in-2024/"
}
```

### Search for articles
```json
{
  "function": "search_articles",
  "search_query": "SIPRI arms producers 2024"
}
```

### Polish language version
```json
{
  "function": "get_article",
  "url": "https://milmag.pl/sipri-100-najwiekszych-producentow-uzbrojenia-ze-wzrostami-przychodow-w-2024/",
  "lang": "pl"
}
```

## Output Structure

### get_article response
```json
{
  "success": true,
  "url": "https://milmag.pl/en/...",
  "title": "Article title",
  "content": "Full article text...",
  "paragraphs": ["Paragraph 1", "Paragraph 2", ...],
  "companies_mentioned": [
    {
      "name": "Lockheed Martin",
      "context": "Major arms manufacturers such as Lockheed Martin..."
    }
  ],
  "revenue_data": {
    "total_revenue": "679 billion USD",
    "growth_rate": "5.9%"
  },
  "regional_data": {
    "US": "334 billion USD",
    "Europe": "151 billion USD"
  },
  "pdf_links": [
    {
      "text": "SIPRI Top 100 Report",
      "url": "https://www.sipri.org/.../report.pdf"
    }
  ],
  "metadata": {
    "date": "2024-12-01",
    "description": "Article meta description"
  }
}
```

### search_articles response
```json
{
  "success": true,
  "query": "SIPRI",
  "total_found": 10,
  "articles": [
    {
      "title": "Article title",
      "url": "https://milmag.pl/en/...",
      "excerpt": "First few sentences...",
      "date": "2024-12-01"
    }
  ]
}
```

## Notes

- The site is available in both English (`/en/`) and Polish (default) versions
- Articles often link to original source documents (PDFs) from SIPRI and other organizations
- Content focuses on European and global defense industry developments
- Polish articles may contain more detailed coverage of regional (Polish/Eastern European) defense companies
