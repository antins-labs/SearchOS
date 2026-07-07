# Investing.com Historical Market Data Access Skill

This skill provides access to historical market price data from investing.com, one of the world's leading financial information websites.

## Overview

Investing.com hosts standardized financial data tables including:
- Historical OHLCV (Open, High, Low, Close, Volume) data for indices, stocks, forex, commodities, and cryptocurrencies
- Technical indicators and analysis
- Real-time quotes and charts

This skill specializes in extracting **historical price data** which is typically difficult for generic scrapers to access due to:
- Cloudflare bot protection
- JavaScript-rendered content
- Dynamic data loading
- Anti-scraping measures

## Features

### 1. get_historical_data

Fetch historical price data for a specific financial instrument.

**Parameters:**
- `instrument` (required): Instrument identifier - can be a slug (e.g., 'hang-sen-40'), name (e.g., 'hsi'), or numeric ID
- `start_date` (optional): Start date in YYYY-MM-DD or MM/DD/YYYY format
- `end_date` (optional): End date in YYYY-MM-DD or MM/DD/YYYY format

**Returns:**
- `success`: Boolean indicating success
- `data`: Array of historical price records with fields:
  - `date`: Date of the data point
  - `close`: Closing price
  - `open`: Opening price
  - `high`: High price
  - `low`: Low price
  - `vol`: Volume (if available)
  - `change_pct`: Percentage change (if available)
- `instrument_id`: Resolved instrument ID
- `instrument_name`: Human-readable instrument name
- `source`: Data source ('next_data' or 'table_extraction')

**Example:**
```json
{
  "function": "get_historical_data",
  "instrument": "hang-sen-40",
  "start_date": "2024-01-01",
  "end_date": "2024-01-31"
}
```

### 2. search_instrument

Search for supported instruments by name or symbol.

**Parameters:**
- `query` (required): Search query string

**Returns:**
- List of matching instruments with their slugs and IDs

**Example:**
```json
{
  "function": "search_instrument",
  "query": "gold"
}
```

### 3. list_supported_instruments

List all supported instruments organized by category.

**Returns:**
- Grouped list of instruments by category (indices, forex, commodities, crypto, stocks)
- Total count of supported instruments

**Example:**
```json
{
  "function": "list_supported_instruments"
}
```

## Supported Instruments

### Indices
- Hang Seng 40 (HSI): `hang-sen-40`, `hsi`, ID: 944422
- S&P 500: `spx-500`, `sp500`, `s&p-500`, ID: 20
- Dow Jones: `us-30`, `djia`, `dow-jones`, ID: 169
- NASDAQ 100: `nasdaq-100`, `nasdaq`, `us-tech-100`, ID: 1497
- Nikkei 225: `nikkei-225`, `nikkei`, ID: 178
- FTSE 100: `ftse-100`, `ftse`, ID: 27
- DAX: `dax`, ID: 172
- CAC 40: `cac-40`, `cac`, ID: 167
- Euro Stoxx 50: `euro-stoxx-50`, ID: 177
- Shanghai Composite: `shanghai-composite`, `shanghai`, ID: 39218

### Forex
- EUR/USD: `eur-usd`, ID: 1
- GBP/USD: `gbp-usd`, ID: 3
- USD/JPY: `usd-jpy`, ID: 4
- USD/CHF: `usd-chf`, ID: 5
- AUD/USD: `aud-usd`, ID: 6
- USD/CAD: `usd-cad`, ID: 7
- NZD/USD: `nzd-usd`, ID: 8
- EUR/GBP: `eur-gbp`, ID: 9
- EUR/JPY: `eur-jpy`, ID: 10

### Commodities
- Gold: `gold`, ID: 8830
- Silver: `silver`, ID: 8836
- Crude Oil WTI: `crude-oil-wti`, `wti`, ID: 8849
- Brent Oil: `brent-oil`, `brent`, ID: 8833
- Natural Gas: `natural-gas`, ID: 8862

### Cryptocurrencies
- Bitcoin: `bitcoin`, `btc`, ID: 945629
- Ethereum: `ethereum`, `eth`, ID: 940810

### Stocks (Examples)
- Apple: `aapl`, ID: 6408
- Microsoft: `msft`, ID: 2456
- Google/Alphabet: `googl`, ID: 6562
- Amazon: `amzn`, ID: 237
- Tesla: `tsla`, ID: 6347

## Technical Details

### Data Extraction Methods

The skill uses two extraction methods:

1. **Next.js Data Extraction**: Attempts to extract data from `__NEXT_DATA__` script tag, which contains the server-rendered props including historical data.

2. **Table Scraping**: Falls back to parsing HTML tables when Next.js data is not available.

### Cloudflare Handling

Investing.com is protected by Cloudflare's anti-bot system. The skill:

1. Uses Playwright browser automation with Chromium
2. Implements anti-detection measures (webdriver flag removal, etc.)
3. Waits for JavaScript challenges to complete
4. Uses realistic browser fingerprinting

### Limitations

- **Rate Limiting**: Cloudflare may still block requests during high traffic or if rate limits are exceeded
- **Cookies Required**: Some sessions may require cookies from initial page visits
- **Dynamic Content**: Data is loaded dynamically and may require waiting
- **Instrument Coverage**: Not all instruments are pre-mapped; use numeric IDs for others

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Cloudflare challenge not passed",
  "url": "https://www.investing.com/indices/hang-sen-40-historical-data"
}
```

## Requirements

- Python 3.8+
- Playwright with Chromium browser (`pip install playwright && playwright install chromium`)
- aiohttp

## Dependencies

```bash
pip install playwright aiohttp
playwright install chromium
```

## Use Cases

1. **Market Analysis**: Fetch historical price data for technical analysis
2. **Backtesting**: Get historical data for trading strategy backtesting
3. **Data Aggregation**: Collect price data for multiple instruments
4. **Price Monitoring**: Track historical price movements over time

## Notes

- The skill may take 10-20 seconds to complete due to Cloudflare challenge handling
- Data quality depends on investing.com's data availability
- Some less liquid instruments may have limited historical data
- Weekend and holiday data may be missing depending on market hours