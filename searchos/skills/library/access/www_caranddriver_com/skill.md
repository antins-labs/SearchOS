# Car and Driver Vehicle Data Extractor

This skill extracts comprehensive vehicle information from Car and Driver (caranddriver.com), including specifications, pricing, ratings, and trim data.

## Features

- **Vehicle Search**: Search for vehicles by make, model, and year
- **Detailed Specs**: Extract EPA fuel economy, seating, cargo capacity, drivetrains, warranties
- **Pricing Data**: Get price ranges (low/high), including MSRP for specific trims
- **Ratings**: Car and Driver ratings, safety scores, awards (10Best, Editors' Choice, EV of the Year)
- **Trim Information**: Available trims with engine, transmission, and performance details
- **Specs Pages**: Parse detailed test results from specs pages (0-60, horsepower, torque, etc.)

## Usage Examples

### Search for a Vehicle

```python
result = await execute({
    'function': 'search',
    'make': 'ford',
    'model': 'ranger',
    'year': 2019
})
```

Returns comprehensive data including:
- Vehicle info (name, body style, make)
- Price range ($25,195 - $39,760)
- Car and Driver rating (7/10)
- EPA fuel economy (18-23 combined MPG)
- Available drivetrains, seating capacity
- Warranty information

### Get Detailed Specs Page

```python
result = await execute({
    'function': 'get_specs',
    'make': 'ford',
    'model': 'mustang-mach-e',
    'year': 2021
})
```

Returns detailed test results including:
- 0-60 mph time
- Horsepower and torque
- Curb weight
- EPA range and MPGe
- Base and as-tested pricing

### List Available Years

```python
result = await execute({
    'function': 'list_years',
    'make': 'ford',
    'model': 'bronco'
})
```

Returns all model years available for the vehicle.

### Get Vehicle by URL

```python
result = await execute({
    'function': 'get_vehicle',
    'url': 'https://www.caranddriver.com/ford/bronco-2021'
})
```

## Data Structure

The extracted data includes:

### Vehicle Information
- `make`: Manufacturer (e.g., "Ford")
- `model`: Model name (e.g., "Ranger")
- `body_style`: Body type (e.g., "pickup", "suv")
- `available_years`: List of available model years

### Pricing
- `price.low`: Starting MSRP
- `price.high`: Maximum MSRP
- `price.is_estimate`: Whether price is estimated

### Ratings
- `ratings.cd_rating`: Car and Driver score (1-10)
- `ratings.safety`: Safety rating
- `ratings.is_cd_ten_best`: 10Best award winner
- `ratings.is_cd_editors_choice`: Editors' Choice award

### Specifications (per year)
- `specs.epa`: Fuel economy (city/highway/combined)
- `specs.seating`: Seating capacity range
- `specs.drivetrains`: Available drivetrain options
- `specs.warranties`: Warranty information

### Properties
- `properties.horsepower`: Engine horsepower
- `properties.zero_to_sixty`: 0-60 mph time
- `properties.primary_fuel_type`: Gas, electric, hybrid, etc.

### Detailed Specs (from specs pages)
- `zero_to_sixty`: 0-60 mph time
- `quarter_mile`: Quarter-mile time and speed
- `horsepower`, `torque`: Engine output
- `curb_weight`: Vehicle weight
- `epa_combined/city/highway`: Fuel economy
- `range`: Electric vehicle range

## URL Patterns

- Review page: `https://www.carandriver.com/{make}/{model}-{year}`
- Specs page: `https://www.carandriver.com/{make}/{model}/specs/{year}/{make}_{submodel}_{year}`

## API Notes

- Data is extracted from the page's `__NEXT_DATA__` JSON structure
- JSON-LD structured data is used as a backup source
- HTTP requests include standard browser headers
- All data is returned in structured JSON format