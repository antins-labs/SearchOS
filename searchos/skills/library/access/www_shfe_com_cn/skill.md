# SHFE (Shanghai Futures Exchange) Data Access Skill

This skill provides access to the Shanghai Futures Exchange (SHFE) trading data through direct API endpoints.

## Overview

The Shanghai Futures Exchange (上海期货交易所) provides comprehensive trading statistics for futures and options products. While the main website has WAF protection that can block automated browsing, the underlying `.dat` JSON API endpoints are directly accessible and provide structured data without authentication.

## Data Available

### 1. Monthly Futures Trading Statistics (`get_monthly_futures`)
Comprehensive monthly data including:
- **o_curtransaction**: Per-instrument trading data with open/high/low/close/settlement prices, volume, turnover, open interest
- **o_curturnover**: Turnover statistics aggregated by product (year-to-date, month-over-month, year-over-year changes)
- **o_curvolume**: Volume statistics by product with comparison metrics
- **o_curdelivery**: Delivery statistics (volume, value, accounts)
- **o_curopeninterest**: Open interest statistics with change indicators
- **o_curmetalindex**: Metal index price data

Products include: Copper (cu), Aluminum (al), Zinc (zn), Lead (pb), Nickel (ni), Tin (sn), Gold (au), Silver (ag), Rebar (rb), Wire Rod (wr), Hot Rolled Coil (hc), Stainless Steel (ss), Fuel Oil (fu), Bitumen (bu), Pulp (sp), Natural Rubber (nr), and more.

### 2. Monthly Options Trading Statistics (`get_monthly_options`)
Monthly options data including:
- Turnover by underlying product
- Volume statistics
- Open interest
- Exercise volume

### 3. Product Configuration (`get_product_config`)
Complete product details including:
- Product names (Chinese and English)
- Contract specifications (unit size, tick size)
- Exchange and product group assignments
- Product types (metals, energy, chemicals)

### 4. Available Months Discovery (`get_available_months`)
Discover which months have data available for querying.

### 5. Instrument Summary (`get_instrument_summary`)
Aggregated summary of trading activity:
- Top instruments by volume/turnover
- Product-level aggregation
- Individual instrument details

### 6. Top Instruments (`get_top_instruments`)
Ranked list of instruments by specified metric (volume, turnover, or open interest).

## Usage Examples

### Get Latest Monthly Futures Data
```python
result = await execute({"function": "get_monthly_futures"})
```

### Get Specific Month Data
```python
result = await execute({
    "function": "get_monthly_futures",
    "year": 2025,
    "month": 5
})
```

### Get Options Data
```python
result = await execute({
    "function": "get_monthly_options",
    "year": 2025,
    "month": 4
})
```

### Get Product Configuration
```python
result = await execute({"function": "get_product_config"})
```

### Discover Available Months
```python
result = await execute({
    "function": "get_available_months",
    "start_year": 2024,
    "end_year": 2025
})
```

### Get Trading Summary
```python
result = await execute({
    "function": "get_instrument_summary",
    "year": 2025,
    "month": 4
})
```

### Filter by Product
```python
result = await execute({
    "function": "get_instrument_summary",
    "year": 2025,
    "month": 4,
    "product": "cu"  # Copper only
})
```

### Get Top Instruments
```python
result = await execute({
    "function": "get_top_instruments",
    "year": 2025,
    "month": 4,
    "sort_by": "volume",
    "limit": 20
})
```

## Data Fields

### Transaction Data (o_curtransaction)
Each instrument record contains:
- INSTRUMENTID: Contract code (e.g., "cu2505" for Copper May 2025)
- PRODUCT: Product code (e.g., "cu")
- PRODUCTID: Product identifier with type (e.g., "cu_f" for futures)
- OPENPRICE: Opening price
- HIGHESTPRICE: Daily high
- LOWESTPRICE: Daily low
- CLOSEPRICE: Closing price
- SETTLEMENTPRICE: Settlement price
- PRICECHG: Price change from previous settlement
- VOLUME: Trading volume (in contracts)
- TURNOVER: Trading value (in 10,000 RMB)
- OPENINTEREST: Open interest (in contracts)
- OPENINTERESTCHG: Change in open interest

### Turnover Data (o_curturnover)
Product-level turnover with:
- YEARTURNOVER: Year-to-date turnover
- MONTHTURNOVER: Current month turnover
- LASTYEARTURNOVER: Previous year total
- LASTYEARMONTHTURNOVER: Previous year same month
- YEARYOYCHANGE: Year-over-year percentage change
- YOYCHANGE: Month-over-year percentage change
- MOMCHANGE: Month-over-month percentage change

## Product Codes

| Code | Product Name (CN) | Product Name (EN) |
|------|------------------|-------------------|
| cu   | 铜               | Copper            |
| al   | 铝               | Aluminum          |
| zn   | 锌               | Zinc              |
| pb   | 铅               | Lead              |
| ni   | 镍               | Nickel            |
| sn   | 锡               | Tin               |
| au   | 黄金             | Gold              |
| ag   | 白银             | Silver            |
| rb   | 螺纹钢           | Rebar             |
| wr   | 线材             | Wire Rod          |
| hc   | 热轧卷板         | Hot Rolled Coil   |
| ss   | 不锈钢           | Stainless Steel   |
| fu   | 燃料油           | Fuel Oil          |
| bu   | 石油沥青         | Bitumen           |
| sp   | 纸浆             | Pulp              |
| nr   | 天然橡胶         | Natural Rubber    |
| br   | 丁二烯橡胶       | Butadiene Rubber  |
| ao   | 氧化铝           | Alumina           |
| bc   | 铜(BC)           | Copper (Bursa)    |
| lu   | 低硫燃料油       | Low Sulfur Fuel   |
| ec   | 集运指数(欧线)   | EC Freight Index  |

## Notes

- All price data is in Chinese Yuan (RMB) unless otherwise specified
- Volume is measured in contracts (lots)
- Turnover is in 10,000 CNY
- The default behavior queries the previous month when year/month not specified
- Empty results will return an error field with details
- The API returns status code '0000' for successful queries

## API Limitations

- Only monthly data is reliably available through the direct API
- Daily data may be protected by WAF and not directly accessible
- Data is typically updated on the last trading day of each month
- Historical data availability varies by product launch date
- The API does not require authentication but uses standard browser headers