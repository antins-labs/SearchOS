# Bloomberg Stock Quote Extractor

Extracts stock quote data from Bloomberg.com quote pages.

## Important Limitations

**Bloomberg.com uses PerimeterX anti-bot protection** that aggressively blocks automated access. The skill implements multiple strategies to bypass this protection:

1. **HTTP requests** with realistic headers (usually blocked)
2. **Browser automation** with anti-detection scripts (often blocked)
3. **Cookie-based session** persistence (requires manual setup)

In most cases, you will encounter blocking. The skill provides detailed error reporting about the blocking status.

## Functions

### get_quote

Fetch a single stock quote by ticker symbol.

**Parameters:**
- `ticker` (string, required): Stock ticker symbol (e.g., 'ZBIO:US', 'AAPL:US')
- `method` (string, optional): Fetch method - 'auto', 'http', or 'browser'. Default: 'auto'

**Example:**
```python
result = await execute({
    'function': 'get_quote',
    'ticker': 'ZBIO:US'
})
```

**Returns:**
```python
{
    'success': True/False,
    'ticker': 'ZBIO:US',
    'url': 'https://www.bloomberg.com/quote/ZBIO:US',
    'blocked': True/False,
    'data': {
        'ticker': 'ZBIO:US',
        'source': 'html_parser',
        'fields': {
            # Extracted quote fields
        },
        'api_responses': [
            # Any captured API data
        ]
    },
    'error': None  # If failed
}
```

### get_quotes

Fetch multiple stock quotes at once.

**Parameters:**
- `tickers` (list, required): List of ticker symbols
- `method` (string, optional): Fetch method. Default: 'auto'

**Example:**
```python
result = await execute({
    'function': 'get_quotes',
    'tickers': ['ZBIO:US', 'MGX:US', 'MBX:US']
})
```

### check_access

Check if Bloomberg.com is accessible with the current method.

**Example:**
```python
result = await execute({
    'function': 'check_access'
})
```

**Returns:**
```python
{
    'http_access': {'success': False, 'blocked': True, ...},
    'browser_access': {'success': False, 'blocked': True, ...},
    'anti_bot_detected': True,
    'anti_bot_provider': 'PerimeterX (px-cloud.net)',
    'recommendation': '...'
}
```

## Ticker Formats

Bloomberg uses region-specific ticker formats:
- US stocks: `SYMBOL:US` (e.g., `AAPL:US`, `MSFT:US`)
- If no region is specified, `:US` is appended automatically

## Anti-Bot Protection Details

Bloomberg.com uses **PerimeterX** (px-cloud.net) bot detection:

- Detects automated browsers via JavaScript challenges
- Uses canvas fingerprinting
- Tracks browser behavior patterns
- Requires valid session cookies for access

When blocked, the page shows a "Are you a robot?" interstitial with no data.

## Error Handling

The skill returns structured error information:

```python
{
    'success': False,
    'blocked': True,
    'error': 'Blocked by PerimeterX anti-bot protection...',
    'ticker': '...'
}
```

## Recommendations

For reliable Bloomberg data access:

1. **Use browser with persistent cookies**: Manual browser session, export cookies
2. **Use Bloomberg Terminal/Professional**: Requires Bloomberg subscription
3. **Use alternative data sources**: Yahoo Finance, Alpha Vantage, etc.
4. **Wait and retry**: Rate limits may reset after some time

## Technical Details

- **Playwright**: Used for browser automation with anti-detection
- **aiohttp**: Used for direct HTTP requests (faster but usually blocked)
- **User-Agent spoofing**: Attempts to appear as real Chrome browser
- **JavaScript challenges**: Detected but not solvable without human interaction