# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# StaffNews.in Holiday Tables Extractor

This skill extracts structured holiday data from staffnews.in, a website that publishes Central Government of India holiday lists including Gazetted and Restricted holidays.

## Features

- **Gazetted Holidays**: Fetches the official list of compulsory holidays for Central Government offices
- **Restricted Holidays**: Fetches the optional/restricted holidays list
- **Generic Holiday Page**: Can fetch any staffnews.in holiday page URL and extract its tables

## Data Structure

Each holiday record contains:
- `serial_number`: The S. No. from the table
- `holiday_name`: Name of the holiday
- `date`: Gregorian date (e.g., "January 26", "March 14")
- `saka_date`: Date in the Saka calendar (e.g., "Magha 06", "Phalguna 23")
- `day`: Day of the week (e.g., "Sunday", "Monday")
- `saka_era`: Saka era year (e.g., "1946", "1947")
- `holiday_type`: "gazetted", "restricted", or "unknown"

## Usage Examples

### Get Gazetted Holidays
```json
{
  "function": "get_gazetted_holidays"
}
```

Returns 17 gazetted holidays for 2025 including Republic Day, Independence Day, Diwali, Christmas, etc.

### Get Restricted Holidays
```json
{
  "function": "get_restricted_holidays"
}
```

Returns 34 restricted holidays for 2025 including New Year's Day, Guru Gobind Singh's Birthday, Basant Panchami, etc.

### Get Custom Holiday Page
```json
{
  "function": "get_holiday_page",
  "url": "https://www.staffnews.in/2026/07/list-of-holidays-2027-to-be-observed-in-central-government-offices.html"
}
```

Fetches and parses any staffnews.in holiday page URL.

## Response Format

```json
{
  "success": true,
  "title": "Gazetted Holidays to be observed in Central Government offices during the year 2025 | StaffNews",
  "url": "https://www.staffnews.in/2024/07/gazetted-holidays-year-2025.html",
  "holiday_type": "gazetted",
  "count": 17,
  "holidays": [
    {
      "serial_number": 1,
      "holiday_name": "Republic Day",
      "date": "January 26",
      "saka_date": "Magha 06",
      "day": "Sunday",
      "saka_era": "1946",
      "holiday_type": "gazetted"
    }
  ]
}
```

## Notes

- The site uses Saka Era dates alongside Gregorian dates
- Tables are split by Saka Era year (1946 Saka Era, 1947 Saka Era)
- The site may have slow loading times; the skill uses Playwright with appropriate timeouts
- Non-breaking spaces and other HTML entities are cleaned from the extracted text
