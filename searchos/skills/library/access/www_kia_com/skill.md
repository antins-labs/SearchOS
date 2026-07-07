# Kia Vehicle Specifications Extractor

Extracts detailed vehicle specifications and trim comparison data from the official Kia USA website (kia.com).

## Features

- **Trim Comparison**: Fetches all available trim levels for a vehicle model with pricing and feature comparisons
- **Vehicle Specs**: Retrieves detailed specifications including dimensions, engine specs, fuel economy, safety features, and equipment
- **Multiple Models**: Supports all Kia models (K4, K5, Sportage, Sorento, Telluride, Carnival, Niro, EV6, EV9, etc.)

## Usage

### Get Trim Comparison

Compare all available trim levels for a Kia model:

```python
result = await execute({
    'function': 'get_trim_comparison',
    'model': 'k4'
})
```

Returns:
- Model and year information
- List of trim levels with MSRP pricing
- Detailed specifications organized by category
- Feature availability per trim (Standard/Not Available/Available)

### Get Vehicle Specs

Get specifications for a specific vehicle:

```python
result = await execute({
    'function': 'get_vehicle_specs',
    'model': 'k4',
    'year': 2025
})
```

Returns:
- Model, year, and trim information
- MSRP pricing
- Categorized specifications (Engine, Safety, Interior, Exterior, etc.)

## Example Response

### Trim Comparison Response

```json
{
  "success": true,
  "type": "compare",
  "model": "K4",
  "year": "2026",
  "trims": [
    {"name": "LX", "msrp": "22290"},
    {"name": "LXS", "msrp": "23390"},
    {"name": "EX", "msrp": "24490"},
    {"name": "GT-Line", "msrp": "25490"},
    {"name": "GT-Line Turbo", "msrp": "28390"}
  ],
  "specifications": {
    "EPA Mileage Ratings": {
      "EPA MPG Estimates (City/Highway/Combined)*": [
        "29/39/33",
        "29/39/33",
        "29/39/33",
        "29/39/33",
        "26/33/28"
      ]
    },
    "Driver Assistance Technology": {
      "Blind-Spot Collision Warning w/ Parallel Exit": [
        "Not Available",
        "Standard",
        "Standard",
        "Standard",
        "Standard"
      ]
    }
  }
}
```

## Supported Models

- **Sedans**: K4, K5
- **SUVs/CUVs**: Sportage, Sorento, Telluride, Niro
- **Minivans**: Carnival
- **Electric**: EV6, EV9
- **Hybrids**: Check Kia website for current hybrid variants

## Notes

- The extractor uses browser automation to handle JavaScript-rendered content
- Data is scraped from the official Kia USA website
- Specifications are organized by category (Safety, Performance, Features, etc.)
- Trim availability and pricing may vary by region and time

## Limitations

- Only supports Kia USA website (kia.com/us/en)
- Uses Playwright for browser automation, which has higher overhead than direct API calls
- Some optional features may not be captured correctly due to complex page rendering