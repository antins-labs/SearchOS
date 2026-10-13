# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Renmin University GSAI Faculty Profile Skill

This skill retrieves structured faculty profile information from the Renmin University of China Gaoling School of Artificial Intelligence (GSAI) website at gsai.ruc.edu.cn.

## Features

- **Chinese Profiles**: Fetches detailed Chinese-language faculty profiles
- **English Profiles**: Also supports English versions of faculty profiles
- **Structured Data**: Extracts all key profile fields into organized JSON

## Available Functions

### `get_profile`

Retrieves a Chinese-language faculty profile.

**Parameters:**
- `url` (required): The faculty profile URL or name slug
  - Full URL: `https://gsai.ruc.edu.cn/chenxu`
  - Name slug: `chenxu`

**Returns:**
```json
{
  "success": true,
  "url": "https://gsai.ruc.edu.cn/chenxu",
  "name": "陈旭",
  "position": "预聘副教授",
  "bio": "陈旭，中国人民大学高瓴人工智能学院预聘副教授...",
  "education": [
    "清华大学 软件学院 博士",
    "美国佐治亚理工学院 (Georgia Institute of Technology) CSE 访问学者",
    "北京科技大学 计算机科学与技术 硕士",
    "北京交通大学 通信工程 学士"
  ],
  "work_experience": [
    "中国人民大学 高瓴人工智能学院 预聘副教授",
    "中国人民大学 高瓴人工智能学院 预聘助理教授",
    "英国伦敦大学学院 (University College London) Computer Science 博士后研究员"
  ],
  "research_interests": "大模型：大模型智能体...",
  "student_requirements": "热爱科研，热爱生活...",
  "courses": [...],
  "contact": {
    "email": "xu.chen@ruc.edu.cn",
    "office": "立德楼1714"
  },
  "links": {
    "google_scholar": "https://scholar.google.com/...",
    "group_website": "ai-engine-lab.com"
  }
}
```

### `get_profile_english`

Retrieves an English-language faculty profile (when available).

**Parameters:**
- `url` (required): The faculty profile URL or name slug
  - Full URL: `https://gsai.ruc.edu.cn/english/chenxu`
  - Name slug: `chenxu` (will be converted to English URL automatically)

## Usage Examples

### Example 1: Get Chinese profile with full URL
```json
{
  "function": "get_profile",
  "url": "https://gsai.ruc.edu.cn/chenxu"
}
```

### Example 2: Get Chinese profile with name slug
```json
{
  "function": "get_profile",
  "url": "chenxu"
}
```

### Example 3: Get English profile
```json
{
  "function": "get_profile_english",
  "url": "chenxu"
}
```

## Extracted Fields

| Field | Description |
|-------|-------------|
| `name` | Faculty member's name |
| `position` | Academic position/title |
| `bio` | Full biography/introduction text |
| `education` | List of educational background entries |
| `work_experience` | List of work experience entries |
| `research_interests` | Research interests and related links |
| `student_requirements` | Requirements for prospective students |
| `courses` | List of taught courses |
| `contact` | Contact information (email, phone, office) |
| `links` | External links (Google Scholar, group website, etc.) |

## Notes

- The skill uses browser automation (Playwright) to handle JavaScript-rendered content
- Both Chinese and English profile versions are supported
- URLs are automatically normalized if only a name slug is provided
- Empty or unavailable fields will be `null` or empty arrays
