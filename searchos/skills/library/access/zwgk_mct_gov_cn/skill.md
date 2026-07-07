# 文化和旅游部政府信息公开 Access Skill

## Overview

This skill provides access to the government information disclosure portal of the **Ministry of Culture and Tourism of the People's Republic of China** (中华人民共和国文化和旅游部). The portal hosts official announcements, regulations, policies, and public notices related to cultural affairs and tourism industry.

## Key Features

### Document Types

The portal contains various types of government documents:

- **5A级旅游景区公告** (5A Scenic Area Announcements): Official designations of national 5A-level tourist attractions
- **政策法规** (Policies and Regulations): Laws, rules, and policy documents
- **部门规章** (Departmental Rules): Ministry-level regulations
- **行政许可** (Administrative Licenses): Tourism operation licenses
- **统计信息** (Statistical Information): Tourism statistics and data
- **行业标准** (Industry Standards): Tourism and cultural industry standards

### Supported Functions

#### 1. `fetch_document` - Retrieve Single Document

Fetch and parse a single government document with full content extraction.

```python
result = await execute({
    'function': 'fetch_document',
    'url': 'https://zwgk.mct.gov.cn/zfxxgkml/zykf/202412/t20241227_957450.html'
})
```

**Returns:**
- `title`: Document title (cleaned of HTML)
- `publish_date`: Publication date
- `organization`: Issuing department
- `index_number`: Official document index
- `doc_number`: Document number (文号)
- `content_text`: Full text content
- `scenic_areas`: For 5A announcements, extracted list of scenic areas
- `attachments`: Any attached files

#### 2. `fetch_documents` - Batch Document Retrieval

Fetch multiple documents concurrently.

```python
result = await execute({
    'function': 'fetch_documents',
    'urls': [
        'https://zwgk.mct.gov.cn/zfxxgkml/zykf/202402/t20240206_951222.html',
        'https://zwgk.mct.gov.cn/zfxxgkml/zykf/202412/t20241227_957450.html',
    ]
})
```

#### 3. `list_documents` - Browse Available Documents

List documents from the portal, optionally filtered by category.

```python
result = await execute({
    'function': 'list_documents',
    'category': 'zykf',  # Resource Development category
    'limit': 20
})
```

**Available Categories:**
- `zykf` - 资源开发 (Resource Development)
- `zcfg` - 政策法规 (Policies and Regulations)
- `bmgz` - 部门规章 (Departmental Rules)
- `scgl` - 市场管理 (Market Management)
- `tjxx` - 统计信息 (Statistical Information)
- `wysy` - 文艺事业 (Arts and Culture)
- `kjjy` - 科技教育 (Science and Education)

## Specialized Content Extraction

### 5A Scenic Area Announcements

The skill automatically extracts scenic area lists from 5A designation announcements. These announcements follow specific formats:

**Numbered Format:**
```
1.北京市北京（通州）大运河文化旅游景区
2.河北省唐山市南湖·开滦旅游景区
...
```

**Paragraph Format:**
```
河北省衡水市衡水湖旅游景区
山西省太原市晋祠天龙山景区
...
```

The extracted `scenic_areas` field contains:
```json
[
  {"number": 1, "name": "北京市北京（通州）大运河文化旅游景区"},
  {"number": 2, "name": "河北省唐山市南湖·开滦旅游景区"},
  ...
]
```

## Document URL Structure

Documents follow a consistent URL pattern:
```
https://zwgk.mct.gov.cn/zfxxgkml/{category}/{YYYYMM}/t{YYYYMMDD}_{DOCID}.html
```

Where:
- `{category}`: Document category (zykf, zcfg, etc.)
- `{YYYYMM}`: Year and month of URL creation
- `{YYYYMMDD}`: Full date in document ID
- `{DOCID}`: Unique document identifier

## Metadata Extraction

Documents include comprehensive metadata from:

1. **Meta Tags**: Standard HTML meta elements
   - `ArticleTitle`: Document title
   - `PubDate`: Publication date
   - `ContentSource`: Source department
   - `ColumnName`: Column/category name

2. **Content Header Table**: Structured header information
   - 索引号 (Index Number)
   - 文号 (Document Number)
   - 发布机构 (Issuing Organization)
   - 发布日期 (Publish Date)
   - 分类 (Category)
   - 主题词 (Keywords)

## Technical Details

### Request Handling
- Uses standard HTTP GET requests
- No authentication required
- Sessions use standard browser user-agents
- 30-second timeout per request

### Content Parsing
- HTML parsing via BeautifulSoup
- Content extraction from `.gsj_htmlcon` container
- Metadata extraction from both meta tags and content header
- Automatic HTML tag cleaning for titles

### Error Handling
- Returns structured error objects for failed requests
- HTTP status codes preserved in error responses
- Timeout handling with clear error messages

## Example Output

```json
{
  "success": true,
  "url": "https://zwgk.mct.gov.cn/zfxxgkml/zykf/202412/t20241227_957450.html",
  "title": "文化和旅游部关于确定19家旅游景区为国家5A级旅游景区的公告",
  "publish_date": "2024-12-27 00:00",
  "organization": "资源开发司",
  "doc_number": "文旅资源发〔2024〕100号",
  "scenic_areas": [
    {"number": 1, "name": "河北省衡水市衡水湖旅游景区"},
    {"number": 2, "name": "山西省太原市晋祠天龙山景区"},
    ...
  ],
  "scenic_area_count": 19,
  "content_text": "根据中华人民共和国国家标准《旅游景区质量等级的划分与评定》...",
  "attachments": []
}
```

## Limitations

1. **Search**: The portal's built-in search API has limited functionality; use `list_documents` for browsing
2. **Pagination**: Document listings may not show all available documents; the portal has limited pagination
3. **Attachments**: Some documents may have PDF attachments that are referenced but require separate download
4. **Rate Limiting**: Be mindful of request frequency to avoid overloading the server

## Use Cases

- Track national 5A scenic area designations
- Monitor tourism policy announcements
- Access cultural heritage preservation notices
- Research tourism industry regulations
- Extract tourism statistical data

## Related Skills

Combine with other government portal access skills for comprehensive policy research across multiple Chinese government agencies.