# Sina Finance VIP Stock Bulletin Access Skill

This skill fetches detailed company bulletin reports and announcements from Sina Finance's VIP stock portal (vip.stock.finance.sina.com.cn).

## Features

- **Get Bulletin Detail**: Fetch the full text content of a single company announcement/bulletin
- **List Bulletins**: List all bulletins for a stock with pagination support
- **List Annual Reports**: Filter to show only annual reports
- **List Quarterly Reports**: Filter by quarterly report type (Q1, semi-annual, Q3)
- **Search Bulletins**: Search bulletins by keyword in title

## Functions

### get_bulletin_detail

Fetch detailed content of a specific bulletin.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| stockid | Yes | Stock code (e.g., '688710', '301580') |
| bulletin_id | Yes | Bulletin ID (e.g., '11079368') |
| include_html | No | Include raw HTML content (default: false) |

**Returns:**
| Field | Description |
|-------|-------------|
| title | Bulletin title |
| date | Announcement date (YYYY-MM-DD) |
| pdf_url | PDF download link if available |
| content | Full text content of the bulletin |
| content_html | Raw HTML (only if include_html=true) |
| stockid | Stock code |
| bulletin_id | Bulletin ID |
| url | Source URL |

**Example:**
```json
{
  "function": "get_bulletin_detail",
  "stockid": "688710",
  "bulletin_id": "11079368"
}
```

### list_bulletins

List all bulletins for a stock.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| stockid | Yes | Stock code |
| page | No | Page number (default: 1) |

**Returns:**
| Field | Description |
|-------|-------------|
| bulletins | Array of bulletin entries with id, title, date, url |
| has_next | Whether there are more pages |
| count | Number of bulletins returned |
| page | Current page number |

**Example:**
```json
{
  "function": "list_bulletins",
  "stockid": "688710",
  "page": 1
}
```

### list_annual_reports

List annual reports for a stock.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| stockid | Yes | Stock code |

**Example:**
```json
{
  "function": "list_annual_reports",
  "stockid": "688710"
}
```

### list_quarterly_reports

List quarterly reports for a stock.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| stockid | Yes | Stock code |
| report_type | No | Report type: 'yjdbg' (Q1), 'zqbg' (semi-annual), 'sjdbg' (Q3) |

**Example:**
```json
{
  "function": "list_quarterly_reports",
  "stockid": "688710",
  "report_type": "yjdbg"
}
```

### search_bulletins

Search bulletins by keyword.

**Parameters:**
| Name | Required | Description |
|------|----------|-------------|
| stockid | Yes | Stock code |
| keyword | No | Keyword to filter by title |
| limit | No | Maximum results to return (default: 10) |

**Example:**
```json
{
  "function": "search_bulletins",
  "stockid": "688710",
  "keyword": "年报",
  "limit": 5
}
```

## Data Source

- **Base URL**: https://vip.stock.finance.sina.com.cn
- The skill scrapes HTML pages from Sina Finance's VIP stock portal
- All data is encoded in GB2312/GBK and properly decoded to UTF-8

## Content Quality

The bulletin detail pages contain full text content including:
- Complete annual/quarterly reports
- Financial statements and tables
- Risk factors and management discussion
- Corporate governance information
- Shareholder information
- All other disclosure content

Each bulletin also provides a PDF download link for the official document.

## Notes

- Bulletin IDs are numeric identifiers found in the listing pages
- The content extraction preserves all text including financial tables and detailed information
- Some bulletins may be very long (200K+ characters) for comprehensive reports
- Rate limiting is not built-in; use responsibly