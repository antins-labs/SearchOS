# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# China Airlines Baggage Policy Access Skill

This skill retrieves baggage policy information from the China Airlines website (www.china-airlines.com).

## Features

### Carry-On Baggage (`get_carry_on_baggage`)
Retrieves information about:
- Size and weight restrictions for carry-on items
- Storage rules (overhead compartments, under-seat storage)
- Special item regulations
- Placement requirements for safe stowage

### Checked Baggage (`get_checked_baggage`)
Retrieves detailed baggage allowance tables including:

**Economy Class:**
- Short Haul (Within Asia): 1-2 pieces, 23 kg (50 lbs) per piece
- Trans-Tasman Routes (Australia-New Zealand): 0-1 pieces, 23 kg per piece
- Long Haul (US/Canada/Europe/Australia/New Zealand): 1-2 pieces, 23 kg per piece
- Allowances vary by booking class (Discount/Basic/Standard/Flex/Reward)

**Premium Economy Class:**
- All Routes: 2 pieces, 28 kg (61 lbs) per piece

**Business Class:**
- All Routes: 2 pieces, 32 kg (70 lbs) per piece

**Member Benefits:**
- Gold: +1 piece
- Emerald: +1 piece
- Paragon: +2 pieces

**Children & Infants:**
- Infants not occupying a seat: 1 piece (same size/weight as adult)
- Children/infants occupying a seat: Same allowance as adult
- One stroller or car seat can be checked free of charge

**Size Restrictions:**
- Total dimensions (length + width + height) must not exceed 158 cm

**Important Notes:**
- Maximum weight per item: 32 kg (70 lbs) for China Airlines/Mandarin Airlines operated flights
- Special items exceeding 32 kg require 48-hour advance approval

## Usage Notes

The China Airlines website uses Akamai bot protection. This skill:
1. Initializes a browser session with anti-detection measures
2. Visits the homepage first to establish cookies
3. Accepts cookie consent if prompted
4. Navigates to the requested baggage policy page

If the website blocks access, the skill will return an error message. Retrying the request may succeed as the blocking is inconsistent.

## Data Source

All information is fetched from:
- Carry-on: https://www.china-airlines.com/us/en/prepare-for-the-fly/information/baggage/carry-on-baggage
- Checked: https://www.china-airlines.com/us/en/prepare-for-the-fly/information/baggage/checked-baggage

## Example Response

```json
{
  "source": "China Airlines",
  "source_url": "https://www.china-airlines.com",
  "data": {
    "page": "checked_baggage",
    "economy_class": {
      "headers": ["Discount", "Basic", "Standard", "Flex", "Reward Ticket"],
      "data": [
        ["Short Haul Within Asia", "1 piece 23 kg", "1 piece 23 kg", "2 pieces 23 kg", ...],
        ...
      ]
    },
    ...
  }
}
```
