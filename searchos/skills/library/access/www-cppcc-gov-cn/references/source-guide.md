# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CPPCC Committee Members Access Skill

## Overview

This skill fetches and parses structured committee member lists from the Chinese People's Political Consultative Conference (CPPCC, 中国人民政治协商会议) official website (www.cppcc.gov.cn). It extracts member information organized by political parties, democratic parties, and sector groups.

## Target Site

- **Host**: www.cppcc.gov.cn
- **Content Type**: Government committee member lists
- **Structure**: Highly structured HTML with party/group headers followed by member names

## Available Functions

### 1. get_committee_members

Fetches the complete committee member list with optional party/group filtering.

**Parameters:**
- `url` (optional): Specific article URL to fetch. Defaults to the 14th CPPCC National Committee member list.
- `party` (optional): Filter by party or sector name (supports partial matching)

**Returns:**
```json
{
  "success": true,
  "url": "http://www.cppcc.gov.cn/zxww/2023/01/18/ARTI1674005617470226.shtml",
  "title": "中国人民政治协商会议第十四届全国委员会委员名单",
  "parties": [
    {
      "party": "中国共产党",
      "declared_count": 87,
      "member_count": 87,
      "members": ["乙晓光", "王宁（军队）", "王军", ...]
    },
    ...
  ],
  "party_count": 34,
  "total_members": 2169
}
```

### 2. get_member_details

Searches for a specific member across all parties and returns their party affiliation and attributes.

**Parameters:**
- `member_name` (required): Name to search for (supports partial matching)
- `url` (optional): Specific article URL to fetch

**Returns:**
```json
{
  "success": true,
  "member_name": "王沪宁",
  "found": true,
  "match_count": 1,
  "matches": [
    {
      "raw_name": "王沪宁",
      "name": "王沪宁",
      "attributes": {},
      "party": "中国共产党"
    }
  ],
  "url": "...",
  "title": "..."
}
```

## Data Structure

### Party/Group Categories

The committee members are organized into 34 categories including:

**Political Parties:**
- 中国共产党 (Communist Party of China)
- 中国国民党革命委员会
- 中国民主同盟
- 中国民主建国会
- 中国民主促进会
- 中国农工民主党
- 中国致公党
- 九三学社
- 台湾民主自治同盟
- 无党派人士

**Sector Groups:**
- 文化艺术界
- 科学技术界
- 社会科学界
- 经济界
- 农业界
- 教育界
- 体育界
- 新闻出版界
- 医药卫生界
- 对外友好界
- 社会福利和社会保障界
- 环境资源界
- 少数民族界
- 宗教界

**Special Invitations:**
- 特邀香港人士
- 特邀澳门人士
- 特别邀请人士

**Mass Organizations:**
- 中国共产主义青年团和中华全国青年联合会
- 中华全国总工会
- 中华全国妇女联合会
- 中华全国工商业联合会
- 中国科学技术协会
- 中华全国台湾同胞联谊会
- 中华全国归国华侨联合会

### Member Attributes

Member names may include attributes in parentheses:
- **Gender**: （女）= female, （男）= male
- **Ethnicity**: （蒙古族）、（藏族）、（回族）etc.
- **Affiliation**: （军队）、（北京）、（文化和旅游部）etc.

Example: `田向利（女）` = female member
Example: `巴特尔（蒙古族）` = Mongolian ethnicity
Example: `王宁（军队）` = military affiliation

## Examples

### Example 1: Get all committee members
```json
{
  "function": "get_committee_members"
}
```

### Example 2: Filter by party
```json
{
  "function": "get_committee_members",
  "party": "文化艺术界"
}
```

### Example 3: Search for a member
```json
{
  "function": "get_member_details",
  "member_name": "王沪宁"
}
```

### Example 4: Search with partial name
```json
{
  "function": "get_member_details",
  "member_name": "张"
}
```
(Note: This will return all members with "张" in their name)

## Technical Details

- **Parsing Method**: HTML parsing using BeautifulSoup
- **Data Format**: Members separated by Chinese comma (、)
- **Party Headers**: Pattern `^(.+?)[（\(](\d+)人[）\)]$` (e.g., "中国共产党（87人）")
- **Encoding**: UTF-8
- **Timeout**: 30 seconds

## Error Handling

The skill returns structured error responses:
- `success: false` indicates failure
- `error` field contains the error message
- Common errors:
  - Network timeout
  - HTTP errors (404, 500, etc.)
  - No data found on page
  - Invalid parameters

## Limitations

- Only works with CPPCC committee member list pages
- Member attributes parsing may not capture all variations
- Historical committee lists may have different formatting
