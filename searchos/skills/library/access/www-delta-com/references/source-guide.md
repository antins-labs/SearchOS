# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Delta Air Lines Baggage Information Skill

This skill retrieves comprehensive baggage policy information from Delta Air Lines'
official website (www.delta.com), including carry-on baggage rules, checked baggage
policies, fees, and frequently asked questions.

## Features

### 1. Carry-On Baggage Information (`get_carry_on_info`)
Retrieves detailed carry-on baggage policies including:
- **Allowance**: Number of carry-on bags and personal items permitted
- **Size Restrictions**: Maximum dimensions (22" x 14" x 9", 45 linear inches)
- **Approved Personal Items**: Purses, laptop bags, briefcases, etc.
- **Free Items**: Jackets, umbrellas, duty-free merchandise, assistive devices
- **Liquid Restrictions**: TSA 3-1-1 rule details
- **Prohibited Items**: Items not allowed in carry-on

### 2. Baggage FAQs (`get_baggage_faqs`)
Extracts frequently asked questions about:
- Carry-on allowances
- Checked baggage fees
- Military baggage policies
- Lost and delayed baggage
- Baggage liability
- Special items

### 3. Baggage Overview (`get_baggage_overview`)
General baggage information including:
- Overview of baggage policies
- Fee structures
- Special allowances (Medallion status, credit cards)
- International travel rules

### 4. Search Baggage Information (`search_baggage_info`)
Searches across all baggage pages for specific information:
- Query-based search
- Returns relevant sections, FAQs, and policies
- Prioritizes results by relevance

## Usage Examples

### Get Carry-On Information
```python
result = await execute({
    'function': 'get_carry_on_info'
}, ctx)
```

Returns structured data with allowance, size restrictions, approved items, and policy details.

### Search for Specific Information
```python
result = await execute({
    'function': 'search_baggage_info',
    'query': 'liquid restrictions'
}, ctx)
```

Searches all pages for information about liquid restrictions and returns matching sections and FAQs.

### Get FAQs
```python
result = await execute({
    'function': 'get_baggage_faqs'
}, ctx)
```

Returns list of frequently asked questions with answers.

## Data Sources

All information is retrieved directly from Delta's official baggage pages:
- https://www.delta.com/us/en/baggage/carry-on-baggage
- https://www.delta.com/us/en/baggage/additional-baggage-information/baggage-faqs
- https://www.delta.com/us/en/baggage/overview

## Technical Notes

- Uses direct HTTP requests to fetch HTML content
- Parses structured data using BeautifulSoup
- No JavaScript rendering required (server-side rendered content)
- Handles rate limiting and network errors gracefully

## Response Format

All functions return a consistent response structure:
```python
{
    'success': True/False,
    'data': {...},  # Function-specific data
    'error': '...'  # Only present if success is False
}
```

## Limitations

- Information retrieved is current as of the time of query
- Always verify critical information with Delta's website for most recent updates
- Some dynamic content (real-time fee calculators) may not be captured
