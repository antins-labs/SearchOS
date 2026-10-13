# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Krupp Foundation Access Skill

Access institutional profiles and exhibition records from the Alfried Krupp von Bohlen und Halbach Foundation website.

## Available Functions

### list_institutions
Returns a list of all institutions supported by the Krupp Foundation.

**Parameters:** None

**Example:**
```json
{"function": "list_institutions"}
```

**Returns:**
- `institutions`: Array of institution objects with name, slug, and URL
- `total`: Count of institutions
- `breadcrumb`: Navigation path

### get_institution
Returns detailed information about a specific institution.

**Parameters:**
- `slug` (optional): Institution slug, e.g., "thyssenkrupp-ag"
- `url` (optional): Full URL to the institution page

**Examples:**
```json
{"function": "get_institution", "slug": "thyssenkrupp-ag"}
{"function": "get_institution", "url": "https://www.krupp-stiftung.de/en/institutionen/villa-huegel-park/"}
```

**Returns:**
- `title`: Institution name
- `sections`: Array of content sections (heading + content)
- `images`: Associated images with alt text and URLs
- `breadcrumb`: Navigation path
- `metadata`: Publication/modification dates

### get_exhibition
Returns content from the Krupp Historical Exhibition at Villa Hügel.

**Parameters:** None

**Example:**
```json
{"function": "get_exhibition"}
```

**Returns:**
- `title`: Exhibition title
- `introduction`: Overview text
- `rooms`: Array of exhibition rooms, each with topics
- `images`: Associated images
- `breadcrumb`: Navigation path

### get_page
Returns content from any page on the Krupp Foundation website.

**Parameters:**
- `url` (required): Full URL from www.krupp-stiftung.de

**Example:**
```json
{"function": "get_page", "url": "https://www.krupp-stiftung.de/en/alfried-krupp/"}
```

**Returns:**
- `title`: Page title
- `sections`: Array of content sections
- `images`: Associated images
- `breadcrumb`: Navigation path
- `type`: Detected page type (institution_list, institution_detail, exhibition, page)

## Data Extracted

The skill extracts:
- **Structured content**: Section headings and paragraphs from main content
- **Images**: Image URLs with descriptive alt text
- **Navigation breadcrumbs**: Hierarchical page location
- **Metadata**: Publication and modification dates from JSON-LD
- **Institution listings**: Names and URLs for all foundation institutions

## Institution Slugs

Some known institution slugs:
- `thyssenkrupp-ag` - thyssenkrupp AG
- `villa-huegel-park` - Villa Hügel & Park
- `historisches-archiv-krupp` - Krupp Historical Archive
- `germania-vi` - Germania VI yacht
- `alfried-krupp-krankenhaus` - Alfried Krupp Hospital
- `alfried-krupp-kolleg-greifswald` - Alfried Krupp Institute for Advanced Study
- `etuf` - ETUF e.V.
- `kulturstiftung-ruhr` - Kulturstiftung Ruhr
- `margarethe-krupp-stiftung` - Margarethe Krupp Foundation
