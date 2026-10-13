# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# George W. Bush White House Archives Access Skill

This skill extracts structured content from the archived George W. Bush White House website (georgewbush-whitehouse.archives.gov), including press releases, holiday pages, and White House event menus.

## Features

### Supported Page Types

1. **Press Releases** (`/news/releases/...`)
   - Extracts title, date, office, and formatted content
   - Handles menu listings, event details, and official announcements
   - Example: Thanksgiving Menu at Camp David, State Dinner menus

2. **Holiday Pages** (`/holiday/...`)
   - Extracts themed holiday content (Thanksgiving, Christmas, Easter, etc.)
   - Captures multiple content sections and related links
   - Example: Thanksgiving at the White House 2007

3. **Menu Archive** (`/firstlady/arts-menu-archive.html`)
   - Complete listing of all White House event menus (2001-2009)
   - Organized by year with dates and links to full menu details
   - Includes State Dinners, holiday menus, and special events

4. **Generic Pages**
   - Fallback extraction for any other pages on the site
   - Captures title, main content, and relevant links

## Functions

### `get_page`
Fetches and extracts content from a specific URL.

**Parameters:**
- `url` (required): The page URL to fetch

**Example:**
```json
{
  "function": "get_page",
  "url": "https://georgewbush-whitehouse.archives.gov/news/releases/2007/11/20071121-2.html"
}
```

**Returns:**
- For press releases: title, date, office, content array
- For holiday pages: title, year, sections, related links
- For menu archive: title, menus array with dates and URLs
- For generic pages: title, content, links

### `get_menu_archive`
Retrieves the complete White House event menu archive.

**Parameters:** None

**Example:**
```json
{
  "function": "get_menu_archive"
}
```

**Returns:**
```json
{
  "type": "menu_archive",
  "title": "White House Event Menus Archive",
  "menus": [
    {
      "date": "Nov. 26, 2008",
      "year": "2008",
      "title": "Thanksgiving Menu at Camp David",
      "url": "https://..."
    },
    ...
  ],
  "total_count": 45
}
```

### `search_menus`
Searches the menu archive by year or keyword.

**Parameters:**
- `year` (optional): Filter by year (e.g., "2007")
- `keyword` (optional): Search in menu titles (e.g., "Thanksgiving")

**Examples:**
```json
{
  "function": "search_menus",
  "year": "2007"
}
```

```json
{
  "function": "search_menus",
  "keyword": "State Dinner"
}
```

```json
{
  "function": "search_menus",
  "year": "2008",
  "keyword": "Thanksgiving"
}
```

## Content Types Extracted

### Press Release Content
The skill extracts structured data from press releases including:
- **Thanksgiving menus** at Camp David and the White House
- **State Dinner menus** for visiting dignitaries
- **Holiday reception menus** 
- **Official announcements** from the First Lady's office

### Menu Archive
The archive includes menus for:
- State Dinners (honoring foreign leaders)
- Official Dinners and Luncheons
- Holiday celebrations (Thanksgiving, Christmas, Easter)
- Special events and receptions

## Notes

- The site is an official National Archives preservation of the George W. Bush White House website
- Content spans 2001-2009 (the Bush administration years)
- Menu listings include both the event date and the menu items served
- Some pages may have archival formatting that differs from modern web standards
