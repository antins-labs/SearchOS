# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# gunrf.ru Weapon Specifications

This skill fetches weapon specifications from gunrf.ru English-language pages.

## Functions

### get_weapon_specs

Fetches detailed specifications for a specific weapon from its gunrf.ru page.

**Parameters:**
- `url` (required): The weapon page URL on gunrf.ru (must end with `_eng.html`)

**Returns:**
- `weapon_name`: Name/title of the weapon
- `specifications`: Dictionary of specification key-value pairs (caliber, weight, rate of fire, etc.)
- `images`: List of weapon images with URLs and alt text
- `description`: Brief description of the weapon

**Example:**
```json
{
  "function": "get_weapon_specs",
  "url": "https://gunrf.ru/rg_avtomat_aks-74u_eng.html"
}
```

**Sample Output:**
```json
{
  "weapon_name": "AKS-74U assault rifle",
  "specifications": {
    "Caliber": "5.45 mm",
    "Cartridge": "5.45×39 (Mod. 1974)",
    "Weapon weight w/o cartridges": "2.485 kg",
    "Barrel length": "206.5 mm",
    "Bullet muzzle velocity": "735 m/sec",
    "Rate of fire": "700 rds/min",
    "Magazine capacity": "30 rds"
  },
  "images": [...],
  "success": true
}
```

### search_weapons

Discovers weapon pages by crawling links from known weapon pages.

**Parameters:**
- `category` (optional): Weapon category to filter (default: "avtomat" for assault rifles)

**Returns:**
- `weapons`: List of discovered weapons with name and URL
- `count`: Total number of weapons found

**Example:**
```json
{
  "function": "search_weapons",
  "category": "avtomat"
}
```

## Notes

- The site uses paragraph text rather than HTML tables for specifications
- Some pages contain specifications for multiple weapon variants (e.g., AK-107/AK-108/AK-109)
- All URLs must be English pages (ending in `_eng.html`)
- The site is in Russian but English pages are available via the `_eng` suffix
