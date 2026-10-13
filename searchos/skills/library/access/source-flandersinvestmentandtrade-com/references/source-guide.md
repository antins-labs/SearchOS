# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Flanders Investment and Trade - Company Directory Access Skill

This skill fetches company directory and event listing data from the Flanders Investment and Trade platform (source.flandersinvestmentandtrade.com). The platform showcases Belgian companies participating in trade events, missions, and exhibitions worldwide.

## Overview

The Flanders Investment and Trade platform is used to promote Belgian/Flemish companies at international trade events. Each event listing includes detailed company profiles with:

- Company name and description
- Product/service descriptions
- Contact information (email, phone, website)
- Location (city, address, postal code)
- Tags and categories
- Video links

## Available Functions

### `get_event`

Get details for a specific event including all participating companies.

**Parameters:**
- `event_id` (string): The event UUID, e.g., `80a9036a-e0f3-4d0e-9fd7-f09f874566d5`
- OR `event_url` (string): Full URL like `https://source.flandersinvestmentandtrade.com/80a9036a-e0f3-4d0e-9fd7-f09f874566d5/Belgian-Games--gamescom-2025`

**Returns:**
- Event details (name, dates, location, status)
- List of all participating companies with full profiles

**Example:**
```json
{
  "function": "get_event",
  "event_id": "80a9036a-e0f3-4d0e-9fd7-f09f874566d5"
}
```

### `get_current_events`

Get list of current/ongoing events.

**Parameters:** None required

**Returns:**
- List of current events with basic details and registration counts

**Example:**
```json
{
  "function": "get_current_events"
}
```

### `get_past_events`

Get paginated list of past/upcoming events.

**Parameters:**
- `page` (integer, optional, default: 1): Page number
- `pagesize` (integer, optional, default: 20): Number of events per page

**Returns:**
- List of events with basic details

**Example:**
```json
{
  "function": "get_past_events",
  "page": 1,
  "pagesize": 10
}
```

### `get_sectors`

Get list of all industry sectors used on the platform.

**Parameters:** None required

**Returns:**
- List of sector names (e.g., "ICT", "Biotechnology", "Food & beverages")

**Example:**
```json
{
  "function": "get_sectors"
}
```

### `search_companies`

Search for companies within a specific event.

**Parameters:**
- `event_id` (string): The event UUID
- `company_name` (string, optional): Search term to filter companies

**Returns:**
- Event details
- Filtered list of matching companies

**Example:**
```json
{
  "function": "search_companies",
  "event_id": "80a9036a-e0f3-4d0e-9fd7-f09f874566d5",
  "company_name": "games"
}
```

## Data Structure

### Event Object
```json
{
  "id": "80a9036a-e0f3-4d0e-9fd7-f09f874566d5",
  "name": "Belgian Games @ gamescom 2025",
  "city": "Keulen",
  "country": "Germany",
  "date_from": "2025-08-20T00:00:00",
  "date_to": "2025-08-22T00:00:00",
  "status": "InProgress",
  "is_private": false,
  "platform_url": "80a9036a-e0f3-4d0e-9fd7-f09f874566d5/Belgian-Games--gamescom-2025",
  "full_url": "https://source.flandersinvestmentandtrade.com/80a9036a-e0f3-4d0e-9fd7-f09f874566d5/Belgian-Games--gamescom-2025",
  "registration_count": 45
}
```

### Company Object
```json
{
  "id": "39b44b50-d524-f011-8c4d-7c1e52885535",
  "company_name": "Altereyes",
  "city": "Hasselt",
  "street": "Vissersstraat 1 bus K6",
  "postal_code": "3500",
  "email": "ken.steyls@altereyes.com",
  "phone": "+32 11 12 38 00",
  "website": "https://www.altereyes.com",
  "company_description": "AlterEyes is a multidisciplinary development studio...",
  "product_description": "AlterEyes is a multidisciplinary development studio...",
  "tags": [],
  "profile_url": "https://source.flandersinvestmentandtrade.com/...",
  "video_url": null,
  "registration_completed": true
}
```

## Use Cases

1. **Trade Event Research**: Find Belgian companies participating in specific trade events
2. **Market Intelligence**: Gather company data for lead generation or market analysis
3. **Event Directory**: Build directories of Belgian companies in specific sectors or regions
4. **Company Discovery**: Search for companies by name or keywords within events

## Technical Notes

- The underlying API uses Azure API Management with subscription key authentication
- All endpoints return JSON data
- SSL certificate verification is disabled due to certificate issues on the target site
- The API does not expose individual company endpoints; companies are always retrieved within event context
