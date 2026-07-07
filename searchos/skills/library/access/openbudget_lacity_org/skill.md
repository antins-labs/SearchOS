# LA City Open Budget Access Skill

This skill retrieves budget data from the City of Los Angeles Open Budget portal
(https://openbudget.lacity.org).

## Overview

The LA City Open Budget portal is a JavaScript-heavy dashboard that visualizes the city's
operating budget. While the main site requires JavaScript execution to display data, it
provides a clean JSON API that this skill uses to extract budget information.

## Data Structure

The LA City budget is organized hierarchically:

1. **Citywide (org1)** - The entire city budget
2. **Departments (org2)** - Individual departments like Police, Fire, Recreation & Parks
3. **Programs (org3)** - Programs within each department, like "Field Forces" or "Specialized Investigation"
4. **Appropriations** - Line items within programs

## Available Functions

### get_years

Get available budget years.

```python
await execute({
    "function": "get_years",
    "budget_type": "operating"  # or "capital"
})
```

Returns a list of fiscal years with available budget data (currently 2010-2025).

### get_departments

Get all departments with their budget totals for a specific year.

```python
await execute({
    "function": "get_departments",
    "year": "2023",
    "page": 0,
    "limit": 50,
    "sort_field": "total",  # or "name"
    "sort_order": "desc"    # or "asc"
})
```

Returns department names, labels, and total budget amounts.

### get_programs

Get programs within a specific department.

```python
await execute({
    "function": "get_programs",
    "year": "2023",
    "department": "Police"
})
```

Returns programs within the specified department with their budget totals.

### get_appropriations

Get appropriations (line items) within a specific program.

```python
await execute({
    "function": "get_appropriations",
    "year": "2023",
    "department": "Police",
    "program": "Field Forces"
})
```

Returns detailed appropriations with descriptions and amounts.

### get_budget_total

Get the total budget amount for a specific level.

```python
# Citywide total
await execute({
    "function": "get_budget_total",
    "year": "2023",
    "level": "org1"
})

# Department total
await execute({
    "function": "get_budget_total",
    "year": "2023",
    "level": "org2",
    "department": "Police"
})

# Program total
await execute({
    "function": "get_budget_total",
    "year": "2023",
    "level": "org3",
    "department": "Police",
    "program": "Field Forces"
})
```

Returns the total budget amount with formatted display value.

### get_fund_sources

Get funding source breakdown for a budget level.

```python
await execute({
    "function": "get_fund_sources",
    "year": "2023",
    "level": "org1"
})
```

Returns a list of funds (e.g., "General Fund", "Special Funds") with amounts and percentages.

### get_historical

Get historical budget data across multiple years.

```python
# All departments over time
await execute({
    "function": "get_historical",
    "year": "2023",  # Reference year
    "level": "org1"
})

# Single department over time
await execute({
    "function": "get_historical",
    "year": "2023",
    "level": "org2",
    "department": "Police"
})
```

Returns budget totals for each fiscal year available, enabling trend analysis.

### get_entity_counts

Get counts of child entities at a level.

```python
await execute({
    "function": "get_entity_counts",
    "year": "2023",
    "level": "org2",
    "department": "Police"
})
```

Returns counts like the number of programs in a department or appropriations in a program.

### search_entities

Search for budget entities across departments, programs, and funds.

```python
# Search all
await execute({
    "function": "search_entities",
    "query": "police"
})

# Filter by type
await execute({
    "function": "search_entities",
    "entity_type": "org1"  # or "org2" or "fund"
})

# Filter by year
await execute({
    "function": "search_entities",
    "query": "police",
    "year": "2023"
})
```

Returns matching entities with their types and years of availability.

## Example Use Cases

### Compare department budgets

```python
# Get 2023 departments sorted by total
result = await execute({
    "function": "get_departments",
    "year": "2023",
    "sort_field": "total",
    "sort_order": "desc",
    "limit": 10
})

# Top departments
for dept in result["data"]["entities"]:
    print(f"{dept['label']}: ${dept['total']:,.0f}")
```

### Track Police budget over time

```python
# Get historical data
result = await execute({
    "function": "get_historical",
    "year": "2023",
    "level": "org2",
    "department": "Police"
})

# Show trend
entity = result["data"]["entities"][0]
for year_data in entity["values"]:
    print(f"{year_data['fiscal_year']}: ${year_data['value']:,.0f}")
```

### Find largest funding sources

```python
result = await execute({
    "function": "get_fund_sources",
    "year": "2023",
    "level": "org1"
})

for fund in result["data"]["funds"][:5]:
    print(f"{fund['fund']}: {fund['percentage']:.1f}%")
```

## Notes

- Budget years are fiscal years (July 1 - June 30)
- Amounts are in whole dollars
- Some programs may have null totals (budget not allocated or classified differently)
- The API returns mostly operating budget data; capital budget data is limited
- Department and program names must match exactly (use search_entities to find correct names)