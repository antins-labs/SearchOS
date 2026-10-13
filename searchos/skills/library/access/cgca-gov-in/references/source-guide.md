# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CGCA Holiday List Access Skill

This skill retrieves the official Government of India holiday list from the Principal Controller of Communication Accounts (CGCA), Delhi website.

## Source

- **Website**: https://cgca.gov.in/ccadl/list-of-holiday
- **Organization**: Principal Controller of Communication Accounts, Delhi
- **Government**: Government of India, Department of Telecommunications

## Features

### get_holidays

Retrieves the holiday list for administrative offices of the Central Government located at Delhi/New Delhi.

**Parameters:**
- `holiday_type` (optional): Filter by type
  - `"all"` (default): Returns both Gazetted and Restricted holidays
  - `"gazetted"`: Returns only Gazetted holidays
  - `"restricted"`: Returns only Restricted holidays

**Returns:**
```json
{
  "success": true,
  "source": "cgca.gov.in",
  "source_url": "https://cgca.gov.in/ccadl/list-of-holiday",
  "page_title": "Pr. Controller Of Communication Accounts, Delhi",
  "year": "2025",
  "location": "Delhi / New Delhi",
  "total_holidays": 52,
  "gazetted_holidays": [
    {
      "holiday": "Republic Day",
      "date": "26 January 2025",
      "day": "Sunday"
    },
    ...
  ],
  "gazetted_count": 17,
  "restricted_holidays": [
    {
      "holiday": "New Year's Day",
      "date": "1 January 2025",
      "day": "Wednesday"
    },
    ...
  ],
  "restricted_count": 35
}
```

## Holiday Types

### Gazetted Holidays
These are mandatory holidays for government offices. Employees are entitled to these holidays.

### Restricted Holidays
Employees can choose a limited number of holidays from this list based on their religious/cultural preferences.

## Important Notes

1. **Server Performance**: The CGCA server is slow to respond. The skill includes retry logic and extended timeouts to handle this.

2. **Year**: The holiday list typically shows the current year's holidays. The year is extracted from the holiday dates.

3. **Location**: This holiday list is specifically for Central Government administrative offices located in Delhi/New Delhi.

4. **Official Source**: This data comes from an official Government of India website and represents the authoritative holiday schedule for government offices in Delhi.

## Error Handling

The skill returns structured error responses for:
- Invalid parameters
- Network timeouts
- Missing or malformed data on the page

## Example Usage

```python
# Get all holidays
result = await execute({"function": "get_holidays"}, ctx)

# Get only Gazetted holidays
result = await execute({"function": "get_holidays", "holiday_type": "gazetted"}, ctx)

# Get only Restricted holidays
result = await execute({"function": "get_holidays", "holiday_type": "restricted"}, ctx)
```
