# Planned Parenthood Health Center Access Skill

This skill provides access to Planned Parenthood's health center database through their public API.

## Features

- **Search Health Centers**: Find locations by zip code, city, or state
- **Filter by Service**: Narrow results by specific service types (abortion, birth control, STD testing, etc.)
- **Filter by Channel**: Find telehealth, onsite, or PP Direct services
- **Get Opening Hours**: Real-time facility hours and current open/closed status
- **List Services**: Get all available service categories

## API Endpoints Used

- `/health-center/api/search` - Search for health centers
- `/health-center/api/_validate_location` - Validate location input
- `/_facility-opening-hours` - Get facility hours

## Usage Examples

### Search for Health Centers by Zip Code

```json
{
  "function": "search",
  "location": "93728"
}
```

Returns health centers near the specified zip code with full details including:
- Name and organization
- Address and location
- Phone numbers
- Services offered
- Hours of operation
- Distance from search location
- Appointment booking URL

### Search with Service Filter

```json
{
  "function": "search",
  "location": "California",
  "service": "abortion",
  "channel": "onsite"
}
```

Returns only health centers that offer abortion services with onsite visits.

### Search Within Distance

```json
{
  "function": "search",
  "location": "Los Angeles, CA",
  "distance": 25
}
```

Returns health centers within 25 miles of Los Angeles.

### Get Facility Opening Hours

```json
{
  "function": "hours",
  "facility_ids": [192, 1122]
}
```

Returns real-time opening information including:
- Whether the facility is currently open
- Today's opening hours (if open)
- Next opening hours (if closed)
- Local timezone

### List Available Services

```json
{
  "function": "services"
}
```

Returns a list of all service categories with their slugs and IDs for filtering.

## Data Returned

### Health Center Search Results

Each result includes:

| Field | Description |
|-------|-------------|
| id | Internal facility ID |
| display_name | Health center name |
| url | URL path to center details |
| organization | Operating Planned Parenthood affiliate |
| location | Address, city, state, zip, timezone |
| phone_numbers | Display, fax, and appointment phone numbers |
| services | List of services with telehealth/onsite availability |
| hours | Weekly schedule (Sunday-Saturday) |
| distance | Distance from search location (miles) |
| appointment_url | Online booking link |

### Service Types

Available service filters:
- `abortion` - Abortion services
- `birth-control` - Birth control and contraception
- `emergency-contraception` - Morning-after pill
- `std-testing` - STD testing and treatment
- `hiv-testing` - HIV services
- `gender-affirming-care` - Gender-affirming care
- `pregnancy-testing` - Pregnancy testing and planning
- `prenatal-postpartum` - Prenatal and postpartum services
- `sexual-reproductive` - Sexual and reproductive health
- `vaccines` - Vaccinations
- `wellness-preventive` - Wellness and preventive care
- `mental-health` - Mental health services

### Channel Types

- `telehealth` - Video/phone appointments
- `onsite` - In-person visits
- `ppdirect` - Planned Parenthood Direct app services

## Pagination

Large result sets are paginated. Use the `page` parameter to navigate:

```json
{
  "function": "search",
  "location": "California",
  "page": 2
}
```

The response includes `next_page` and `previous_page` indicators.

## Error Handling

All errors are returned in a consistent format:

```json
{
  "error": true,
  "message": "Description of the error"
}
```

Common errors:
- Invalid location format
- Unknown service type
- Missing required parameters

## Rate Limits

No authentication is required. The API appears to have reasonable rate limits for normal usage.