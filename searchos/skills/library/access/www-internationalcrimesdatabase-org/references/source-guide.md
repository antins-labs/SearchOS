# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# International Crimes Database (ICD) Access Skill

This skill provides structured access to case records from the International Crimes Database (ICD), maintained by the Asser Institute. The database contains international criminal case law from various tribunals and courts worldwide.

## Available Functions

### get_case
Retrieve detailed information about a specific case.

**Parameters:**
- `case_id` (string): The numeric case ID, e.g., "147"
- `url` (string, optional): Full or relative case URL

**Example:**
```json
{
  "function": "get_case",
  "case_id": "147"
}
```

**Returns:**
- `case_id`: The case identifier
- `title`: Full case title
- `url`: Case URL
- `metadata`: Structured case data including:
  - Court
  - Case number
  - Decision title
  - Decision date
  - Parties (list with names and roles)
  - Categories (e.g., "Genocide", "Crimes against humanity")
  - Keywords
  - Links (to official documents)
- `sections`: Detailed content sections such as:
  - Summary
  - Procedural history
  - Legally relevant facts
  - Core legal questions
  - Specific legal rules and provisions
  - Court's holding and analysis
  - Further analysis
  - Instruments cited
  - Additional materials

### list_cases
List all cases in the database, optionally filtered by category.

**Parameters:**
- `category` (string, optional): Filter by crime category

**Example:**
```json
{
  "function": "list_cases",
  "category": "Genocide"
}
```

**Available Categories:**
- Genocide
- WarCrimes
- CrimesAgainstHumanity
- CrimeOfAggression
- Torture
- Piracy
- Terrorism

**Returns:**
- `total`: Number of cases found
- `category`: The category filter (or "all" if none)
- `cases`: Array of case objects with `case_id`, `name`, and `url`

### list_categories
Get all available crime categories for browsing.

**Example:**
```json
{
  "function": "list_categories"
}
```

**Returns:**
- `total`: Number of categories
- `categories`: Array with `name`, `slug`, and `url` for each category

### search_cases
Search for cases by name/keyword.

**Parameters:**
- `query` (string): Search term to match against case names

**Example:**
```json
{
  "function": "search_cases",
  "query": "Rwanda"
}
```

**Returns:**
- `query`: The search term used
- `total`: Number of matching cases
- `cases`: Array of matching case objects

## Data Sources

All data is retrieved from the official International Crimes Database at:
https://www.internationalcrimesdatabase.org

## Use Cases

- Research international criminal law jurisprudence
- Find cases by crime category (genocide, war crimes, crimes against humanity, etc.)
- Extract case metadata for legal research
- Analyze court holdings and legal reasoning
- Identify cited instruments and precedents

## Notes

- The database contains approximately 69 cases covering various international crimes
- Cases include decisions from international tribunals (ICTR, ICTY, ICC, etc.) and national courts
- Case records are structured with standardized sections for easy analysis
- Links to official documents (PDFs) are included when available
