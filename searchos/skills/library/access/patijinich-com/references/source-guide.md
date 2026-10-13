# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Pati Jinich Recipe Extractor

Extract structured recipe data from [Pati Jinich](https://patijinich.com), the official website of Pati Jinich, host of the PBS series "Pati's Mexican Table". The site features over 700 authentic Mexican recipes with detailed ingredients, instructions, and cultural context.

## Features

- **Recipe Extraction**: Get complete recipe details including ingredients, instructions, timing, servings, ratings, and more
- **Search**: Search recipes by keyword
- **Browse**: List recipes with pagination and filtering by cuisine or course
- **Taxonomies**: Access available cuisines (Mexican, American, etc.) and courses (Breakfast, Dessert, Main Course, etc.)

## Available Functions

### get_recipe
Extract a single recipe from a patijinich.com URL.

**Parameters:**
- `url` (required): The recipe page URL

**Example:**
```json
{
  "function": "get_recipe",
  "url": "https://patijinich.com/morelia-style-gazpacho-salad/"
}
```

### get_recipe_by_id
Get a recipe by its WPRM (WordPress Recipe Maker) ID.

**Parameters:**
- `recipe_id` (required): The WPRM recipe ID

**Example:**
```json
{
  "function": "get_recipe_by_id",
  "recipe_id": 37910
}
```

### search_recipes
Search recipes by keyword.

**Parameters:**
- `query` (required): Search term
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page, max 50 (default: 10)

**Example:**
```json
{
  "function": "search_recipes",
  "query": "tacos",
  "per_page": 20
}
```

### list_recipes
List recipes with pagination and optional filtering.

**Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page, max 50 (default: 10)
- `cuisine` (optional): Filter by cuisine (e.g., "Mexican")
- `course` (optional): Filter by course (e.g., "Dessert", "Breakfast")
- `keyword` (optional): Filter by keyword tag

**Example:**
```json
{
  "function": "list_recipes",
  "per_page": 20,
  "cuisine": "Mexican",
  "course": "Main Course"
}
```

### list_cuisines
List all available cuisine types for filtering.

**Example:**
```json
{
  "function": "list_cuisines"
}
```

### list_courses
List all available course types for filtering.

**Example:**
```json
{
  "function": "list_courses"
}
```

## Recipe Data Structure

Each recipe returns structured data including:

```json
{
  "name": "Morelia-Style Fruit Salad",
  "description": "A refreshing Mexican fruit salad...",
  "yield": "6 servings",
  "servings": "6 servings",
  "prep_time": {
    "minutes": 15,
    "readable": "15 minutes"
  },
  "cook_time": {
    "minutes": 10,
    "readable": "10 minutes"
  },
  "total_time": {
    "minutes": 25,
    "readable": "25 minutes"
  },
  "cuisine": "Mexican",
  "category": "Antojos",
  "keywords": ["fruit", "jicama", "mango", "lime"],
  "ingredients": [
    "2 cups peeled and diced ripe mango",
    "2 cups peeled and diced pineapple",
    "..."
  ],
  "instructions": [
    {
      "name": "To make individual gazpachos:",
      "steps": [
        "In a cup, add a layer of mango, pineapple, jícama...",
        "..."
      ]
    }
  ],
  "rating": {
    "average": 4.15,
    "count": 7
  },
  "image": "https://patijinich.com/.../image.jpg",
  "url": "https://patijinich.com/morelia-style-gazpacho-salad/",
  "author": "Pati Jinich",
  "source": "json-ld"
}
```

## Data Sources

The skill extracts recipe data from multiple sources:

1. **JSON-LD Structured Data**: Primary source for individual recipe pages, using Schema.org Recipe format
2. **WPRM REST API**: WordPress Recipe Maker plugin API for listing and searching recipes
3. **HTML Parsing**: Fallback for extracting recipe data when other sources are unavailable

## Notes

- The site contains over 700 Mexican recipes
- Recipes include cultural context from Pati's PBS show and cookbooks
- Cuisine types include Mexican, American, Chinese, French, Israeli, and more
- Course types include Breakfast, Lunch, Dinner, Dessert, Appetizer, Antojos, and more
- Most recipes include ratings from site visitors
