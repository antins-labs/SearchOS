# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# GDACS Disaster Alert Access Skill

This skill retrieves disaster alert information from GDACS (Global Disaster Alert and Coordination System), a cooperation framework between the United Nations, the European Commission, and disaster managers worldwide.

## Features

- **Event Reports**: Comprehensive data for specific disaster events including CAP alerts, GeoJSON, and RSS feeds
- **Current Alerts**: Real-time list of active disasters worldwide
- **Event Search**: Filter events by type, alert level, or keyword
- **CAP Alerts**: Standard Common Alerting Protocol XML data
- **Geographic Data**: GeoJSON format for mapping applications

## Supported Event Types

| Code | Type |
|------|------|
| EQ | Earthquake |
| FL | Flood |
| TC | Tropical Cyclone |
| VO | Volcano |
| DR | Drought |
| WF | Wildfire |

## Alert Levels

- **Green**: Low humanitarian impact
- **Orange**: Medium humanitarian impact  
- **Red**: High humanitarian impact

## Usage Examples

### Get Current Earthquake Alerts
```json
{
  "function": "get_current_alerts",
  "event_type": "EQ",
  "limit": 10
}
```

### Get Specific Event Report
```json
{
  "function": "get_event_report",
  "event_type": "EQ",
  "event_id": "1500799"
}
```

### Search for Events
```json
{
  "function": "search_events",
  "query": "Indonesia",
  "event_type": "EQ",
  "alert_level": "Green"
}
```

### Get CAP Alert
```json
{
  "function": "get_cap_alert",
  "event_type": "EQ",
  "event_id": "1500799"
}
```

### Get GeoJSON Data
```json
{
  "function": "get_geojson",
  "event_type": "EQ",
  "event_id": "1500799",
  "episode_id": "1661013"
}
```

## Data Sources

The skill uses multiple GDACS data endpoints:

- **RSS Feed**: `https://www.gdacs.org/xml/rss.xml` - Current alerts
- **CAP XML**: `https://www.gdacs.org/contentdata/resources/{type}/{id}/cap_{id}.xml` - Alert details
- **GeoJSON**: `https://www.gdacs.org/contentdata/resources/{type}/{id}/geojson_{id}_{episode}.geojson` - Geographic data
- **Event RSS**: `https://www.gdacs.org/contentdata/resources/{type}/{id}/rss_{id}_{episode}.xml` - Event history

## Returned Data

### Event Report
Returns comprehensive event data including:
- CAP alert information (headline, description, severity, urgency)
- Event parameters (magnitude, depth, coordinates, country)
- Population exposure data
- Vulnerability scores
- Alert timeline

### CAP Alert
Standard CAP format including:
- Alert identifier and sender
- Event category and type
- Severity, urgency, certainty
- Affected areas with polygons
- Parameter values (event ID, episode ID, country, etc.)

### GeoJSON
Geographic features including:
- Event centroid point
- Impact radius circle polygon
- Affected area polygons
- Metadata (alert level, coordinates, country, etc.)

## Notes

- Event IDs can be found by searching the current alerts feed
- Episode IDs represent specific updates/events within a disaster sequence
- The main GDACS website has a cookie consent wall that doesn't affect the data APIs
- Data is updated in near real-time for active events
