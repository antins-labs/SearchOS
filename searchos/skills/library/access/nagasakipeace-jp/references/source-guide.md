# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Nagasaki Peace Portal Access Skill

This skill retrieves structured information from the official Nagasaki Peace Portal (nagasakipeace.jp), which provides comprehensive information about the Nagasaki Atomic Bomb Museum, historical records of the atomic bombing, survivor testimonies, and peace education resources.

## Available Functions

### get_home_page
Retrieves the home page with navigation structure and overview information. Returns categorized links to all major sections of the site including museum visits, historical records, survivor testimonies, and reference materials.

### get_museum_info
Retrieves detailed information about the Nagasaki Atomic Bomb Museum including:
- Location and address
- Site area and floor area
- Floor-by-floor facility information
- Introduction and historical context

### get_records_page
Retrieves the overview page for Records of the Nagasaki Atomic Bombing, including links to:
- Photographs
- About the Atomic Bomb

### get_photo_gallery
Retrieves photo gallery categories or specific photo collections.

**Parameters:**
- `gallery_id` (optional): Specific gallery identifier (e.g., `part_1.html`, `part_2_01.html`)

Available galleries include:
- Events Leading up to Atomic Bombing
- At 11:02 a.m. August 9, 1945
- Nagasaki, the Atomic Wasteland
- The Ruins of Urakami Cathedral
- Damage Caused by the Flash of Heat
- Damage Caused by the Fire
- Damages Caused by the Blast
- Human Injuries Caused by Radiation
- Rescue and Relief Activities
- The Achievements of Dr. Takashi Nagai
- Testimonies of the Japanese Atomic Bomb Survivors
- The Nuclear Age
- Modern Nuclear Weapons

### get_survivors_page
Retrieves the Atomic Bomb Survivors page with list of available testimonies including:
- Plea of Atomic Bomb Survivor (Sakue Shimohira)
- The Unforgettable Experience of the Atomic Bombing (Yoshiro Yamawaki)
- A Monument to 11:02 a.m. (Koichi Wada)
- Nationally Designated Historic Site "Nagasaki Atomic Bomb Historic Ruins"

### get_survivor_story
Retrieves a specific survivor's testimony with full text content.

**Parameters:**
- `story_id` (required): Story identifier (e.g., `sakue_shimohira.html`, `yoshiro_yamawaki.html`)

### get_reference_page
Retrieves the reference materials page with links to:
- Lending programs
- Educational materials
- Kids resources

### get_about_atomic_bomb
Retrieves background information about the atomic bomb and its effects on Nagasaki.

### get_page
Retrieves any page by its path for flexible access to all site content.

**Parameters:**
- `path` (required): Page path (e.g., `/en/visit/abm/`, `/en/search/record/`)

## Content Types

The skill extracts and structures:
- Page metadata (title, description, keywords)
- Headings hierarchy
- Paragraphs and full text content
- Tables (e.g., museum floor information)
- Images with captions
- Internal navigation links

## Example Usage

```python
# Get museum information
result = await execute({"function": "get_museum_info"}, ctx)

# Get survivor testimonies list
result = await execute({"function": "get_survivors_page"}, ctx)

# Get specific survivor story
result = await execute({
    "function": "get_survivor_story",
    "story_id": "sakue_shimohira.html"
}, ctx)

# Get photo gallery
result = await execute({"function": "get_photo_gallery"}, ctx)

# Get specific photo gallery
result = await execute({
    "function": "get_photo_gallery",
    "gallery_id": "part_1.html"
}, ctx)

# Get any page by path
result = await execute({
    "function": "get_page",
    "path": "/en/search/record/photo/"
}, ctx)
```

## Notes

- All content is in English (using the /en/ path)
- The site provides historical documentation about the atomic bombing of Nagasaki on August 9, 1945
- Survivor testimonies contain detailed personal accounts of the bombing experience
- Photo galleries include historical photographs from before, during, and after the bombing
- The Nagasaki Atomic Bomb Museum information includes practical visitor details
