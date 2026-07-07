# Trip.com Travel Guide Attraction Extractor

This skill extracts detailed attraction information from Trip.com travel guide pages.

## Features

Extracts the following information from Trip.com attraction pages:
- Basic Info: POI ID, name (local & English), type, address
- Ratings: Average rating, review count
- Location: GPS coordinates (latitude/longitude)
- Hours: Opening hours with seasonal variations
- Pricing: Ticket prices when available
- Contact: Phone numbers
- Reviews: Recent visitor reviews with ratings and images
- Additional: Hot score, recommended visit duration, district info

## Supported URLs

Works with Trip.com travel guide attraction URLs like:
- `https://my.trip.com/travel-guide/attraction/lintan/yeliguan-scenic-area-131183999`
- `https://www.trip.com/travel-guide/attraction/tanchang/guan-e-gou-scenic-area-10521199`

The POI ID is the numeric suffix in the URL (e.g., `131183999` or `10521199`).

## Functions

### get_attraction_by_id

Fetch attraction details using the POI ID.

```json
{
  "function": "get_attraction_by_id",
  "poi_id": 131183999,
  "locale": "en-XX",
  "currency": "USD"
}
```

### get_attraction_by_url

Fetch attraction details using the full Trip.com URL.

```json
{
  "function": "get_attraction_by_url",
  "url": "https://my.trip.com/travel-guide/attraction/lintan/yeliguan-scenic-area-131183999"
}
```

### search_attractions

Not available - Trip.com does not provide a public search API. Use the website directly to find attraction URLs/IDs.

## Example Response

```json
{
  "success": true,
  "data": {
    "poi_id": 131183999,
    "name": "Yeliguan Scenic Area",
    "name_local": "冶力关旅游区",
    "type": "SIGHT",
    "address": "甘南藏族自治州临潭县冶力关镇",
    "rating": 4.4,
    "review_count": 45,
    "opening_hours_desc": "Waktu operasi: Musim panas 07:30–18:00, Musim sejuk 09:00–16:00",
    "opening_hours": [
      {"season": "Musim panas", "hours": "07:30–18:00"},
      {"season": "Musim sejuk", "hours": "09:00–16:00"}
    ],
    "price": "36.38",
    "coordinate": {
      "coordinateType": "GCJ02",
      "latitude": 35.013319,
      "longitude": 103.622037
    },
    "is_free": false,
    "hot_score": "5.2",
    "recommended_duration": "1–2 hari"
  }
}
```

## Notes

- The skill extracts data from embedded JSON in the HTML page (no API calls needed)
- Prices are shown in the requested currency if available
- Reviews are limited to the 10 most recent
- Opening hours may vary by season and are shown with descriptions in the page's locale
- Coordinates use the GCJ02 coordinate system (Chinese standard)