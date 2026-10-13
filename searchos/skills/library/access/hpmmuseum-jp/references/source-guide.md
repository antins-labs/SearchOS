# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Hiroshima Peace Memorial Museum Access Skill

This skill provides structured access to the Hiroshima Peace Memorial Museum website (hpmmuseum.jp), enabling retrieval of museum information, virtual museum exhibits, and exhibition details.

## Features

- **Information Pages**: Access visiting information, hours, access routes, guide services, floor maps, and more
- **Virtual Museum Exhibits**: Browse and read detailed exhibit pages from the online virtual museum
- **Multi-language Support**: Content available in English, Japanese, French, German, Italian, Spanish, and Chinese
- **Exhibition Information**: Access permanent and special exhibition details

## Functions

### get_info_page

Retrieve museum information pages by page ID.

**Parameters:**
- `page_id` (required): The page ID number
- `lang`: Language code (default: eng)

**Common Page IDs:**
| Page | ID |
|------|-----|
| Visiting | 42 |
| Access | 154 |
| Guide Services | 52 |
| Floor Map | 174 |
| Museum Shop | 155 |
| Library | 63 |
| Online A-bomb Survivor Testimony | 177 |
| Learn about the A-bomb and Peace | 163 |
| Museum History | 67 |
| Outline of Facilities | 168 |
| Donations | 171 |

**Example:**
```json
{
  "function": "get_info_page",
  "page_id": "42",
  "lang": "eng"
}
```

### get_exhibit_page

Retrieve a specific page from a virtual museum exhibit.

**Parameters:**
- `exhibit_id` (required): Exhibit ID (e.g., "1302")
- `page_num` (required): Page number as 2-digit string (e.g., "00", "01", "06")
- `lang`: Language code (default: eng)

**Example:**
```json
{
  "function": "get_exhibit_page",
  "exhibit_id": "1302",
  "page_num": "06"
}
```

### get_exhibit_toc

Get the table of contents for a virtual museum exhibit.

**Parameters:**
- `exhibit_id` (required): Exhibit ID
- `lang`: Language code (default: eng)

**Example:**
```json
{
  "function": "get_exhibit_toc",
  "exhibit_id": "1302"
}
```

### get_permanent_exhibitions

Get information about permanent exhibitions.

**Parameters:**
- `lang`: Language code (default: eng)

**Example:**
```json
{
  "function": "get_permanent_exhibitions",
  "lang": "eng"
}
```

### get_homepage

Get homepage navigation information including links to all major sections.

**Parameters:**
- `lang`: Language code (default: eng)

**Example:**
```json
{
  "function": "get_homepage",
  "lang": "eng"
}
```

## Language Codes

| Language | Code |
|----------|------|
| English | eng |
| Japanese | jpn |
| French | fre |
| German | ger |
| Italian | ita |
| Spanish | spa |
| Chinese | zho |

## Known Exhibits

- **1302**: "Memories of You: If not for the bomb" - A special exhibition about the atomic bombing and its aftermath

## Return Values

All functions return structured dictionaries containing:

- `title`: Page title
- `content`: Main text content
- `url`: The accessed URL
- `status`: HTTP status code
- Function-specific data (e.g., `sections`, `images`, `navigation` for exhibits)

On error, returns:
- `error`: Error description
- `hint`: Suggestion for fixing the error (when applicable)

## Notes

- The museum website may have slow response times; timeouts are set accordingly
- Virtual museum exhibits are rich in historical photographs and detailed narratives
- The site uses a consistent URL structure that allows systematic access to content
