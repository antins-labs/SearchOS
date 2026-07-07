# China Tourism Hotel Association (CTHA) Hotel Directory Skill

This skill accesses the official National Star-Rated Hotel Directory from the China Tourism Hotel Association (中国旅游饭店业协会) website at www.ctha.com.cn.

## Overview

The website hosts two main hotel directories:
- **National 5-Star Tourist Hotel Directory** (全国五星级旅游饭店名录) - Contains approximately 842 five-star hotels across China
- **National 1-4 Star Tourist Hotel Directory** (全国一至四星级旅游饭店名录) - Contains lower-rated hotels

## Features

### get_provinces
Retrieves a list of all Chinese provinces and autonomous regions with their IDs, which can be used for filtering hotels by location.

**Example:**
```python
result = await execute({"function": "get_provinces"})
# Returns: {"success": True, "count": 32, "provinces": [{"id": 2, "name": "北京市"}, ...]}
```

### get_5star_hotels
Fetches five-star hotels with optional filtering by province, pagination, and keyword search.

**Example - Get all 5-star hotels:**
```python
result = await execute({"function": "get_5star_hotels", "page": 1, "page_size": 20})
```

**Example - Get 5-star hotels in Beijing (province_id=2):**
```python
result = await execute({"function": "get_5star_hotels", "province_id": "2", "page": 1, "page_size": 20})
```

**Example - Search for a specific hotel:**
```python
result = await execute({"function": "get_5star_hotels", "keyword": "希尔顿", "page": 1})
```

### get_1to4star_hotels
Fetches one to four star hotels with optional filtering by province, specific star rating, pagination, and keyword search.

**Example - Get all 1-4 star hotels:**
```python
result = await execute({"function": "get_1to4star_hotels", "page": 1, "page_size": 20})
```

**Example - Get only 4-star hotels in Beijing:**
```python
result = await execute({"function": "get_1to4star_hotels", "province_id": "2", "star_rating": "4", "page": 1})
```

### search_hotels
Searches hotels by keyword. Requires a keyword parameter.

**Example:**
```python
result = await execute({"function": "search_hotels", "keyword": "北京王府", "page": 1})
```

## Data Fields

Each hotel record contains:
- `id`: Unique hotel identifier
- `name`: Hotel name (饭店名称)
- `province`: Province name (省份)
- `city`: City name (城市)
- `district`: District name (区县)
- `address`: Full address (地址)
- `telephone`: Contact phone number (电话)
- `star_rating`: Star rating level (星级: 1-5)
- `certificate_number`: Star rating certificate number (星级标牌号)
- `category_id`: Category identifier
- `status`: Hotel status (1=active)
- `create_time`: Record creation timestamp

## API Details

The skill uses the website's internal AJAX API endpoints:
- Province list: `/index/index/getprovince.html`
- Hotel list: `/index/index/gethotel.html`

These endpoints return JSON data that is parsed and cleaned into a structured format.

## Notes

- The base URL is `http://www.ctha.com.cn` (HTTP, not HTTPS)
- Maximum page size is 100 records
- The website may be slow to respond; a 30-second timeout is configured
- Province IDs are obtained from the `get_provinces` function
- For 5-star hotels, the API automatically sets `star_rating="5"` and `category_id="94"`
- For 1-4 star hotels, you can specify a particular star rating or get all with `star_rating=""` and `category_id="58"`

## Use Cases

1. **Browse all 5-star hotels in China**: Get an overview of luxury hotels nationwide
2. **Find hotels in a specific region**: Use province filtering to get hotels in Beijing, Shanghai, Guangdong, etc.
3. **Search for a specific hotel**: Use keyword search to find hotels by name
4. **Get hotel contact information**: Retrieve addresses and phone numbers
5. **Analyze hotel distribution**: See how many star-rated hotels are in each region

## Technical Notes

The CTHA website loads hotel data via AJAX after the initial page load. The JavaScript on the page calls POST endpoints to retrieve JSON data. This skill directly accesses those endpoints to fetch structured data efficiently without needing browser automation.