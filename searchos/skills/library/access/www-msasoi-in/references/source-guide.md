# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# msasoi.in - Central Government Holidays Access Skill

This skill extracts structured holiday data from the Ministry of Statistics and Programme Implementation website (msasoi.in), specifically from Department of Personnel and Training (DoPT) Office Memorandums regarding Central Government holidays.

## Data Source

- **Website**: www.msasoi.in
- **Content**: DoPT O.M. documents listing holidays for Central Government Offices
- **Example**: [Holidays to be observed in Central Government Offices during year 2025](https://www.msasoi.in/2024/07/Holidays%20to%20be%20observed%20in%20Central%20Government%20Offices%20during%20year%202025%20.html)

## Available Functions

### get_holidays_2025

Fetches the complete list of Central Government holidays for 2025.

**Returns**:
- Page metadata (title, document reference, date)
- Three holiday tables:
  1. **Gazetted Holidays** (17 holidays) - Mandatory closed holidays
  2. **Restricted Holidays** (Part 1) - 9 optional holidays from 1946 Saka Era
  3. **Restricted Holidays** (Part 2) - 25 optional holidays from 1947 Saka Era
- Each holiday includes:
  - Serial number
  - Holiday name
  - Gregorian date
  - Saka Era date
  - Day of week
  - Saka Era classification (1946/1947)

**Example**:
```python
result = await execute({"function": "get_holidays_2025"}, ctx)
```

### search_holidays

Search and filter holidays by various criteria.

**Parameters**:
- `query`: Search string to match in holiday names (case-insensitive)
- `saka_era`: Filter by Saka Era ("1946 SAKA ERA" or "1947 SAKA ERA")
- `holiday_type`: Filter by type ("Gazetted" or "Restricted")

**Examples**:
```python
# Search for holidays containing "Diwali"
result = await execute({
    "function": "search_holidays",
    "query": "diwali"
}, ctx)

# Get all Restricted holidays
result = await execute({
    "function": "search_holidays",
    "holiday_type": "Restricted"
}, ctx)

# Get holidays from 1947 Saka Era
result = await execute({
    "function": "search_holidays",
    "saka_era": "1947 SAKA ERA"
}, ctx)
```

## Output Structure

```json
{
  "success": true,
  "page_info": {
    "title": "Holidays to be observed in Central Government Offices during year 2025 - DoPT O.M. dated 09.07.2024",
    "h1": "...",
    "h2": "...",
    "document_intro": [...]
  },
  "tables": [
    {
      "table_type": "Gazetted Holidays",
      "total_holidays": 17,
      "holidays": [
        {
          "sno": "1",
          "name": "Republic Day",
          "date": "January 26",
          "saka_date": "Magha 06",
          "day": "Sunday",
          "saka_era": "1946 SAKA ERA"
        },
        ...
      ]
    },
    ...
  ],
  "total_holidays": 51,
  "all_holidays": [...]
}
```

## Notes

- The skill uses direct HTTP fetching (no browser automation required)
- Tables are identified by the `border` attribute in HTML
- Saka Era dates are preserved in their original format
- The data structure handles the split of Restricted Holidays across two Saka Eras (1946 and 1947)
