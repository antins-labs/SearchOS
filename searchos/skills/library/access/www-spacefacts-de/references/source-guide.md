# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# SpaceFacts Data Extractor

Extracts structured tabular data from [www.spacefacts.de](http://www.spacefacts.de), a comprehensive database of space mission records, astronaut information, and spaceflight statistics.

## Available Functions

### `list_available_pages`
Lists all available data pages with their descriptions.

### `get_iss_commanders`
Retrieves all International Space Station (ISS) commanders with:
- Mission designation (ISS-01, ISS-02, etc.)
- Commander name
- Start and end dates
- Mission duration

Example:
```python
execute({"function": "get_iss_commanders"})
```

Returns:
```json
{
  "commanders": [
    {
      "mission": "ISS-01",
      "commander": "William M. Shepherd",
      "start_date": "02.11.2000",
      "end_date": "19.03.2001",
      "duration": "137 days"
    },
    ...
  ],
  "count": 83,
  "title": "ISS Commanders"
}
```

### `get_time_in_space`
Retrieves astronauts and cosmonauts sorted by total time spent in space. Each record includes:
- Full name (surname, given names)
- Nationality
- Number of flights
- Mission list
- Time in space (days, hours, minutes)
- Status (active/retired with date)

Parameters:
- `limit` (optional): Maximum number of records to return

Example:
```python
execute({"function": "get_time_in_space", "limit": 10})
```

### `get_active_astronauts`
Retrieves currently active astronauts and cosmonauts with:
- Full name
- Nationality
- Selection date
- Completed flights

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_by_first_mission`
Retrieves all astronauts and cosmonauts sorted by their first mission date, starting from Yuri Gagarin. Each record includes:
- Rank order
- Full name
- First mission date
- Nationality
- Number of flights
- Mission list

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_deceased`
Retrieves deceased astronauts and cosmonauts.

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_international`
Retrieves international space travelers (non-US/non-Soviet/Russian).

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_taikonauts`
Retrieves Chinese astronauts (taikonauts/yuhangyuans).

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_relocations`
Retrieves records of manned spacecraft relocations.

Parameters:
- `limit` (optional): Maximum number of records to return

### `get_all_alphabetical`
Retrieves all astronauts and cosmonauts who have flown in space, sorted alphabetically.

Parameters:
- `limit` (optional): Maximum number of records to return

## Data Source

Data is extracted from www.spacefacts.de, a German website maintained by space enthusiasts that provides comprehensive, well-structured data on:
- All manned spaceflights
- Astronaut and cosmonaut biographies
- ISS expedition records
- Space records and statistics

The site is regularly updated with the latest mission information.

## Notes

- All dates are in DD.MM.YYYY format as used on the source site
- Time in space is provided in days, hours, and minutes
- The data includes both professional astronauts/cosmonauts and space tourists
- Status field indicates if an astronaut is currently active or retired (with retirement date)
