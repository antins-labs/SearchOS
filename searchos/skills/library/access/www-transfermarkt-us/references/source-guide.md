# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Transfermarkt Access Skill

## Overview

This skill provides access to Transfermarkt (www.transfermarkt.us) football data, including:
- **Fixtures**: Match schedules and results for clubs
- **Squad**: Player rosters and squad information
- **Market Values**: Player market valuations

## Important Limitation

⚠️ **CRITICAL: This site is currently blocked by anti-bot protection.**

Transfermarkt uses AWS WAF (Web Application Firewall) with JavaScript challenge/CAPTCHA verification that blocks automated access. All attempts to access the site via:
- Direct HTTP requests
- Playwright browser automation
- Various stealth techniques

Result in a 405 status code with a "Human Verification" challenge page.

## Available Functions

### get_fixtures
Retrieve fixture/match schedule for a club and season.

**Parameters:**
- `club_id` (required): Transfermarkt club ID (e.g., "583" for PSG)
- `season_id` (optional): Season ID, default "2024"
- `club_name` (optional): Club name slug for URL

**Example URL:** `https://www.transfermarkt.us/fc-paris-saint-germain/spielplan/verein/583/saison_id/2024`

### get_squad
Retrieve squad information for a club.

**Parameters:**
- `club_id` (required): Transfermarkt club ID
- `club_name` (optional): Club name slug for URL

**Example URL:** `https://www.transfermarkt.us/fc-paris-saint-germain/kader/verein/583`

### get_player_market_values
Retrieve player market values for a club.

**Parameters:**
- `club_id` (required): Transfermarkt club ID
- `club_name` (optional): Club name slug for URL

**Example URL:** `https://www.transfermarkt.us/fc-paris-saint-germain/marktwertanalyse/verein/583`

## Club ID Reference

| Club | Club ID | Club Name Slug |
|------|---------|----------------|
| Paris Saint-Germain | 583 | fc-paris-saint-germain |
| VfB Stuttgart | 79 | vfb-stuttgart |
| Real Madrid | 418 | real-madrid |
| FC Barcelona | 131 | fc-barcelona |
| Bayern Munich | 27 | fc-bayern-munchen |
| Manchester City | 281 | manchester-city |
| Liverpool | 31 | fc-liverpool |

## Response Structure

### Successful Response (when protection is bypassed)
```json
{
  "success": true,
  "blocked": false,
  "status": 200,
  "url": "https://www.transfermarkt.us/...",
  "data_type": "fixtures",
  "data": {
    "fixtures": [...],
    "count": 10
  }
}
```

### Blocked Response (current behavior)
```json
{
  "success": false,
  "blocked": true,
  "error": "Access blocked by Transfermarkt's anti-bot protection (AWS WAF)...",
  "status": 405,
  "title": "Human Verification",
  "url": "https://www.transfermarkt.us/..."
}
```

## Technical Details

### Anti-Bot Protection
- **Type**: AWS WAF with JavaScript challenge
- **Detection**: Browser automation detection via webdriver properties
- **Response**: 405 Method Not Allowed with verification page
- **Challenge**: Interactive CAPTCHA requiring human interaction

### Attempted Bypasses
The following techniques were attempted without success:
1. Standard Playwright browser automation
2. Stealth scripts to hide webdriver properties
3. Realistic browser headers and fingerprints
4. Mobile user agents
5. Session establishment via homepage visit
6. Mouse movement simulation
7. Alternative domains (.com, .de, .co.uk)

### Future Possibilities
- If Transfermarkt provides an official API
- If the site's protection policy changes
- If legitimate session cookies/tokens become available

## Usage Examples

```python
# Get PSG fixtures for 2024/25 season
result = await execute({
    "function": "get_fixtures",
    "club_id": "583",
    "season_id": "2024",
    "club_name": "fc-paris-saint-germain"
}, ctx)

# Get VfB Stuttgart squad
result = await execute({
    "function": "get_squad",
    "club_id": "79",
    "club_name": "vfb-stuttgart"
}, ctx)

# Get Real Madrid player market values
result = await execute({
    "function": "get_player_market_values",
    "club_id": "418",
    "club_name": "real-madrid"
}, ctx)
```

## Data Extraction Logic

The skill includes extraction logic for when access becomes available:

### Fixtures
- Parses `tr.begegnungZeile` rows
- Extracts date, opponent, and result
- Returns structured fixture list

### Squad
- Parses player rows from squad table
- Extracts player name, position, and market value
- Returns player list with details

### Market Values
- Parses market value table rows
- Extracts player name and current valuation
- Returns value list

## Error Handling

The skill returns structured error responses:
- `success`: Boolean indicating operation success
- `blocked`: Boolean indicating if blocked by anti-bot protection
- `error`: Human-readable error message
- `status`: HTTP status code (405 for blocked requests)
