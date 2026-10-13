# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# FilmAffinity Awards History Access Skill

This skill retrieves award history data from FilmAffinity (www.filmaffinity.com), a comprehensive movie database with detailed award information.

## Features

- **get_award_history**: Fetch all winners for a specific award category
  - Returns year-by-year winners with movie titles
  - Includes nomination and award counts for each winning film
  - Links to person and movie pages on FilmAffinity

- **get_categories**: List all available award categories for a festival
  - Discover all categories within a film festival (e.g., Berlin, Cannes, Oscars)
  - Get category IDs for use with get_award_history

## Usage Examples

### Get Award History

```json
{
  "function": "get_award_history",
  "category_id": "berlin_best_actor"
}
```

Returns:
- Category title and URL
- Statistics (total years, winners count)
- Year-by-year data with:
  - Winner names and FilmAffinity IDs
  - Movie titles and IDs
  - Nomination and award counts

### List Available Categories

```json
{
  "function": "get_categories",
  "category_id": "berlin_best_actor"
}
```

Returns all categories available for the Berlin Film Festival.

## Category ID Examples

**Berlin Film Festival:**
- `berlin_golden_bear` - Golden Bear (Best Picture)
- `berlin_best_actor` - Silver Bear Best Actor
- `berlin_best_actress` - Silver Bear Best Actress
- `berlin_best_director` - Silver Bear Best Director
- `berlin_best_screenplay` - Silver Bear Best Screenplay

**Other Festivals:**
- `oscars_best_picture`, `oscars_best_actor`, `oscars_best_actress`
- `cannes_golden_palm`, `cannes_best_actor`
- `venice_golden_lion`, `venice_best_actor`

Use `get_categories` to discover the full list of available categories.

## Data Structure

Each winner entry includes:
- `name`: Winner's name
- `person_id`: FilmAffinity person ID
- `person_url`: Link to person's FilmAffinity page
- `movie`: Movie title
- `movie_id`: FilmAffinity movie ID
- `movie_url`: Link to movie's award page
- `nominations`: Total nominations for the film at this festival
- `awards`: Total awards won by the film at this festival

## Notes

- The site requires JavaScript rendering, so Playwright is used for access
- Some years may have multiple winners (ties)
- Future years are included but marked as empty
- The site is in English; category names may vary by language setting
