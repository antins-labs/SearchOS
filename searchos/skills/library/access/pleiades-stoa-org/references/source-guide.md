# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Pleiades Gazetteer Access Skill

This skill fetches structured data about ancient places from the **Pleiades gazetteer** (pleiades.stoa.org), a community-built scholarly resource for ancient geography covering the Mediterranean and Near Eastern worlds.

## About Pleiades

Pleiades is a historical gazetteer that provides stable identifiers, geographic coordinates, and scholarly metadata for ancient places. It's widely used in digital humanities, archaeology, and classical studies.

## Functions

### get_place

Retrieve comprehensive information about a specific ancient place.

**Parameters:**
- `place_id` (required): The numeric Pleiades place ID

**Returns:**
- `id`: Place ID
- `title`: Place name
- `description`: Textual description
- `place_types`: Categories (e.g., "pyramid", "settlement", "temple")
- `subjects`: Subject keywords
- `repr_point`: Representative coordinates [longitude, latitude]
- `bbox`: Bounding box [min_lon, min_lat, max_lon, max_lat]
- `features`: GeoJSON Feature collection with geometry
- `names`: Ancient and modern names with attestations
- `locations`: Geographic locations with temporal data
- `connections`: Links to related places
- `references`: Bibliographic and external references (Wikipedia, Wikidata, etc.)
- `creators`/`contributors`: Scholarly attribution
- `raw`: Complete original JSON data

**Example:**
```json
{
  "function": "get_place",
  "place_id": "154462177"
}
```

This returns data about "Sekhemkhet's Step Pyramid" including:
- Coordinates: [31.2136, 29.8662]
- Place type: pyramid
- Names: "Buried Pyramid"
- Connection to: Saqqara (place 796289136)
- References to Wikipedia and Wikidata

### list_place_types

List all available place type categories in the Pleiades vocabulary.

**Parameters:**
- `include_hidden` (optional): Include deprecated/hidden types (default: false)

**Returns:**
- `place_types`: Array of place types with id, title, description
- `count`: Total number of types

Place types include: abbey, acropolis, agora, amphitheatre, aqueduct, arch, basilica, bridge, cemetery, sanctuary, temple, theater, villa, and many more.

### list_time_periods

List all temporal periods used in Pleiades attestations.

**Returns:**
- `time_periods`: Array of periods with id, title, start/end dates
- `count`: Total number of periods

Periods range from prehistoric through modern times, with focus on ancient Mediterranean chronology.

### list_relationship_types

List all connection/relationship types between places.

**Returns:**
- `relationship_types`: Array of relationship types
- `count`: Total number of types

Examples: "at" (located at), "near" (nearby), "contains" (spatial containment)

## Data Structure Notes

### Coordinates
All coordinates are in WGS84 (EPSG:4326) format as [longitude, latitude].

### Temporal Data
- `start` and `end` are year numbers (negative for BCE)
- Example: start: -2670, end: -2168 (Old Kingdom Egypt)

### Attestations
Names and locations may have multiple attestations with:
- `timePeriod`: Temporal context
- `confidence`: How certain the attribution is

## Example Place IDs

- `154462177` - Sekhemkhet's Step Pyramid (Egypt)
- `347826778` - Headless Pyramid (Egypt)
- `796289136` - Saqqara (Egypt)
- `579885` - Athens (Greece)
- `423025` - Rome (Italy)

## API Notes

The skill uses the Pleiades JSON API:
- Place data: `https://pleiades.stoa.org/places/{id}/json`
- Vocabularies: `https://pleiades.stoa.org/vocabularies/{vocabulary}`

All data is licensed under Creative Commons Attribution 3.0 (CC-BY).

## Use Cases

1. **Geographic research**: Get precise coordinates for ancient sites
2. **Linked data**: Follow connections to related places
3. **Historical analysis**: Access temporal attestations for places
4. **Data enrichment**: Link your data to stable Pleiades URIs
5. **Vocabulary lookup**: Browse standardized place types and time periods
