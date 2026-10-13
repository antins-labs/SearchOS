# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# TheGlobalEconomy.com Access Skill

Access economic indicators, country profiles, and global rankings from TheGlobalEconomy.com database.

## Overview

TheGlobalEconomy.com provides comprehensive economic data for over 200 countries, including:
- GDP, inflation, unemployment, trade balances
- Government finance, debt, and spending
- Business and consumer confidence indicators
- Population, education, and health metrics
- Historical data with time series coverage

## Functions

### get_country_profile

Retrieve all economic indicators for a specific country, organized by category.

**Parameters:**
- `country_code` (required): ISO 3-letter country code (e.g., "USA", "CHN", "GBR", "JPN", "DEU")
- `categories` (optional): List of categories to filter (e.g., ["Main indicators", "GDP and economic growth"])

**Returns:**
- Country name and code
- List of indicator categories, each containing:
  - Category name
  - List of indicators with:
    - Name and URL
    - Latest value and reference date
    - Measurement unit
    - Frequency (quarterly, annual, monthly)
    - Time coverage range

**Example:**
```python
# Get full economic profile for USA
result = await execute({
    "function": "get_country_profile",
    "country_code": "USA"
})

# Get only main indicators for China
result = await execute({
    "function": "get_country_profile",
    "country_code": "CHN",
    "categories": ["Main indicators"]
})
```

### get_rankings

Get global or regional rankings for a specific indicator.

**Parameters:**
- `indicator` (required): Indicator slug (e.g., "GDP_per_capita_PPP", "land_area", "inflation")
- `region` (optional): Region filter (default: "World")
  - Available: World, Europe, Asia, Africa, North-America, South-America, European-union, etc.
- `limit` (optional): Maximum number of results (default: 50)

**Returns:**
- Indicator name and URL
- List of ranked countries with values
- Available regions for this indicator
- Table headers and metadata

**Example:**
```python
# Global GDP per capita rankings
result = await execute({
    "function": "get_rankings",
    "indicator": "GDP_per_capita_PPP"
})

# Land area rankings for Europe only
result = await execute({
    "function": "get_rankings",
    "indicator": "land_area",
    "region": "Europe"
})

# Top 10 inflation rates globally
result = await execute({
    "function": "get_rankings",
    "indicator": "inflation",
    "limit": 10
})
```

### get_indicator_data

Get detailed time-series data for a specific indicator for a country.

**Parameters:**
- `country_code` (required): ISO 3-letter country code
- `indicator` (required): Indicator slug (e.g., "gdp_growth", "inflation_annual", "unemployment_rate_monthly")

**Returns:**
- Indicator name and description
- Recent values (latest periods with data)
- Related indicators for the same country

**Example:**
```python
# Get quarterly GDP growth for USA
result = await execute({
    "function": "get_indicator_data",
    "country_code": "USA",
    "indicator": "gdp_growth"
})

# Get inflation data for Germany
result = await execute({
    "function": "get_indicator_data",
    "country_code": "DEU",
    "indicator": "inflation_annual"
})
```

### list_countries

List all available countries with their codes.

**Parameters:** None

**Returns:**
- List of countries with name and ISO code
- Total count

**Example:**
```python
result = await execute({"function": "list_countries"})
```

### list_indicators

List all available ranking indicators.

**Parameters:** None

**Returns:**
- List of indicators with slug, name, and URL
- Total count

**Example:**
```python
result = await execute({"function": "list_indicators"})
```

## Common Indicator Slugs

### Economic Growth
- `gdp_growth` - Quarterly GDP growth rate
- `Economic_growth` - Annual GDP growth rate
- `GDP_per_capita_PPP` - GDP per capita (PPP)
- `GDP_current_USD` - GDP in current US dollars

### Inflation & Prices
- `inflation` - Inflation rate
- `inflation_annual` - Annual inflation
- `cpi` - Consumer Price Index

### Labor Market
- `unemployment_rate_monthly` - Monthly unemployment rate
- `unemployment` - Unemployment rate

### Trade
- `exports` - Exports
- `imports` - Imports
- `trade_balance` - Trade balance

### Government
- `government_debt` - Government debt
- `government_spending` - Government spending

### Demographics
- `land_area` - Land area
- `population` - Population
- `population_growth` - Population growth rate

## Notes

- Country codes follow ISO 3166-1 alpha-3 standard (3 letters)
- Data availability varies by country and indicator
- Some indicators may have quarterly, monthly, or annual frequency
- Time coverage ranges vary (some data goes back to 1960s)
- Rankings can be filtered by region for regional comparisons
