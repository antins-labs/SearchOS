# J.D. Power Vehicle Ratings Access Skill

This skill provides access to J.D. Power's vehicle ratings, awards, and specifications data.

## Overview

J.D. Power is a global leader in consumer insights, advisory services, and data analytics. Their automotive division provides comprehensive vehicle ratings based on real-world owner experiences through several major studies:

- **Vehicle Dependability Study (VDS)**: Measures problems experienced by original owners of 3-year-old vehicles
- **Initial Quality Study (IQS)**: Measures problems experienced by original owners of new vehicles during the first 90 days of ownership
- **APEAL Study**: Measures owner emotional attachment and level of excitement with their new vehicle

## Available Functions

### 1. `list_studies`

List all available J.D. Power rating studies with descriptions and available years.

**Parameters**: None

**Example**:
```python
result = await execute({'function': 'list_studies'})
```

**Response**:
```json
{
  "success": true,
  "data": {
    "studies": [
      {
        "name": "dependability",
        "title": "Vehicle Dependability Study (VDS)",
        "description": "Measures problems experienced by original owners of 3-year-old vehicles",
        "url_pattern": "https://www.jdpower.com/cars/ratings/dependability/{year}",
        "available_years": [2024, 2025]
      },
      ...
    ]
  }
}
```

### 2. `get_ratings`

Get vehicle ratings and award winners for a specific study and year.

**Parameters**:
- `study` (required): Study type - one of `dependability`, `quality`, `performance`
- `year` (required): Model year (e.g., 2024, 2025)

**Example**:
```python
result = await execute({
    'function': 'get_ratings',
    'study': 'dependability',
    'year': 2025
})
```

**Response**:
```json
{
  "success": true,
  "data": {
    "study": "dependability",
    "year": 2025,
    "title": "2025 Dependability Awards and Ratings | JD Power",
    "brand_ratings": [
      {
        "rank": 1,
        "make": "Buick",
        "year": "2022",
        "url": "https://www.jdpower.com/cars/2022/buick"
      },
      {
        "rank": 2,
        "make": "Lexus",
        "year": "2022",
        "url": "https://www.jdpower.com/cars/2022/lexus"
      }
    ],
    "segment_winners": {
      "Small": [
        {
          "category": "Small SUV",
          "year": "2022",
          "make": "Nissan",
          "model": "Kicks",
          "url": "https://www.jdpower.com/cars/2022/nissan/kicks"
        }
      ],
      "Compact": [
        {
          "category": "Compact Car",
          "year": "2022",
          "make": "Toyota",
          "model": "Corolla",
          "url": "https://www.jdpower.com/cars/2022/toyota/corolla"
        }
      ],
      ...
    }
  }
}
```

### 3. `get_vehicle`

Get ratings and specifications for a specific vehicle model.

**Parameters**:
- `year` (required): Model year (e.g., 2022)
- `make` (required): Vehicle make (e.g., 'toyota', 'bmw')
- `model` (required): Vehicle model (e.g., 'corolla', '3-series')

**Example**:
```python
result = await execute({
    'function': 'get_vehicle',
    'year': 2022,
    'make': 'toyota',
    'model': 'corolla'
})
```

**Response**:
```json
{
  "success": true,
  "data": {
    "url": "https://www.jdpower.com/cars/2022/toyota/corolla",
    "title": "2022 Toyota Corolla Ratings and Reviews | JD Power",
    "year": "2022",
    "make": "Toyota",
    "model": "Corolla",
    "ratings": [...],
    "sections": [...]
  }
}
```

## Data Extracted

### Rating Studies

For each study, the skill extracts:

1. **Brand Ratings**: Overall brand rankings for the study
   - Rank position
   - Make name
   - Model year
   - Link to brand page

2. **Segment Winners**: Award winners by vehicle segment
   - Vehicle category (e.g., "Compact Car", "Midsize SUV")
   - Year, Make, Model
   - Link to vehicle page
   
   Segments include:
   - Small Vehicles
   - Compact Vehicles
   - Midsize Vehicles
   - Large Vehicles

### Vehicle Pages

For individual vehicles, the skill extracts:
- Basic vehicle information (year, make, model)
- Rating scores
- Specification sections

## Technical Details

### Site Structure

J.D. Power uses Next.js with server-side rendering. The site structure:
- Ratings URL pattern: `/cars/ratings/{study}/{year}`
- Vehicle URL pattern: `/cars/{year}/{make}/{model}`

### Data Extraction

Due to the server-side rendering nature of the site, this skill uses Playwright browser automation to extract data from the rendered pages. The skill:
1. Navigates to the appropriate page
2. Waits for dynamic content to load
3. Extracts structured data from the DOM
4. Parses and formats the information

### Limitations

1. **Rate Limiting**: The site may implement rate limiting. The skill is configured for 1 request per second.
2. **Cloudflare Protection**: Some pages may be blocked by Cloudflare protection, particularly for older years.
3. **JavaScript Required**: The site requires JavaScript execution, preventing simple HTTP requests.
4. **Vehicle Page Reliability**: Individual vehicle pages have higher block rates than ratings pages.

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Access blocked by Cloudflare",
  "url": "https://www.jdpower.com/cars/ratings/dependability/2024",
  "study": "dependability",
  "year": 2024
}
```

Common errors:
- `Access blocked by Cloudflare`: The site's protection system blocked the request
- `Missing required parameter`: A required parameter was not provided
- `Invalid study`: The study parameter is not one of the valid options

## Use Cases

1. **Market Research**: Analyze vehicle dependability and quality trends across years
2. **Competitive Analysis**: Compare brand rankings and segment performance
3. **Consumer Information**: Retrieve award winners for specific vehicle categories
4. **Data Integration**: Incorporate J.D. Power ratings into automotive databases

## Testing

To test the skill:

```python
# List available studies
result = await execute({'function': 'list_studies'})

# Get ratings
result = await execute({
    'function': 'get_ratings',
    'study': 'dependability',
    'year': 2025
})

# Get vehicle details
result = await execute({
    'function': 'get_vehicle',
    'year': 2022,
    'make': 'toyota',
    'model': 'corolla'
})
```