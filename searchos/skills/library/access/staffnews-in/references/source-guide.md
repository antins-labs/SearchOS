# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# StaffNews.in Holiday Tables Access Skill

This skill extracts structured Central Government holiday data from staffnews.in, specifically the official gazetted and restricted holiday lists for the year 2025.

## Available Functions

### get_gazetted_holidays

Extracts the complete list of **Gazetted Holidays** (mandatory holidays) observed in Central Government offices during 2025.

**Returns:**
- `holiday_type`: "gazetted"
- `title`: Page title
- `url`: Source URL
- `total_holidays`: Count of holidays
- `holidays`: Array of holiday objects with:
  - `serial`: Serial number
  - `name`: Holiday name
  - `date`: Date string (e.g., "January 26")
  - `month`: Month name
  - `day`: Day number
  - `saka_date`: Saka calendar date
  - `weekday`: Day of week
  - `saka_era`: Saka era year (1946 or 1947)

**Example holidays extracted:**
- Republic Day (January 26, Sunday)
- Maha Shivaratri (February 26, Wednesday)
- Holi (March 14, Friday)
- Id-ul-Fitr (March 31, Monday)
- Independence Day (August 15, Friday)
- Christmas Day (December 25, Thursday)

### get_restricted_holidays

Extracts the complete list of **Restricted Holidays** (optional holidays) that employees can choose from.

**Returns:**
- Same structure as gazetted holidays
- `holiday_type`: "restricted"

**Example holidays extracted:**
- New Year's Day (January 01, Wednesday)
- Makar Sankranti (January 14, Tuesday)
- Basant Panchami (February 14, Sunday)
- Raksha Bandhan (August 09, Saturday)
- Ganesh Chaturthi (August 27, Wednesday)
- Christmas Eve (December 24, Wednesday)

### get_all_holidays

Fetches both gazetted and restricted holidays in a single call.

**Returns:**
- `gazetted`: Object with gazetted holidays data
- `restricted`: Object with restricted holidays data

## Data Notes

- The source tables span two Saka eras: 1946 (ending March 21) and 1947 (starting March 22)
- Holidays are listed with both Gregorian and Saka calendar dates
- Some holiday names contain non-breaking spaces and special characters (handled automatically)
- The tables include approximately 17 gazetted holidays and 34 restricted holidays

## Source

- Gazetted Holidays: https://staffnews.in/2024/07/gazetted-holidays-year-2025.html
- Restricted Holidays: https://staffnews.in/2024/07/restricted-holidays-year-2025.html
