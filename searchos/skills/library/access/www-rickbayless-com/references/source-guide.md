# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Rick Bayless Recipe Skill

This skill extracts Mexican recipes from Rick Bayless's official website at www.rickbayless.com.

## Features

- **get_recipe**: Fetch complete recipe details including:
  - Recipe title
  - Description/story
  - Ingredient list with structured quantity, unit, and notes
  - Step-by-step instructions
  - Recipe image
  - Category/classification

- **list_recipes**: Get a list of available recipes from the recipe index

- **search_recipes**: Search for recipes by keyword (e.g., "tacos", "salsa", "chicken")

## Usage Examples

### Get a specific recipe
```
function: get_recipe
url: https://www.rickbayless.com/recipe/gaspacho-moreliano/
```

### List available recipes
```
function: list_recipes
```

### Search for recipes
```
function: search_recipes
query: tacos
```

## Data Structure

### Recipe Response
```json
{
  "title": "Gaspacho Moreliano",
  "description": "There is a stretch of Quintana Roo street...",
  "image_url": "https://www.rickbayless.com/wp-content/uploads/...",
  "category": "",
  "ingredients": [
    {
      "quantity": "2",
      "unit": "large ripe",
      "name": "",
      "notes": "mangos (about 1 pound total), peeled...",
      "full_text": "2large ripemangos (about 1 pound total)..."
    }
  ],
  "instructions": [
    "Make the Gaspacho Moreliano. Combine the mango...",
    "Layering and serving the dish. Divide..."
  ],
  "ingredient_count": 10,
  "instruction_count": 2,
  "url": "https://www.rickbayless.com/recipe/gaspacho-moreliano/"
}
```

### Recipe List Response
```json
{
  "recipes": [
    {
      "url": "https://www.rickbayless.com/recipe/huevos-rancheros/",
      "title_hint": "Huevos Rancheros"
    }
  ],
  "count": 16,
  "source_url": "https://www.rickbayless.com/recipe/"
}
```

## Error Handling

The skill returns structured error responses:
- `NOT_FOUND`: Recipe URL returned 404
- `FETCH_ERROR`: Failed to fetch page (non-200 status)
- `PARSE_ERROR`: Could not parse recipe data from page
- `MISSING_PARAM`: Required parameter not provided
- `INVALID_URL`: URL is not a valid rickbayless.com recipe URL
- `UNKNOWN_FUNCTION`: Unknown function name provided

## Notes

- The site uses lazy-loaded images; the skill extracts the actual image URL from `data-src` attributes or Open Graph metadata
- Ingredient parsing attempts to separate quantity, unit, and notes where possible
- All recipes include full ingredient text in the `full_text` field for fallback
