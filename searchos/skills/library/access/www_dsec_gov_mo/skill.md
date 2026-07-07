# DSEC Macau Statistics Access Skill

Access statistical data from the **Macau Statistics and Census Service (DSEC - Direcção dos Serviços de Estatística e Censos)**.

## Overview

This skill provides direct HTTP API access to Macau's official statistical database, covering:

- **Tourism & Services**: Visitor arrivals, hotel occupancy, package tours, visitor expenditure, tourist price index, gaming sector, MICE statistics
- **Demographics**: Population statistics, census data, household budget surveys
- **National Accounts**: GDP, GNI, balance of payments
- **General Statistics**: Statistical yearbook, monthly bulletins, economic bulletins

## Available Functions

### list_categories

List all available statistical categories and their topics.

**Parameters:**
- `language` (string, optional): Language for names. Options: `en-US`, `zh-CN`, `zh-MO`, `pt-PT`. Default: `en-US`

**Example:**
```python
result = await execute({
    "function": "list_categories",
    "language": "en-US"
})
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "categories": {
      "TourismAndServices": [
        {"key": "VisitorArrivals", "name": "Visitor Arrivals"},
        {"key": "GamingSectorSurvey", "name": "Gaming Sector"},
        ...
      ],
      ...
    }
  }
}
```

---

### get_key_indicators

Get all key statistical indicators with their latest values.

**Parameters:**
- `language` (string, optional): Language for indicator names. Default: `en-US`
- `indicator_id` (integer, optional): Filter to a specific indicator ID

**Example:**
```python
result = await execute({
    "function": "get_key_indicators",
    "language": "en-US"
})
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "indicators": [
      {
        "id": 9,
        "name": "Occupancy rate of hotel establishments",
        "value": "90.2",
        "unit": "%",
        "year": 2026,
        "period_description": "Apr./2026"
      },
      {
        "id": 14,
        "name": "Tax revenue from gaming sector",
        "value": "7,652",
        "unit": "million MOP",
        "year": 2026,
        "period_description": "May/2026"
      },
      ...
    ],
    "count": 119
  }
}
```

---

### search_indicators

Search key indicators by keyword in their names.

**Parameters:**
- `query` (string, required): Search keyword
- `language` (string, optional): Language for indicator names. Default: `en-US`

**Example:**
```python
result = await execute({
    "function": "search_indicators",
    "query": "visitor"
})
```

---

### get_statistical_releases

Get publication releases for a specific statistical topic.

**Parameters:**
- `category` (string, required): Category name
  - `TourismAndServices`
  - `General`
  - `NationalAccounts`
  - `Demographic`
- `topic` (string, required): Topic key within category (e.g., `VisitorArrivals`, `GamingSectorSurvey`)
- `period_type` (string, optional): Filter by period - `Monthly`, `Quarterly`, `Yearly`
- `year` (integer, optional): Filter by year
- `language` (string, optional): Language for content. Default: `en-US`

**Example:**
```python
# Get monthly visitor arrival statistics for 2026
result = await execute({
    "function": "get_statistical_releases",
    "category": "TourismAndServices",
    "topic": "VisitorArrivals",
    "period_type": "Monthly",
    "year": 2026
})
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "topic": {
      "key": "VisitorArrivals",
      "name": "Visitor Arrivals",
      "link": "https://www.dsec.gov.mo/Statistic?id=4&guid=..."
    },
    "releases": {
      "Monthly": {
        "count": 5,
        "items": [
          {
            "release_id": 31632,
            "name": "Apr./2026",
            "year": "2026",
            "period": 4,
            "has_news": true,
            "files": [
              {
                "name": "Statistical Tables",
                "type": ".xlsx",
                "link": "https://www.dsec.gov.mo/getAttachment/..."
              }
            ]
          },
          ...
        ]
      }
    }
  }
}
```

---

### get_release_detail

Get detailed information for a specific release by its ID.

**Parameters:**
- `release_id` (integer, required): Release ID from publications list

**Example:**
```python
result = await execute({
    "function": "get_release_detail",
    "release_id": 31632
})
```

---

## Categories and Topics

### TourismAndServices
- `VisitorArrivals` - Visitor arrival statistics (monthly, quarterly)
- `PackageToursAndHotelOccupancyRate` - Hotel occupancy and package tours
- `VisitorExpenditureSurvey` - Visitor spending data
- `TouristPriceIndex` - Tourist price index
- `GamingSectorSurvey` - Gaming industry statistics
- `MICEStatistics` - Meetings, Incentives, Conferences, Exhibitions
- `TourismSatelliteAccount` - Tourism economic contribution

### NationalAccounts
- `GrossDomesticProduct` - GDP statistics
- `GrossNationalIncome` - GNI data
- `BalanceOfPayments` - Balance of payments

### Demographic
- `DemographicStatistics` - Population statistics
- `PopulationCensus` - Census results
- `HouseholdBudgetSurvey` - Household spending data

### General
- `YearbookOfStatistics` - Statistical yearbook
- `MacaoInFigures` - Key statistics overview
- `MonthlyBulletinOfStatistics` - Monthly bulletins

---

## Data Format

Most statistical data is available as downloadable Excel (`.xlsx`) or PDF files through the attachment links. Links are returned in the format:

```
https://www.dsec.gov.mo/getAttachment/{guid}/{filename}.aspx
```

---

## Language Support

The API supports four languages:
- `en-US` - English
- `zh-CN` - Simplified Chinese
- `zh-MO` - Traditional Chinese (Macau)
- `pt-PT` - Portuguese

---

## Usage Examples

### Get latest tourism indicators
```python
# Search for tourism-related indicators
result = await execute({
    "function": "search_indicators",
    "query": "visitor"
})

# Get all key indicators
result = await execute({
    "function": "get_key_indicators"
})
```

### Get gaming sector statistics
```python
result = await execute({
    "function": "get_statistical_releases",
    "category": "TourismAndServices",
    "topic": "GamingSectorSurvey",
    "period_type": "Yearly"
})
```

### Get visitor arrival monthly reports
```python
result = await execute({
    "function": "get_statistical_releases",
    "category": "TourismAndServices",
    "topic": "VisitorArrivals",
    "period_type": "Monthly",
    "year": 2026
})
```

---

## Notes

- The DSEC website provides statistical releases primarily as downloadable Excel/PDF files
- Release dates and modification timestamps are available in Unix timestamp format (milliseconds)
- The skill uses the publicly available JSON data files that power the official website
- No authentication is required for accessing the statistics API