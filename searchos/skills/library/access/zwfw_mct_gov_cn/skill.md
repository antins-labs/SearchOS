# China 5-Star Hotel Database Access Skill

This skill provides access to the China Ministry of Culture and Tourism's (文化和旅游部) 5-star hotel database at `zwfw.mct.gov.cn`.

## Overview

The database contains comprehensive information about 5-star hotels across China, including:
- Hotel name (酒店名称)
- Province/location (所属地区)
- Hotel card ID (饭店编号)
- Rating level (星级)
- Unique identifier (UUID)

## API Details

The site uses SM4 encryption for all API communications:

1. **Encryption Key**: Retrieved via `POST /portal/getsm4key`
2. **Request Encryption**: Data is encrypted using SM4 ECB mode before sending
3. **Response Decryption**: Encrypted responses are decrypted using the same SM4 key

### SM4 Encryption

The implementation uses the site's built-in SM4 JavaScript library accessed via Playwright:
- `encrypt_ecb(plaintext, key)` - Encrypt data
- `decrypt_ecb(ciphertext, key)` - Decrypt data

The encrypted data uses Base64 encoding with URL-safe character substitutions:
- `+` → `@`
- `\r` → `#`
- `\n` → `!`

## Available Functions

### 1. list_hotels

List hotels with pagination and optional search filters.

**Parameters:**
- `page_num` (integer): Page number, starting from 1
- `page_size` (integer): Items per page, max 100
- `hotel_name` (string): Search by hotel name (partial match)
- `province` (string): Filter by province name

**Returns:**
```json
{
  "success": true,
  "data": {
    "pagination": {
      "total": 835,
      "current": 1,
      "totalPage": 56,
      "pageSize": 15
    },
    "list": [
      {
        "hotelName": "王府饭店",
        "province": "北京",
        "uuid": 55407
      }
    ]
  }
}
```

**Example:**
```python
result = await execute({
    "function": "list_hotels",
    "page_num": 1,
    "page_size": 15,
    "hotel_name": "希尔顿",
    "province": ""
})
```

### 2. get_hotel_detail

Get detailed information for a specific hotel.

**Parameters:**
- `uuid` (string, required): Hotel's unique identifier

**Returns:**
```json
{
  "success": true,
  "data": {
    "createtime": 1782034202000,
    "delflag": 0,
    "hotelCardid": "1150001",
    "hotelLevel": "五星",
    "hotelName": "王府饭店",
    "lastupdatetime": 1782034202000,
    "province": "北京",
    "serialnumber": 55407,
    "uuid": 55407
  }
}
```

**Example:**
```python
result = await execute({
    "function": "get_hotel_detail",
    "uuid": "55407"
})
```

### 3. search_hotels

Search for hotels and return up to a specified number of results.

**Parameters:**
- `query` (string): Search query for hotel name
- `province` (string): Filter by province
- `max_results` (integer): Maximum number of results to return

**Returns:**
```json
{
  "success": true,
  "count": 13,
  "data": [
    {
      "hotelName": "北京希尔顿酒店",
      "province": "北京",
      "uuid": 55411
    }
  ]
}
```

**Example:**
```python
result = await execute({
    "function": "search_hotels",
    "query": "希尔顿",
    "province": "北京",
    "max_results": 50
})
```

## Data Statistics

Based on initial queries:
- Total hotels: 835+ entries
- Provinces: All Chinese provinces and major cities
- Popular hotel chains: Hilton (13 locations), Shangri-La, Kempinski, etc.

## Province Names

Common province names in the database:
- 北京, 北京市
- 广东省, 浙江省, 江苏省
- 上海市, 天津市, 重庆市
- 四川省, 陕西省, 湖北省

## Technical Notes

1. **Browser Automation**: Uses Playwright to execute SM4 encryption/decryption in the site's JavaScript context
2. **Session Management**: The browser instance is reused across requests for efficiency
3. **Error Handling**: All errors are returned in a structured format with the `error` key
4. **Concurrency**: The client is designed to be thread-safe for use in async contexts

## Limitations

- The API may have rate limiting (not yet encountered in testing)
- Some province names may be inconsistently formatted (e.g., "北京" vs "北京市")
- Hotel names are stored in Chinese only

## Example Usage Patterns

### Get all hotels in a province
```python
result = await execute({
    "function": "search_hotels",
    "province": "广东省",
    "max_results": 1000
})
```

### Find a specific hotel
```python
# Search by name
hotels = await execute({
    "function": "search_hotels",
    "query": "王府饭店"
})

# Get full details
if hotels['data']:
    detail = await execute({
        "function": "get_hotel_detail",
        "uuid": str(hotels['data'][0]['uuid'])
    })
```

### Paginated listing
```python
page1 = await execute({
    "function": "list_hotels",
    "page_num": 1,
    "page_size": 50
})

total_pages = page1['data']['pagination']['totalPage']
```