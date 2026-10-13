# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Noff.gg Clash Royale Card Stats

This skill fetches detailed card statistics from [noff.gg](https://www.noff.gg/clash-royale), a Clash Royale stats and deck building website.

## Features

- **Comprehensive Card Data**: Retrieves all available stats including:
  - Basic info: name, rarity, type, arena unlock level
  - Combat stats: hitpoints, damage, hit speed, range, speed, targets
  - Meta stats: win rate, pick rate, trend analysis
  - Flavor text description

- **Multi-Entity Support**: Correctly handles cards with multiple entities (e.g., Rascals with Rascal Boy and Rascal Girl, Goblin Barrel with spawned Goblins)

- **All Card Types**: Works with troops, spells, and buildings

## Usage

### Get Card Stats

```
function: get_card
card_name: mega-knight
```

Returns detailed statistics for the specified card.

### Card Name Format

Use lowercase with hyphens for spaces:
- `mega-knight` (Mega Knight)
- `pekka` (P.E.K.K.A)
- `goblin-barrel` (Goblin Barrel)
- `skeleton-army` (Skeleton Army)
- `rascals` (Rascals)

## Example Output

### Single Entity Card (Mega Knight)
```json
{
  "name": "Mega Knight",
  "rarity": "Legendary",
  "type": "Troop",
  "arena": 7,
  "stats": {
    "Area Damage": "222",
    "Jump Damage": "444",
    "Spawn Damage": "355",
    "Damage Per Second": "130",
    "Hitpoints": "3300",
    "Jump Range": "3.5-5",
    "Hit Speed": "1.7sec",
    "Targets": "Ground",
    "Speed": "Medium",
    "Range": "Melee: Medium"
  },
  "winRate": "40.2%",
  "pickRate": "7.2%"
}
```

### Multi-Entity Card (Rascals)
```json
{
  "name": "Rascals",
  "rarity": "Common",
  "type": "Troop",
  "arena": 13,
  "description": "Spawns a mischievous trio of Rascals!...",
  "level": 1,
  "entities": {
    "Rascal Boy": {
      "Hitpoints": "716",
      "Damage": "85",
      "Hit Speed": "1.5sec",
      "Speed": "Medium",
      "Range": "Melee: Short",
      "Targets": "Ground",
      "count": 1
    },
    "Rascal Girl": {
      "Hitpoints": "102",
      "Damage": "52",
      "Hit Speed": "1sec",
      "Speed": "Medium",
      "Range": "5",
      "Targets": "Air & Ground",
      "count": 2
    }
  },
  "winRate": "50.3%",
  "pickRate": "6.8%",
  "trend": "below average"
}
```

## Notes

- Stats are shown at Level 1 (tournament standard may differ)
- Win rate and pick rate are based on recent match data
- The skill uses browser automation to render JavaScript content
- All stats include unit-specific attributes where applicable
