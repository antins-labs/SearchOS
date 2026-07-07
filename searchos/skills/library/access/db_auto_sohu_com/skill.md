# Sohu Auto Database Access Skill

Access car model data from Sohu Auto's automotive database at db.auto.sohu.com.

## Overview

This skill provides programmatic access to Sohu's comprehensive car database through their portal API. It bypasses the web interface and directly queries the JSON APIs for pricing, sales statistics, dealer information, and more.

## Available Functions

### get_model_stats
Get model information and sales statistics including:
- Model name, brand, price range
- Historical monthly sales figures
- Sales rankings with trend indicators

**Parameters:**
- `model_id`: Car model ID (required)

**Example:** Model 6178 = 五菱宏光MINIEV, Model 6025 = Tesla Model Y, Model 7267 = 小米SU7

---

### get_model_prices
Get price ranges for one or more car models.

**Parameters:**
- `model_ids`: List of model IDs (required)

Returns min/max local prices for each model.

---

### get_trim_prices
Get detailed trim-level pricing organized by year and status (在售/停售).

**Parameters:**
- `model_id`: Car model ID (required)
- `city_code`: City code for local pricing (optional, default: 110100 Beijing)

Returns guide prices and dealer prices for each trim variant.

---

### get_city_prices
Get dealer prices across all cities for a model.

**Parameters:**
- `model_id`: Car model ID (required)

Returns prices organized by province and city with dealer counts.

---

### get_dealer_prices
Get detailed dealer listings with pricing.

**Parameters:**
- `model_id`: Car model ID (required)
- `city_code`: City code (optional, default: 110100)
- `size`: Number of results (optional, default: 999)

Returns dealer name, address, phone, GPS coordinates, and offered price.

---

### get_model_news
Get news articles about a car model.

**Parameters:**
- `model_id`: Car model ID (required)
- `limit`: Number of articles (optional, default: 10, max: 50)

Returns article title, brief, cover image, author, and publication date.

---

### get_competitor_ranking
Get same-segment competitor rankings with evaluation scores.

**Parameters:**
- `model_id`: Car model ID (required)

Returns competitor models with scores for: looking (外观), stuff (配置), space (空间), power (动力), expense (能耗), overall (综合).

---

### get_related_trims
Get related/recommended similar car trims for comparison.

**Parameters:**
- `model_id`: Car model ID (required)
- `limit`: Number of results (optional, default: 6)

---

### get_hot_models
Get currently trending/hot car models on the platform.

No parameters required.

---

### get_full_model_info
Get comprehensive model data in one aggregated call.

**Parameters:**
- `model_id`: Car model ID (required)
- `city_code`: City code for local pricing (optional, default: 110100)

Returns stats, prices, trims, and recent news combined.

---

## Common Model IDs

| Model ID | Name |
|----------|------|
| 6178 | 五菱宏光MINIEV |
| 6025 | Tesla Model Y |
| 7267 | 小米SU7 |
| 6582 | 比亚迪元PLUS |

## Common City Codes

| Code | City |
|------|------|
| 110100 | 北京 |
| 310100 | 上海 |
| 330100 | 杭州 |
| 440100 | 广州 |
| 440300 | 深圳 |

## Usage Examples

```python
# Get sales stats for Wuling Hongguang MINIEV
await execute({"function": "get_model_stats", "model_id": 6178})

# Compare prices of multiple models
await execute({"function": "get_model_prices", "model_ids": [6178, 6025, 7267]})

# Get dealer prices in Shanghai for Xiaomi SU7
await execute({"function": "get_dealer_prices", "model_id": 7267, "city_code": "310100"})

# Get competitor rankings
await execute({"function": "get_competitor_ranking", "model_id": 6025})

# Get comprehensive info
await execute({"function": "get_full_model_info", "model_id": 6178, "city_code": "330100"})
```

## Data Source

All data comes from Sohu Auto's portal API at `portal.auto.sohu.com/aggr`. The data includes:
- Real-time dealer pricing
- Monthly sales statistics
- Model specifications and variants
- User evaluation scores
- News articles

## Notes

- Model IDs can typically be found in the URL of the car's page on db.auto.sohu.com (e.g., model_6178)
- Prices are in 万元 (ten thousand CNY)
- Sales data is updated monthly
- Dealer prices may vary by city