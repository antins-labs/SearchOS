# Qunar Scenic Area Ticket Scraper

This skill extracts scenic area ticket information from Qunar's mobile ticket platform (touch.piao.qunar.com), one of China's largest travel booking websites.

## Host

`touch.piao.qunar.com` - Qunar mobile touch site for scenic area tickets

## Functions

### get_detail

Get detailed information for a specific scenic area by its ID.

**Parameters:**
- `sightId` (string, required): The scenic area ID (e.g., "8606")

**Returns:**
```json
{
  "success": true,
  "data": {
    "sightId": "8606",
    "title": "太昊伏羲陵文化旅游区",
    "level": "AAAAA景区",
    "score": 4.7,
    "scoreText": "很棒",
    "commentCount": 326,
    "imageCount": 60,
    "image": "https://qimgs.qunarzz.com/...",
    "lowestPrice": 8.0,
    "highestPrice": 805.0,
    "priceRange": "¥8-805",
    "ticketCategories": [
      {
        "name": "成人票",
        "priceFrom": "¥40",
        "typeId": "200515080"
      },
      ...
    ],
    "description": "...",
    "displayText": "Formatted summary..."
  }
}
```

### batch

Get information for multiple scenic areas at once.

**Parameters:**
- `sightIds` (array of strings, required): List of scenic area IDs

**Returns:**
```json
{
  "success": true,
  "data": [...],
  "displayText": "成功获取 3/3 个景区信息"
}
```

## Data Extracted

For each scenic area, the skill extracts:

1. **Basic Information**
   - Title (景区名称)
   - Level (景区等级: AAAAA, AAAA, etc.)
   - Description (简介)

2. **Rating & Reviews**
   - Score (评分, 0-5 scale)
   - Score text (评价描述, e.g., "很棒")
   - Comment count (评论数)

3. **Media**
   - Main image URL
   - Image count

4. **Pricing**
   - Lowest ticket price
   - Highest ticket price
   - Price range

5. **Ticket Categories**
   - Ticket type name (票种名称)
   - Price (价格)
   - Type ID (ticket category identifier)

## Example Scenic Areas

| sightId | Name | Level |
|---------|------|-------|
| 8606 | 太昊伏羲陵文化旅游区 | AAAAA景区 |
| 472314 | 宁明花山岩画景区 | AAAAA景区 |
| 9805 | 冶力关国家森林公园 | AAAA景区 |

## Technical Details

### Request Method
- Direct HTTP requests to `https://touch.piao.qunar.com/touch/detail.htm?id={sightId}`
- Mobile User-Agent required for proper content delivery
- No authentication required

### Parsing Strategy
- HTML parsing using regex patterns
- Extracts data from specific CSS class patterns:
  - `.mp-headfeagure-title` - Title and level
  - `.mp-commentcard-score` - Rating score
  - `.mp-commentcard-desc` - Score text
  - `.mp-totalcommentnum` - Comment count
  - `.mp-imgswipeicon-number` - Image count
  - `.mp-headfigure-img` - Main image
  - `.mp-ticket-list` - Ticket categories

### Ticket Types
Common ticket categories include:
- 成人票 (Adult tickets)
- 儿童票 (Child tickets)
- 学生票 (Student tickets)
- 老人票 (Senior tickets)
- 双人票 (Couple tickets)
- 三人票 (Family of 3 tickets)
- 大小同价 (Same price for adults and children)
- 优待票 (Discounted tickets for specific groups)
- Day tour packages (一日游套餐)

## Error Handling

The skill handles:
- Invalid/missing sightId parameters
- Network timeouts (30 second limit)
- HTTP errors
- Missing or unavailable scenic areas
- Pages with incomplete data

When an error occurs, the response includes:
```json
{
  "success": false,
  "error": "Error description",
  "data": null
}
```

## Use Cases

1. **Travel Planning**: Get ticket prices and ratings for attractions
2. **Price Comparison**: Compare ticket prices across different scenic areas
3. **Data Collection**: Gather scenic area information for analysis
4. **Travel Apps**: Integrate Qunar ticket data into travel applications

## Limitations

- Only supports scenic areas with valid IDs on Qunar platform
- Some scenic areas may have incomplete data
- Data is in Chinese language
- Real-time availability not provided (only general ticket information)
- Some scenic areas may have changed or been removed

## Testing

```python
# Test single query
result = await execute({'function': 'get_detail', 'sightId': '8606'})

# Test batch query
result = await execute({
    'function': 'batch',
    'sightIds': ['8606', '472314', '9805']
})
```