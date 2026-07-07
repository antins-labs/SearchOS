# Upstream Bio SEC Filings Extractor

This skill extracts SEC filing data from the Upstream Bio investor relations website (investors.upstreambio.com).

## Features

- **List SEC Filings**: Retrieve a list of all SEC filings with optional filtering by filing type
- **Get Filing Details**: Extract detailed information about a specific SEC filing
- **Search Filings**: Search filings by keyword or phrase

## Usage

### List All SEC Filings

```python
result = await execute({
    "function": "list_sec_filings"
})
```

Returns a list of all available SEC filings with metadata.

### Filter by Filing Type

```python
result = await execute({
    "function": "list_sec_filings",
    "filing_type": "S-1",  # or "10-K", "8-K", "s-1a", etc.
    "limit": 10
})
```

### Get Specific Filing Details

```python
result = await execute({
    "function": "get_sec_filing_detail",
    "filing_type": "s-1a",
    "accession_number": "0001193125-24-233296"
})
```

Returns detailed information including document links and filing metadata.

### Search Filings

```python
result = await execute({
    "function": "search_filings",
    "query": "registration",
    "limit": 5
})
```

## Common SEC Filing Types

- **S-1, S-1A**: Registration statements
- **10-K**: Annual reports
- **10-Q**: Quarterly reports
- **8-K**: Current reports
- **4**: Insider trading reports
- **DEF 14A**: Proxy statements

## Technical Details

### Access Method

The skill uses Playwright browser automation with stealth configuration to bypass:
- Cloudflare protection
- Bot detection mechanisms
- JavaScript-rendered content

### Data Extraction

The extractor parses HTML tables on the investor relations page to extract:
- Filing type
- Filing date
- Description
- Document links

### Return Format

All functions return a dictionary with:
- `error`: Error message if any, or `None` on success
- `filings`: List of filing objects (for list/search functions)
- `documents`: List of document links (for detail function)
- `total`: Count of results
- Additional metadata as applicable

## Limitations

- Requires browser automation, which is slower than direct API calls
- May experience intermittent failures due to Cloudflare protection
- Requires proper browser initialization (handled automatically)
- Network timeouts may occur (handled with retries)

## Error Handling

The skill includes:
- Automatic retry logic (up to 3 attempts)
- Proper browser cleanup after each request
- Detailed error messages for troubleshooting
- Graceful handling of network issues

## Probe URLs

- SEC filings list: https://investors.upstreambio.com/financial-information/sec-filings
- Filing detail example: https://investors.upstreambio.com/sec-filings/sec-filing/s-1a/0001193125-24-233296/

## Platform Information

- CMS: Drupal
- IR Platform: Custom investor relations site
- Protection: Cloudflare
- Rendering: JavaScript-required for table data