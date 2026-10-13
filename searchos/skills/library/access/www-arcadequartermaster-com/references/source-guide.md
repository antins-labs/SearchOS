# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Arcade Quartermaster KOF Boss Data

This skill fetches King of Fighters boss character data from arcadequartermaster.com, including character profiles and move lists.

## Supported Games

- **KOF 2000** - Boss characters: Kula, Zero, plus strikers (Candy Diamond, Foxy, Rugal)
- **KOF 2001** - Boss characters: Zero (Original), Igniz
- **KOF 2003** - Boss characters: Kusanagi, Maki, Adelheid Bernstein, Mukai

## Available Functions

### fetch_boss_page

Fetches character data from a specific KOF boss page URL.

**Parameters:**
- `url` (required): The URL to fetch, must be from arcadequartermaster.com

**Example:**
```json
{
  "function": "fetch_boss_page",
  "url": "https://www.arcadequartermaster.com/kof01_ceo.html"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "url": "https://www.arcadequartermaster.com/kof01_ceo.html",
    "title": "THE KING OF FIGHTERS 2001 || BOSS CHARACTERS || ZERO & IGNIZ",
    "characters": [
      {
        "name": "Zero (Original)",
        "profile": {
          "nationality": "North Pole",
          "height_weight": "193 cm / 88 kg",
          "blood_type": "Type O",
          "hobby": "Raising children",
          "treasures": "The entire NESTS Cartel",
          "most_hated": "Nothing",
          "forte_in_sports": "Scuba diving"
        },
        "moves": [
          {
            "name": "LUCIFER LASHER",
            "input": "Hold A, then..."
          }
        ]
      }
    ]
  }
}
```

### fetch_all_pages

Fetches data from all known KOF boss pages in a single call.

**Example:**
```json
{
  "function": "fetch_all_pages"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "kof01_ceo": {
      "url": "https://www.arcadequartermaster.com/kof01_ceo.html",
      "title": "...",
      "characters": [...]
    },
    "kof03_bosses": {...},
    "kof00_nests": {...}
  }
}
```

## Data Extracted

Each character includes:

### Profile Fields
- **name**: Character name
- **mode_of_combat**: Fighting style
- **nationality**: Character's nationality
- **birthdate**: Character's birth date
- **height_weight**: Height and weight measurements
- **blood_type**: Blood type
- **hobby**: Character's hobbies
- **favorite_food**: Favorite foods
- **treasures**: Personal treasures
- **most_hated**: Things the character hates
- **forte_in_sports**: Sports they excel at

### Move Data
- **name**: Move name (in ALL CAPS)
- **input**: Input commands for the move (directions, buttons)

### Stages (KOF 2003)
Some pages also include stage/background information with location names.

## Notes

- The site uses old-school HTML table layouts which can make parsing challenging
- Move inputs may contain directional arrow references (displayed as images on the original site)
- Some profile fields may be "Unknown" for certain characters
- The parser handles multiple HTML patterns across different KOF game pages
