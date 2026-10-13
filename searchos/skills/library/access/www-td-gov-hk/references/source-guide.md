# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Hong Kong Transport Department - Tunnels and Bridges

This skill retrieves toll information and details for Hong Kong's tunnels and bridges from the official Transport Department website (www.td.gov.hk).

## Features

### 1. Time-Varying Tolls (`get_time_varying_tolls`)

Retrieves the time-varying toll rates for the three major harbour crossings:
- **Western Harbour Crossing (WHC)** - 西區海底隧道
- **Cross Harbour Tunnel (CHT)** - 紅磡海底隧道
- **Eastern Harbour Crossing (EHC)** - 東區海底隧道

The tolls vary by:
- **Vehicle type**: Private cars, motorcycles, taxis, other vehicles
- **Time slot**: Peak hours, off-peak hours, normal hours, transition periods
- **Day type**: Mondays to Saturdays (excluding general holidays), Sundays and general holidays

#### Example Usage

```
# Get all time-varying tolls
function: get_time_varying_tolls

# Filter by vehicle type
function: get_time_varying_tolls
vehicle_type: Private Car

# Filter by time slot type
function: get_time_varying_tolls
time_slot: peak
```

#### Response Structure

```json
{
  "success": true,
  "data": {
    "peak_time_slots": {
      "am_peak": {"start": "07:30", "end": "10:15"},
      "pm_peak": {"start": "16:30", "end": "19:00"},
      "normal": {"start": "10:11", "end": "19:15"}
    },
    "time_varying_tolls": [
      {
        "vehicle_type": "Private Car",
        "date_type": "Mondays to Saturdays (excluding general holidays)",
        "time_slot_type": "Peak time slot",
        "whc": {"time": "08:08 - 10:14", "toll": "$60"},
        "cht_ehc": {"time": "07:48 - 10:14", "toll": "$40"}
      }
    ],
    "fixed_tolls": [
      {"vehicle_type": "Taxi", "toll": "$25"}
    ],
    "remarks": ["Additional notes about toll arrangements..."]
  }
}
```

### 2. Tunnels and Bridges List (`get_tunnels_bridges`)

Retrieves detailed information about all tunnels and bridges in Hong Kong, including:
- Name and description
- Length (in kilometers)
- Toll information (free or toll range)
- Commissioned year
- Number of lanes
- Connecting districts

#### Example Usage

```
# Get all tunnels and bridges
function: get_tunnels_bridges

# Filter by name
function: get_tunnels_bridges
name: Cross Harbour

# Filter by toll type
function: get_tunnels_bridges
toll_type: free
```

#### Response Structure

```json
{
  "success": true,
  "data": {
    "tunnels_and_bridges": [
      {
        "name": "Cross Harbour Tunnel",
        "description": "The Cross-Harbour Tunnel is a dual two-lane tunnel...",
        "length_km": 1.9,
        "toll_range": "$8 - $50",
        "commissioned": 1972,
        "lanes": "two",
        "connects": [
          {"area": "Hung Hom", "district": "Yau Tsim Mong District"},
          {"area": "Causeway Bay", "district": "Wan Chai District"}
        ]
      }
    ],
    "total_count": 25
  }
}
```

### 3. Search Tunnels (`search_tunnels`)

Search for tunnels and bridges by name or description.

#### Example Usage

```
function: search_tunnels
query: Lion Rock
```

## Data Sources

- Time-varying tolls: https://www.td.gov.hk/en/transport_in_hong_kong/tunnels_and_bridges_n/tvt/index.html
- Tunnels and bridges: https://www.td.gov.hk/en/transport_in_hong_kong/tunnels_and_bridges_n/location_map/index.html

## Notes

- All toll amounts are in Hong Kong Dollars (HKD)
- Time-varying tolls apply to private cars and motorcycles only
- Taxis and other vehicles have fixed tolls
- Transition time slots have variable tolls that change incrementally
- The skill parses structured data from official government tables
- Some tunnels are toll-free (e.g., Central - Wan Chai Bypass, Kai Tak Tunnel)
