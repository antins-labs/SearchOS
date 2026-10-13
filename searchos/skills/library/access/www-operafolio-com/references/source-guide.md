# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# OperaFolio Access Skill

This skill extracts structured opera data from [OperaFolio.com](http://www.operafolio.com), a comprehensive mobile opera guide with ratings and detailed information.

## Available Functions

### get_composer_operas
Get a complete list of operas by a specific composer.

**Parameters:**
- `composer` (required): Composer name, e.g., "Giuseppe Verdi" or "Giuseppe_Verdi"

**Returns:**
- Composer information (name, years, country, rating)
- List of operas with details: name, acts, language, librettist, first performance, rating

**Example:**
```json
{
  "function": "get_composer_operas",
  "composer": "Giuseppe Verdi"
}
```

### get_opera_details
Get detailed information about a specific opera.

**Parameters:**
- `opera` (required): Opera name, e.g., "Rigoletto" or "La Traviata"

**Returns:**
- Opera metadata (name, year, country, genre, rating)
- Composer and librettist information
- First performance venue and date
- Synopsis (full plot summary)
- List of arias with character/voice type
- External links (libretto, Wikipedia, upcoming performances)
- Background facts

**Example:**
```json
{
  "function": "get_opera_details",
  "opera": "Rigoletto"
}
```

### get_composers
Get a list of all composers in the database.

**Returns:**
- List of composers with name, birth/death years, and rating (1-3 stars)

### get_operas
Get a list of featured/popular operas.

**Returns:**
- List of operas with name, composer, country, year, genre, and rating

### search_operas
Search for operas by name.

**Parameters:**
- `query` (required): Search term

**Returns:**
- Matching operas with basic information

**Example:**
```json
{
  "function": "search_operas",
  "query": "traviata"
}
```

### get_famous_arias
Get a list of famous arias from the database.

**Returns:**
- List of arias with name, opera, composer, and rating

## Data Fields

### Star Ratings
- 3 stars (★★★): Masterpiece / Essential
- 2 stars (★★): Notable / Important
- 1 star (★): Worth knowing

### Country Codes
Standard two-letter country codes (IT=Italy, DE=Germany, FR=France, etc.)

## Notes

- The site uses a simple URL parameter structure with underscores for spaces
- Opera names in URLs are normalized (spaces replaced with underscores)
- Some alternate versions of operas may not have dedicated pages
- External libretto links point to various third-party sources
