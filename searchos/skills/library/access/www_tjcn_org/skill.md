# TJCN Statistical Bulletin Access Skill

This skill fetches and parses Chinese provincial statistical bulletins (国民经济和社会发展统计公报) from www.tjcn.org (中国统计信息网).

## Features

- **Full Text Extraction**: Retrieves complete statistical report content including all sections and data tables
- **GBK Encoding Support**: Properly handles the site's GBK encoding which is often misdetected as UTF-8
- **Structured Data Parsing**: Extracts:
  - Metadata (province, year, publish date, source, view count)
  - Data tables (表1, 表2, etc.) with their titles and row data
  - Section breakdowns (一、综合, 二、农业, etc.)
- **List Parsing**: Can extract report listings from category pages
- **Search Helper**: Provides province code mapping for finding reports

## Usage

### Get a Single Report

```python
result = await execute({
    'function': 'get_report',
    'url': 'http://www.tjcn.org/tjgb/11zj/37664.html'
})
```

Returns:
```json
{
    "success": true,
    "url": "http://www.tjcn.org/tjgb/11zj/37664.html",
    "metadata": {
        "province": "浙江省",
        "year": 2023,
        "title": "浙江省2023年国民经济和社会发展统计公报",
        "publish_date": "2024-03-11",
        "source": "浙江省统计局",
        "views": 615
    },
    "full_text": "...",
    "full_text_length": 13340,
    "data_tables": {
        "table_1": {
            "number": 1,
            "title": "2023年居民消费价格指数情况（上年＝100）",
            "content": "...",
            "rows": [["居民消费价格指数", "100.3", "100.3", "100.3"], ...]
        }
    },
    "data_tables_count": 9,
    "sections": [
        {
            "number": "一",
            "title": "综合",
            "content": "...",
            "content_length": 1244
        }
    ],
    "sections_count": 13
}
```

### Get Report List

```python
result = await execute({
    'function': 'get_list',
    'url': 'http://www.tjcn.org/tjgb/11zj/'
})
```

### Search for Reports

```python
result = await execute({
    'function': 'search',
    'query': '浙江',
    'year': 2023
})
```

## URL Patterns

The site organizes reports by province codes in the URL path:
- `/tjgb/11zj/` - 浙江省 (Zhejiang)
- `/tjgb/03hb/` - 河北省 (Hebei)
- `/tjgb/10js/` - 江苏省 (Jiangsu)
- `/tjgb/02bj/` - 北京市 (Beijing)
- `/tjgb/09sh/` - 上海市 (Shanghai)
- etc.

Each report has a numeric ID (e.g., `37664.html`).

## Content Structure

Statistical bulletins follow a standardized format:
1. **综合** (Overview): GDP, population, employment, price indices
2. **农业** (Agriculture): Crop production, livestock, fisheries
3. **工业和建筑业** (Industry and Construction): Output, key products
4. **服务业** (Services): Value-added by sector
5. **国内贸易** (Domestic Trade): Retail sales, consumer goods
6. **固定资产投资** (Investment): Fixed asset investment by sector
7. **对外经济** (Foreign Trade): Exports, imports, FDI
8. **交通运输** (Transportation): Cargo, passenger volumes
9. **金融** (Finance): Deposits, loans, securities, insurance
10. **人民生活** (Living Standards): Income, consumption, social security
11. **教育科技** (Education and Technology): Schools, R&D spending
12. **卫生文化** (Health and Culture): Hospitals, cultural facilities
13. **资源环境** (Resources and Environment): Energy, environment protection

## Technical Notes

- The site uses GBK/GB2312 encoding; the skill automatically detects and decodes
- Content is embedded in nested table structures; the skill extracts from the largest relevant table
- Data tables within the text are identified by markers like "表1", "表2"
- Section headers use Chinese numerals (一, 二, 三, etc.)