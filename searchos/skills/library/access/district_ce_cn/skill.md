# district.ce.cn - 地方党政领导人物库

中国经济网地方经济频道 (district.ce.cn) 的党政领导信息获取技能。

## 功能概述

该技能可从 district.ce.cn 获取以下内容：

### 1. 人事任免文章 (fetch_article)
获取领导任免新闻文章，自动提取：
- 文章标题和正文
- 发布日期、作者、来源等元数据
- **结构化简历信息**：
  - 姓名、性别、民族
  - 出生年月、籍贯
  - 学历、政治面貌
  - 现任职务
  - 完整职业生涯履历（日期范围 + 职位描述）

**适用 URL 格式**：
- `http://district.ce.cn/newarea/sddy/YYYYMM/DD/tYYYYMMDD_XXXXXXX.shtml`
- 如：`http://district.ce.cn/newarea/sddy/202303/02/t20230302_38421268.shtml`

### 2. 领导干部数据库 (fetch_leadership_db)
获取各省地市领导干部数据库页面，提取：
- 地区列表（地市、州、地区）
- 各地区党委书记姓名及链接
- 各地区市/州长（行署专员）姓名及链接
- 最新人事动态更新

**适用 URL 格式**：
- `http://district.ce.cn/zt/rwk/sf/{省份}/ds/YYYYMM/DD/tYYYYMMDD_XXXXXXX.shtml`
- 如：`http://district.ce.cn/zt/rwk/sf/xj/ds/201206/14/t20120614_1269253.shtml`（新疆）

### 3. 页面类型检测 (detect_page_type)
自动检测给定 URL 的页面类型，推荐合适的抓取函数。

## 使用示例

### 获取领导简历
```
参数：
{
  "function": "fetch_article",
  "url": "http://district.ce.cn/newarea/sddy/202303/02/t20230302_38421268.shtml"
}

返回：
{
  "success": true,
  "title": "张胜源当选海北州州长(图|简历)",
  "meta": {
    "publish_date": "2023-03-02 10:47:00",
    "author": "尹彦宏",
    "source": "中国经济网综合"
  },
  "biographical_info": {
    "person_name": "张胜源",
    "gender": "男",
    "ethnicity": "藏族",
    "birth_date": "1972年4月",
    "native_place": "青海西宁",
    "education": "省委党校研究生学历",
    "position": "海北州州长",
    "career_history": [
      {"date_range": "1992.07--1993.05", "position": "青海省互助县五十乡政府干部"},
      {"date_range": "1993.05--1995.08", "position": "青海省互助县威远路桥公司干部"},
      ...
    ]
  }
}
```

### 获取地区领导名单
```
参数：
{
  "function": "fetch_leadership_db",
  "url": "http://district.ce.cn/zt/rwk/sf/xj/ds/201206/14/t20120614_1269253.shtml"
}

返回：
{
  "success": true,
  "title": "新疆各地书记、市/州长(行署专员)名单+简历（持续更新）",
  "region": "新疆",
  "leader_count": 14,
  "leaders": [
    {
      "region": "乌鲁木齐市",
      "secretary": "张柱(兼)",
      "secretary_url": "http://...",
      "head": "牙合甫·排都拉",
      "head_url": "http://..."
    },
    ...
  ]
}
```

## 数据来源

- 网站名称：中国经济网 - 地方经济频道
- 网站 URL：http://district.ce.cn
- 数据类型：地方政府党政领导人物库
- 更新频率：实时更新，随人事变动持续调整

## 注意事项

1. 简历数据通过模式匹配提取，可能存在部分信息未能识别的情况
2. 领导名单页面会持续更新，返回的数据反映抓取时的最新状态
3. 人物链接指向最新的相关报道或简历页面，可能需要进一步抓取获取详细简历
4. 部分老旧页面格式可能略有不同，提取结果可能有差异

## 技术说明

- 采用 aiohttp 异步 HTTP 请求，无需浏览器自动化
- 使用 BeautifulSoup 进行 HTML 解析
- 支持完整的 Unicode 中文字符处理
- 自动处理页面编码（UTF-8）