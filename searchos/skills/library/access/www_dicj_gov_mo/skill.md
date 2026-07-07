# DICJ Macau Gaming Statistics Access Skill

## Overview

This skill provides structured access to gaming statistics from the Macau Gaming Inspection and Coordination Bureau (DICJ - 博彩監察協調局). DICJ is the regulatory body overseeing Macau's gaming industry, one of the world's largest gaming markets.

## Data Available

### 1. Monthly Gross Gaming Revenue

Monthly gross revenue statistics for all gaming activities in Macau, including:
- Monthly revenue for current and previous year
- Year-over-year change rates
- Cumulative totals

**Example:**
```python
result = await execute({
    "function": "get_monthly_revenue",
    "year": 2024,
    "lang": "en"
})
```

Sample output:
```json
{
  "success": true,
  "year": 2024,
  "title": "Monthly Gross Revenue from Games of Fortune in 2024 and 2023",
  "remarks": "* 1 HKD = 1.03 MOP (Unit: Million MOP)",
  "monthly_data": [
    {
      "month": "January",
      "current_year_value": "19,337",
      "previous_year_value": "11,580",
      "change_rate": "67.0%",
      "current_year_cumulative": "19,337",
      "previous_year_cumulative": "11,580",
      "cumulative_change_rate": "67.0%"
    },
    ...
  ]
}
```

### 2. Quarterly Statistics

Comprehensive quarterly data including multiple report types:

1. **Gross Revenue by Gaming Category**
   - Games of Fortune (casino games)
   - Horse racing
   - Chinese lottery
   - Instant lottery
   - Sports betting (football, basketball)

2. **Betting Volumes** for pari-mutuel and lottery games

3. **Revenue by Game Type**
   - Baccarat (VIP and mass market)
   - Slot machines
   - Blackjack
   - Roulette
   - Sic Bo
   - And many other game types

4. **Number of Gaming Tables and Machines**

5. **Visitor Statistics**

**Example:**
```python
result = await execute({
    "function": "get_quarterly_statistics",
    "year": 2024,
    "lang": "en"
})
```

### 3. Concessionaire Financial Reports

Access annual financial reports from Macau's gaming concessionaires:

- **SJM** - SJM Resorts (澳娛綜合)
- **Wynn** - Wynn Macau (永利)
- **Galaxy** - Galaxy Entertainment (銀河)
- **Venetian** - Venetian Macau (威尼斯人)
- **MGM** - MGM China (美高梅)
- **PBL** - Melco Resorts (新濠博亞)
- **WingHing** - Wing Hing Lottery (榮興彩票)
- **SLOT** - Macau Lottery Services (澳門彩票)

**List available reports:**
```python
result = await execute({
    "function": "get_concessionaire_reports",
    "concessionaire": "PBL",
    "lang": "en"
})
```

**Get specific report:**
```python
result = await execute({
    "function": "get_financial_report",
    "concessionaire": "PBL",
    "year": 2024,
    "lang": "cn"
})
```

## Functions Reference

### get_monthly_revenue
Get monthly gross gaming revenue statistics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| year | integer | Yes | Year to fetch (2005-2025) |
| lang | string | No | Language: 'cn', 'en', 'pt' (default: 'en') |

### get_quarterly_statistics
Get comprehensive quarterly statistics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| year | integer | Yes | Year to fetch (2005-2025) |
| lang | string | No | Language: 'cn', 'en', 'pt' (default: 'en') |

### get_concessionaire_reports
List available financial reports for a concessionaire.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| concessionaire | string | Yes | Code: SJM, Wynn, Galaxy, Venetian, MGM, PBL, WingHing, SLOT |
| lang | string | No | Language (default: 'cn') |

### get_financial_report
Get specific financial report content.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| concessionaire | string | Yes | Concessionaire code |
| year | integer | Yes | Report year |
| lang | string | No | Language (default: 'cn') |

### list_concessionaires
List all gaming concessionaires with codes and names.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| lang | string | No | Language for names (default: 'en') |

### check_years
Check which years have available data.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| data_type | string | No | 'monthly' or 'quarterly' (default: 'monthly') |
| lang | string | No | Language (default: 'en') |

## Data Sources

All data is sourced from official DICJ XML and HTML publications:
- Monthly revenue: `/web/{lang}/information/DadosEstat_mensal/{year}/report_{lang}.xml`
- Quarterly stats: `/web/{lang}/information/DadosEstat/{year}/report_{lang}.xml`
- Financial reports: `/web/{lang}/information/relcontas/{concessionaire}/RC{year}.html`

## Language Support

All functions support three languages:
- **cn** - Chinese (Traditional)
- **en** - English
- **pt** - Portuguese

## Usage Notes

1. **Data Availability**: Monthly data is typically updated within the first few days of each month. Quarterly data is updated quarterly.

2. **Historical Data**: Monthly revenue data is available from 2005 onwards. Quarterly detailed statistics have varying availability.

3. **Financial Reports**: Reports are published annually, typically in April for the previous fiscal year.

4. **Units**: Unless otherwise specified:
   - Revenue figures are in millions of Macanese Patacas (MOP)
   - Exchange rate: 1 HKD ≈ 1.03 MOP

5. **Rate Limits**: The DICJ website has no documented rate limits, but reasonable request intervals are recommended.

## Example Queries

### Get current year monthly revenue (English)
```python
result = await execute({
    "function": "get_monthly_revenue",
    "year": 2024,
    "lang": "en"
})
```

### Get quarterly stats in Chinese
```python
result = await execute({
    "function": "get_quarterly_statistics",
    "year": 2024,
    "lang": "cn"
})
```

### Check all concessionaires
```python
# First list all concessionaires
concessionaires = await execute({
    "function": "list_concessionaires",
    "lang": "en"
})

# Then get reports for each
for c in concessionaires["concessionaires"]:
    reports = await execute({
        "function": "get_concessionaire_reports",
        "concessionaire": c["code"],
        "lang": "en"
    })
```

### Compare revenue across years
```python
years = [2022, 2023, 2024]
for year in years:
    data = await execute({
        "function": "get_monthly_revenue",
        "year": year,
        "lang": "en"
    })
    # Process year-over-year comparison
```

## Error Handling

All functions return a consistent structure:
```json
{
  "success": true/false,
  "error": "error message if failed",
  ...data fields...
}
```

Common errors:
- HTTP 404: Data not available for requested year/concessionaire
- Invalid parameter: Check function-specific requirements
- Network timeout: Retry with reasonable interval