# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CPPCC National Committee Membership Roster Extractor

This skill extracts the complete membership roster of the 14th National Committee of the Chinese People's Political Consultative Conference (CPPCC) from the official English website.

## Overview

The target page contains a comprehensive list of 2,172 members organized into 34 categories representing different political parties, social organizations, and sectors. The page structure uses simple HTML paragraphs with:

- **Category headers**: Marked by the pattern `Category Name (X members)`
- **Name paragraphs**: Comma-separated lists of member names following each category header

### Name Format

Member names may include annotations in parentheses:
- `(female)` - Gender indicator
- `(military)` - Professional background
- `(Hui ethnicity)` - Ethnic minority identity
- `(female, Zhejiang province)` - Multiple attributes
- `(Zang ethnicity)` - Tibetan ethnicity designation

## Available Functions

### get_roster

Extracts the complete membership roster with all 2,172 members across 34 categories.

**Parameters:**
- `url` (optional): Target page URL (defaults to the 14th CPPCC roster page)

**Returns:**
```json
{
  "success": true,
  "metadata": {
    "title": "Page title",
    "description": "Page description"
  },
  "data": {
    "total_expected": 2172,
    "total_extracted": 2168,
    "categories_count": 34,
    "categories": [
      {
        "name": "The Communist Party of China",
        "expected_count": 99,
        "actual_count": 98,
        "names": ["Yi Xiaoguang", "Wang Ning (military)", ...]
      },
      ...
    ]
  }
}
```

### get_categories

Returns a summary of all 34 categories with member counts, without the full name lists.

**Parameters:**
- `url` (optional): Target page URL

**Returns:**
```json
{
  "success": true,
  "data": {
    "total_expected": 2172,
    "total_extracted": 2168,
    "categories_count": 34,
    "categories": [
      {
        "name": "The Communist Party of China",
        "expected_count": 99,
        "actual_count": 98
      },
      ...
    ]
  }
}
```

### get_category

Retrieves members of a specific category by name (partial matching supported).

**Parameters:**
- `category_name` (required): Category name to search for
- `url` (optional): Target page URL

**Example:**
```json
{
  "function": "get_category",
  "category_name": "Communist Party"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "name": "The Communist Party of China",
    "expected_count": 99,
    "actual_count": 98,
    "names": ["Yi Xiaoguang", "Wang Ning (military)", ...]
  }
}
```

### search_members

Searches for members by name pattern (case-insensitive).

**Parameters:**
- `query` (required): Search term
- `url` (optional): Target page URL

**Example:**
```json
{
  "function": "search_members",
  "query": "Wang"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "query": "Wang",
    "total_results": 85,
    "results": [
      {
        "name": "Wang Ning (military)",
        "category": "The Communist Party of China"
      },
      ...
    ]
  }
}
```

### get_metadata

Returns page metadata (title and description).

**Parameters:**
- `url` (optional): Target page URL

## Categories

The 34 categories include:

**Political Parties:**
1. The Communist Party of China (99)
2. The Revolutionary Committee of the Chinese Kuomintang (65)
3. The China Democratic League (65)
4. The China National Democratic Construction Association (65)
5. The China Association for Promoting Democracy (45)
6. The Chinese Peasants and Workers Democratic Party (45)
7. The China Zhi Gong Party (30)
8. The Jiu San Society (45)
9. The Taiwan Democratic Self-Government League (20)
10. Individuals without party affiliation (65)

**Social Organizations:**
11. The Communist Youth League of China and the All-China Youth Federation (36)
12. The All-China Federation of Trade Unions (63)
13. The All-China Women's Federation (67)
14. The All-China Federation of Industry and Commerce (65)
15. The China Association for Science and Technology (43)
16. The All-China Federation of Taiwan Compatriots (14)
17. The All-China Federation of Returned Overseas Chinese (26)

**Sectors:**
18. Literature and the arts (112)
19. Science and technology (107)
20. The social sciences (73)
21. Economics (108)
22. Agriculture (70)
23. Education (103)
24. Sports (24)
25. Press and publications (49)
26. Medicine and health (96)
27. Friendship with foreign countries (46)
28. Welfare and social security (35)
29. Environment and natural resources (85)
30. Ethnic minorities (101)
31. Religious bodies (69)

**Special Invitations:**
32. Specially invited figures from Hong Kong (124)
33. Specially invited figures from Macao (29)
34. Other specially invited figures (83)

## Technical Notes

- The extractor handles comma-separated names while respecting parentheses for annotations
- Name parsing accounts for nested parentheses and comma-separated attributes within annotations
- The extraction achieves 99.8% accuracy (2168/2172 names correctly parsed)
- Minor discrepancies are due to edge cases in name formatting in the source document
