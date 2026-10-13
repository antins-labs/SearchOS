# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Alpha History Vietnam War Archive

Access historical articles from Alpha History's Vietnam War archive at alphahistory.com/vietnamwar.

## Overview

This skill provides structured access to educational content about the Vietnam War, including:
- **Topic Articles**: In-depth articles covering key events, movements, and concepts
- **Documents**: Primary source documents and historical texts
- **Timelines**: Chronological entries organized by period
- **Biographies**: Profiles of key figures (Who's Who)

## Functions

### get_article

Fetch a specific article with full structured content.

**Parameters:**
- `url` (optional): Full article URL
- `slug` (optional): Article URL slug (e.g., "japanese-occupation-of-vietnam")

**Returns:**
- Article title, description, and URL
- Structured sections with headings, paragraphs, images, and captions
- Word count
- Related article links

**Example:**
```json
{
  "function": "get_article",
  "slug": "viet-minh"
}
```

### list_topics

List all available topic articles.

**Returns:**
- List of articles with titles and URLs covering major Vietnam War topics

**Example:**
```json
{
  "function": "list_topics"
}
```

Topics include: French colonialism, Japanese occupation, Viet Minh, Ho Chi Minh, First Indochina War, Dien Bien Phu, Geneva Accords, South Vietnam, Ngo Dinh Diem, North Vietnam, Viet Cong, US involvement, and more.

### list_documents

List all available document articles.

**Returns:**
- Document categories and individual document articles

**Example:**
```json
{
  "function": "list_documents"
}
```

Categories include: Vietnam before 1954, North and South Vietnam, American escalation, Military tactics, The My Lai massacre.

### list_timeline

Get timeline entries for a specific period.

**Parameters:**
- `period` (optional): Time period (default: "to-1945")

**Available periods:**
- `to-1945`: Before 1945
- `1946-1954`: 1946-1954
- `1955-1959`: 1955-1959
- `1960-1964`: 1960-1964
- `1965-1967`: 1965-1967
- `1968-1970`: 1968-1970
- `1971-beyond`: 1971 and beyond
- `cambodia`: Cambodia-related events
- `operations`: Military operations

**Returns:**
- Timeline entries with year, month (if available), and event description

**Example:**
```json
{
  "function": "list_timeline",
  "period": "1946-1954"
}
```

### list_people

List biographical entries from Who's Who.

**Returns:**
- List of people with names and profile URLs

**Example:**
```json
{
  "function": "list_people"
}
```

Includes figures like: Ho Chi Minh, Le Duan, Le Duc Tho, Pham Van Dong, Vo Nguyen Giap, Ngo Dinh Diem, Nguyen Van Thieu, and many others.

### search

Search for articles by keyword.

**Parameters:**
- `keyword` (required): Search term

**Returns:**
- Matching articles with titles and URLs

**Example:**
```json
{
  "function": "search",
  "keyword": "ho chi minh"
}
```

## Content Structure

Articles are returned with structured sections:
- Each section has an optional heading (with level h2-h6)
- Paragraphs are extracted as plain text
- Images include src URL and alt text
- Captions are extracted separately

This structured format makes it easy to:
- Navigate through article content
- Extract specific sections
- Display content with proper formatting
- Cite and reference specific passages

## Use Cases

1. **Research**: Access comprehensive historical content about the Vietnam War
2. **Education**: Retrieve structured content for teaching materials
3. **Reference**: Look up specific events, people, or documents
4. **Chronology**: Build timelines of Vietnam War events
5. **Analysis**: Extract and analyze historical narratives

## Notes

- All content is from Alpha History's educational Vietnam War archive
- Articles are well-structured with clear sections and headings
- Images include descriptive captions
- Related articles are linked for further reading
- Timeline entries span from the 1850s through 1975
