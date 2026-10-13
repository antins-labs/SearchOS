# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# EV Specifications Access Skill

This skill extracts detailed electric vehicle specifications from [evspecifications.com](https://www.evspecifications.com) model pages.

## Features

- **Complete Specification Extraction**: Retrieves all technical specifications from EV model pages
- **Organized Data**: Specifications are organized by category (Battery, Motor, Performance, Dimensions, etc.)
- **Key Specs Summary**: Quick access to the most important specifications
- **Section Filtering**: Extract specifications from specific categories only

## Available Functions

### `get_model`
Fetches complete specifications for an EV model.

**Parameters:**
- `url` (required): The full URL to the EV model page

**Returns:**
- `title`: Page title
- `model_title`: Model name extracted from title
- `key_specifications`: Most important specs (brand, model, battery, range, etc.)
- `all_specifications`: Complete flat dictionary of all specifications
- `organized_specifications`: Specs grouped by category

**Example:**
```python
result = await execute({
    "function": "get_model",
    "url": "https://www.evspecifications.com/en/model/53a43ea"
}, ctx)
```

### `get_section`
Extracts specifications from a specific section/category.

**Parameters:**
- `url` (required): The full URL to the EV model page
- `section` (required): Section keyword (e.g., "battery", "motor", "performance", "dimensions", "charging")

**Returns:**
- Specifications matching the section keyword

**Example:**
```python
result = await execute({
    "function": "get_section",
    "url": "https://www.evspecifications.com/en/model/53a43ea",
    "section": "battery"
}, ctx)
```

### `get_key_specs`
Returns only the key specifications for quick reference.

**Parameters:**
- `url` (required): The full URL to the EV model page

**Returns:**
- Brand, Model, Model year, Trim, Market
- Body style, Battery capacity
- Top speed, Acceleration
- Power, Range
- Dimensions, Weight, Seating

**Example:**
```python
result = await execute({
    "function": "get_key_specs",
    "url": "https://www.evspecifications.com/en/model/53a43ea"
}, ctx)
```

## Data Categories

The skill extracts specifications from these categories:

1. **General**: Brand, model, year, market, body style, colors
2. **Dimensions**: Length, width, height, wheelbase, cargo volume
3. **Weights**: Curb weight, payload, GVWR, towing capacity
4. **Electric Motor**: Power, torque, motor type, location
5. **Performance**: Top speed, acceleration (0-60 mph, 0-100 km/h)
6. **Battery**: Capacity, type, voltage, cells, thermal management
7. **Range & Efficiency**: EPA/WLTP range, energy consumption
8. **Charging**: Charging interfaces, power levels, times
9. **Suspension**: Front/rear suspension type
10. **Brakes**: Brake type, disc dimensions
11. **Wheels & Tires**: Rim sizes, tire specifications
12. **Steering**: Steering type, turning circle

## Sample Output

```json
{
  "success": true,
  "title": "2025 Tesla Model X - Specifications",
  "model_title": "2025 Tesla Model X",
  "key_specifications": {
    "Brand": "Tesla",
    "Model": "Model X",
    "Model year": "2025 (MY25)",
    "Market": "North America",
    "Body style": "Sport utility vehicle (SUV)",
    "Battery capacity": "100 kWh (kilowatt hours)",
    "Top speed": "149.1 mph (miles per hour) 240.0 km/h (kilometers per hour)",
    "Acceleration from 0 to 60 mph": "3.80 s (seconds)",
    "Total system power": "500 kW (kilowatts) 670.5 hp (mechanical horsepower)",
    "Range": "335.0 mi / 539.1 km"
  }
}
```

## Notes

- The skill uses Playwright browser automation to handle JavaScript-rendered content
- Pages may take a few seconds to load completely
- Some models may not have all specification categories available
- Price information is typically not available on this site
