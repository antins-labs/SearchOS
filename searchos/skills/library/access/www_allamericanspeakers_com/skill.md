# All American Speakers Bureau - Access Skill

## Overview

This skill provides access to All American Speakers Bureau (www.allamericanspeakers.com), a full-service speakers bureau and celebrity booking agency. Extract detailed information about keynote speakers, celebrities, and performers including biographies, speaking fees, categories, and availability.

## Available Functions

### 1. `get_profile`

Get detailed profile information for a specific speaker.

**Parameters:**
- `url` (optional): Full URL to the speaker profile page
- `speaker_id` (optional): Speaker ID number
- `speaker_name` (optional): Speaker name (used with speaker_id for URL construction)

**Example:**
```python
# By URL
result = await execute({
    "function": "get_profile",
    "url": "https://www.allamericanspeakers.com/celebritytalentbios/Nelly+Cheboi/464943"
})

# By ID
result = await execute({
    "function": "get_profile",
    "speaker_id": "418752",
    "speaker_name": "Jeison Aristizábal"
})
```

**Returns:**
```json
{
    "success": true,
    "name": "Nelly Cheboi",
    "speaker_id": "464943",
    "categories": ["Computer Science", "Education", "Empowerment", "Female Leadership"],
    "biography": "Nelly Cheboi grew up in poverty in rural Kenya...",
    "live_event_fee": "$5,000 - $10,000",
    "virtual_event_fee": "$5,000 - $10,000",
    "travels_from": "Chicago, IL, USA",
    "image_url": "https://thumbnails.aaehq.com/t_face_s270/photo/image/...",
    "url": "https://www.allamericanspeakers.com/celebritytalentbios/Nelly+Cheboi/464943"
}
```

### 2. `get_category`

Get a list of speakers from a specific category.

**Parameters:**
- `category` (optional): Category path (e.g., "Technology/Artificial-Intelligence")
- `url` (optional): Full URL to the category page

**Example:**
```python
result = await execute({
    "function": "get_category",
    "category": "Technology/Artificial-Intelligence"
})
```

**Returns:**
```json
{
    "success": true,
    "category": {
        "url": "https://www.allamericanspeakers.com/category/Technology/Artificial-Intelligence",
        "title": "Artificial Intelligence Speakers | Machine Learning Experts",
        "speaker_count": 1872
    },
    "speakers": [
        {
            "position": 1,
            "name": "Zack Kass",
            "url": "https://www.allamericanspeakers.com/speakers/454184/Zack-Kass",
            "image": "https://thumbnails.aaehq.com/t_face_s170/photo/image/..."
        }
    ],
    "total_count": 1872
}
```

### 3. `search_by_id`

Search for a speaker by their unique ID number.

**Parameters:**
- `speaker_id` (required): Speaker ID number

**Example:**
```python
result = await execute({
    "function": "search_by_id",
    "speaker_id": "418752"
})
```

### 4. `list_categories`

List available speaker categories for browsing.

**Parameters:** None

**Example:**
```python
result = await execute({
    "function": "list_categories"
})
```

**Returns:**
```json
{
    "success": true,
    "categories": [
        {
            "name": "Artificial Intelligence",
            "url": "https://www.allamericanspeakers.com/category/Technology/Artificial-Intelligence",
            "path": "Technology/Artificial-Intelligence"
        }
    ],
    "total_count": 64
}
```

## Data Fields

| Field | Description |
|-------|-------------|
| `name` | Speaker's full name |
| `speaker_id` | Unique speaker identifier |
| `categories` | List of topics/categories the speaker covers |
| `biography` | Full biography text |
| `live_event_fee` | Speaking fee range for in-person events |
| `virtual_event_fee` | Speaking fee range for virtual events |
| `travels_from` | Location speaker travels from |
| `image_url` | URL to speaker's headshot |
| `meta_description` | SEO meta description from page |

## Category Paths

Some popular category paths:
- `Technology/Artificial-Intelligence`
- `Business/Entrepreneurship`
- `Motivational`
- `Diversity-Inclusion`
- `Health/Mental-Health`
- `Celebrity`
- `Sports`
- `Leadership`

## Notes

1. **Cloudflare Protection**: The site uses Cloudflare but standard HTTP requests with proper headers work without browser automation.

2. **Fee Display**: Some speakers show "Please Contact" for fees instead of price ranges.

3. **Speaker URLs**: Profile pages follow the pattern `/celebritytalentbios/{Name}/{ID}` where Name uses `+` for spaces.

4. **Category Data**: Category pages embed speaker lists in JSON-LD structured data (ItemList), providing efficient access to all speakers in a category.

5. **Rate Limiting**: Recommended to limit requests to 2 per second to avoid throttling.

## Error Handling

All functions return a consistent error format:

```json
{
    "success": false,
    "error": "Description of the error",
    "status_code": 404
}
```

## Use Cases

- **Event Planning**: Research speakers for corporate events, conferences, and meetings
- **Fee Research**: Compare speaking fees across different speakers
- **Category Exploration**: Find speakers by topic or specialty
- **Speaker Discovery**: Browse categories to discover relevant speakers