# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# WorldData.info Volcano Data Access Skill

This skill retrieves volcanic activity statistics and volcano information from WorldData.info, a comprehensive database of geographical and statistical data.

## Features

### 1. Country-Specific Volcano Data (`get_country_volcanoes`)

Retrieves complete volcano inventory and eruption history for a specific country.

**Returns:**
- Summary statistics (total volcanoes, active volcanoes)
- Complete list of volcanoes with status, last eruption date, and elevation
- Historical eruption records with dates, VEI (Volcanic Explosivity Index), deaths, and damage

**Example countries:** Chile, Ecuador, Colombia, Japan, Indonesia, Italy, Iceland, USA, etc.

### 2. Global Strongest Eruptions (`get_global_eruptions`)

Retrieves the most powerful volcanic eruptions recorded worldwide, ranked by VEI.

**Returns:**
- Date of eruption
- Country
- Volcano name
- VEI (Volcanic Explosivity Index, scale 0-7)
- Death toll
- Total damage

### 3. Latest Volcanic Activity (`get_latest_activity`)

Retrieves recent volcanic activity reports from around the world.

**Returns:**
- Date of activity
- Country
- Volcano name
- Warning level (if available)
- Ash cloud height

## Usage Examples

### Get volcano data for Chile

```json
{
  "function": "get_country_volcanoes",
  "country": "chile",
  "region": "america"
}
```

### Get volcano data for Japan (region auto-detected)

```json
{
  "function": "get_country_volcanoes",
  "country": "japan"
}
```

### Get top 10 strongest eruptions worldwide

```json
{
  "function": "get_global_eruptions",
  "limit": 10
}
```

### Get latest volcanic activity

```json
{
  "function": "get_latest_activity",
  "limit": 20
}
```

## Data Fields

### Volcano Record
- `name`: Volcano name
- `status`: Activity status (Active, Solfatara stage, Potentially active, etc.)
- `last_eruption`: Date of last known eruption (MM/DD/YYYY format)
- `elevation`: Summit elevation in meters

### Eruption Record
- `date`: Eruption date (MM/DD/YYYY or year)
- `volcano`: Volcano name
- `vei`: Volcanic Explosivity Index (0-7)
- `deaths`: Number of fatalities
- `damage`: Total damage (if available)

### Latest Activity Record
- `date`: Activity date
- `country`: Country name
- `volcano`: Volcano name
- `warning_level`: Alert level (Red, Orange, etc.)
- `ash_clouds`: Ash cloud height in feet

## Notes

- The VEI (Volcanic Explosivity Index) ranges from 0 (effusive) to 7 (super-colossal)
- VEI 7 eruptions are extremely rare (e.g., Tambora 1815)
- Region parameter is optional; the skill will try common regions automatically
- Country names can be provided in various formats (e.g., "Costa Rica", "costa-rica", "usa")
