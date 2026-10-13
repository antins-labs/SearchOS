# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# China Zhi Gong Party (致公党) Website Access Skill

This skill provides structured access to the official website of the China Zhi Gong Party (中国致公党), one of China's eight non-communist political parties.

## Available Functions

### 1. get_current_leadership
Retrieves the list of current leaders (第十六届/现任领导).

**Example:**
```python
params = {
    "function": "get_current_leadership"
}
```

**Returns:**
- List of current leaders with names, positions, profile URLs, and brief introductions
- Includes Chairman (主席), Vice Chairmen (副主席), and other leadership positions

### 2. get_leader_profile
Retrieves detailed biography and career history for a specific leader.

**Parameters:**
- `profile_url` (required): URL of the leader's profile page

**Example:**
```python
params = {
    "function": "get_leader_profile",
    "profile_url": "https://www.zg.org.cn/zgdjj/ljld/dsljld/202212/t20221216_75309.htm"
}
```

**Returns:**
- Full name and photo URL
- Basic information (gender, ethnicity, birth date, native place)
- Current position
- Complete career history with timeline
- Educational background

### 3. get_central_news
Retrieves the latest central news articles (中央要闻).

**Parameters:**
- `limit` (optional): Number of articles to return (default: 10)

**Example:**
```python
params = {
    "function": "get_central_news",
    "limit": 5
}
```

**Returns:**
- List of news articles with titles, dates, URLs, and preview text

### 4. get_article
Retrieves full content of a specific news article.

**Parameters:**
- `article_url` (required): URL of the news article

**Example:**
```python
params = {
    "function": "get_article",
    "article_url": "https://www.zg.org.cn/zyyw/202607/t20260719_77645.htm"
}
```

**Returns:**
- Article title and date
- Full text content (paragraphs)
- Associated images
- Breadcrumb navigation

### 5. get_leadership_history
Retrieves index of all leadership terms (历届领导).

**Example:**
```python
params = {
    "function": "get_leadership_history"
}
```

**Returns:**
- List of all leadership terms from 1st to current (16th)
- URLs for each term's leadership page

### 6. get_term_leadership
Retrieves leadership list for a specific historical term.

**Parameters:**
- `term_url` (required): URL of the term's leadership page

**Example:**
```python
params = {
    "function": "get_term_leadership",
    "term_url": "https://www.zg.org.cn/zgdjj/ljld/dyjld/"  # First term
}
```

**Returns:**
- List of leaders for that term
- Names, positions, and profile URLs

## Data Structure

### Leader Object
```json
{
  "name": "蒋作君",
  "profile_url": "https://www.zg.org.cn/zgdjj/ljld/dsljld/202212/t20221216_75309.htm",
  "image_url": "https://www.zg.org.cn/zgdjj/ljld/dsljld/202212/W020230313686492663264.jpg",
  "intro": "Brief introduction...",
  "current_position": "现任全国政协副主席、致公党中央主席",
  "date": "2016-08-02"
}
```

### Profile Object
```json
{
  "name": "蒋作君",
  "image_url": "...",
  "bio_title": "蒋作君同志简历",
  "basic_info": "蒋作君，男，汉族，1955年7月生，安徽怀宁人...",
  "gender": "男",
  "birth_year": "1955",
  "birth_month": "7",
  "ethnicity": "汉族",
  "native_place": "安徽怀宁",
  "current_position": "现任全国政协副主席、致公党中央主席",
  "career_history": [
    "1974.03-1978.02 安徽省歙县森村乡插队知青",
    "1978.02-1982.08 安徽医学院医疗系学习..."
  ]
}
```

### News Article Object
```json
{
  "title": "致公党中央领导班子...",
  "url": "https://www.zg.org.cn/zyyw/202607/t20260719_77645.htm",
  "date": "2026-07-19",
  "preview": "Preview text...",
  "paragraphs": ["Paragraph 1", "Paragraph 2", ...],
  "images": [
    {"url": "...", "alt": "..."}
  ]
}
```

## Notes

- All Chinese text is preserved in UTF-8 encoding
- URLs are absolute and can be used directly
- Dates are in YYYY-MM-DD format where available
- The skill handles various Chinese date formats and ethnic group names
- Error responses include descriptive messages in both English and Chinese where appropriate

## Source Website

- Main site: https://www.zg.org.cn
- Leadership section: https://www.zg.org.cn/zgdjj/ljld/
- Central news: https://www.zg.org.cn/zyyw/
