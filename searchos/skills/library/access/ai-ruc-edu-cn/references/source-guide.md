# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# RUC AI Faculty Profile Scraper

Extracts detailed faculty profile information from the Renmin University of China Gaoling School of Artificial Intelligence website (ai.ruc.edu.cn).

## Supported URLs

This skill extracts structured data from faculty profile pages such as:

- Chinese profiles: `http://ai.ruc.edu.cn/academicfaculty/szdwn/{pinyin}/index.htm`
  - Example: `http://ai.ruc.edu.cn/academicfaculty/szdwn/wjr/index.htm` (文继荣)

- English profiles: `http://ai.ruc.edu.cn/english/FACULTYn/{Name}/index.htm`
  - Example: `http://ai.ruc.edu.cn/english/FACULTYn/JiRongWen/index.htm`
  - Example: `http://ai.ruc.edu.cn/english/FACULTYn/QiQi/index.htm`

## Extracted Information

### Basic Profile
- **Name**: Faculty member's name
- **Position**: Academic title (Professor, Associate Professor, etc.)
- **Bio**: Biographical summary
- **Photo URL**: Profile photo (if available)

### Sections (when available)
- **Education**: Educational background
- **Work Experience**: Professional history
- **Research Interests**: Research areas and focus
- **Teaching**: Courses taught
- **Publications**: Academic publications with links to external resources
- **Contact**: Email and other contact information

### External Links
The skill extracts external links found in publications sections, including:
- Google Scholar profiles
- DBLP profiles
- Paper links (ScienceDirect, PDFs, etc.)

## Usage

### Get Faculty Profile

```
function: get_profile
url: http://ai.ruc.edu.cn/english/FACULTYn/QiQi/index.htm
```

Returns structured data:

```json
{
  "success": true,
  "profile": {
    "url": "http://ai.ruc.edu.cn/english/FACULTYn/QiQi/index.htm",
    "name": "Qi Qi",
    "position": "TENURED ASSOCIATE PROFESSOR",
    "bio": "Dr. Qi is now a tenured Associate Professor...",
    "sections": {
      "Education": {
        "content": "2008-2012, Stanford University, Ph.D....",
        "links": []
      },
      "Work Experience": {
        "content": "2021.8 - now, Gaoling School...",
        "links": []
      },
      "Research Interests": {
        "content": "EconCS, Game theory, Mechanism design...",
        "links": []
      },
      "Publications": {
        "content": "List of publications...",
        "links": [{"text": "DBLP", "url": "https://dblp.org/..."}]
      }
    },
    "contact": {
      "email": "qi.qi@ruc.edu.cn"
    },
    "external_links": [...]
  }
}
```

### Search (Not Available)

The site does not provide a searchable faculty directory API. You must provide direct URLs to faculty profile pages.

## Notes

- Both Chinese and English profile pages are supported
- Section names are normalized to English for consistency
- External links are collected separately for easy access
- The skill handles the site's HTML structure which uses `colorlib-narrow-content` divs for section content
