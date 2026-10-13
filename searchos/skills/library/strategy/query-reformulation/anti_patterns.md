# Anti-patterns — query_reformulation

## Index
- **问题复制** — 把原始问题整句粘贴当 query (×2, 2026-04-18)
- **过度指定** — 查询词 >8 词，限定修饰堆砌 (×1, 2026-04-18)
- **同义/重复重试** — 换词序不换角度 (×2, 2026-04-23)
- **语言错配** — 中文内容用英文查询或反之 (×1, 2026-04-18)
- **一步到位** — 单查询想拿所有字段 (×1, 2026-04-18)
- **全景式聚合** — 期待单一 omnibus 汇总页 (×2, 2026-04-18)
- **搜后不读** — 连续 search 不 open 提取 evidence (×1, 2026-04-23)
- **缺时间感知** — 对未发布的会议论文直搜 (×1, 2026-04-20)

## Details

### 问题复制
**踩坑**: 把原始问题（有时是整段多实体多属性问句）直接作为 query，如 "Provide a complete list of all video games where Hideo Kojima acted as designer, director, or producer"
**原因**: Golden Document Fallacy——假设存在一个黄金文档能直接回答问题；搜索引擎是关键词匹配系统不是问答系统，长句命中率接近 0
**改用**: 提取 1-2 个最具区分度的核心实体做 query（`Hideo Kojima filmography` 或 `Hideo Kojima games list site:en.wikipedia.org`），去掉所有修饰词
**观察**: 2 次  |  **最后**: 2026-04-18  |  **来源**: "SUPPLY project EHA funding"

### 过度指定
**踩坑**: 查询词 >8 个词堆砌修饰（如 `fastest production street legal cars Nürburgring Nordschleife lap times 2024 official records`，17 词）
**原因**: 搜索引擎在关键词过多时匹配质量急剧下降，返回文档可能不包含任何一个完整匹配
**改用**: 关键词 ≤6 个；用 `site:` 和引号替代额外关键词做精确定位（`site:en.wikipedia.org "Nürburgring Nordschleife lap times"`）
**观察**: 1 次  |  **最后**: 2026-04-18

### 同义/重复重试
**踩坑**: 上次搜索无果后只换词序/同义词重搜（`Canada population by year male female 2014-2024` → `Canadian annual population statistics gender 2014 to 2024`）；触发 NO_PROGRESS / SEARCH_LOOP
**原因**: 问题不在措辞，而在搜索角度或信息源；同义重试烧 budget 不解决根本
**改用**: 连续 2 步无进展立刻切角度：换源 `site:statcan.gc.ca`、换语言（中英双语）、换维度、换实体粒度
**观察**: 2 次  |  **最后**: 2026-04-23  |  **来源**: "2024 BYD Tesla 销量"

### 语言错配
**踩坑**: 搜中国 NLP 研究组的发表情况却用英文 query `Chinese NLP research groups ACL 2026 papers`
**原因**: 中文内容的官方源、新闻稿多用中文标题；英文 query 无法命中中文专业页面
**改用**: 根据目标内容原始语言选择 query 语言；跨语言场景用双语查询（`ACL 2026 论文列表` + `ACL 2026 accepted papers list site:aclweb.org`）
**观察**: 1 次  |  **最后**: 2026-04-18

### 一步到位
**踩坑**: 试图在一次搜索中获取多个实体/字段（`Tesla BYD 2024 revenue comparison annual report`）
**原因**: 信息天然分布在不同来源（SEC filing vs 中国财报），强行合并降低每个维度的匹配质量
**改用**: 每个查询聚焦一个实体或一个维度；`Tesla 2024 annual revenue 10-K SEC filing` 和 `BYD 2024 年报 营业收入` 分开查
**观察**: 1 次  |  **最后**: 2026-04-18

### 全景式聚合
**踩坑**: 对"列举所有/主要"类任务用单一 query 想拿全景（`国内主要 NLP 研究组 ACL 2026 论文发表情况汇总`、`Chinese EV models released 2022-2025 complete list`）
**原因**: Golden Document Fallacy 的极端形式；此类信息碎片化分布在各机构官网/公众号，极少有官方"全景汇总"页；单一宽泛 query 返回噪声或陷入死循环
**改用**: Decomposition-for-Aggregation——先枚举实体（搜 `ACL 2026 accepted papers China` 或已知列表），再对每个实体发独立并行查询（`THUNLP ACL 2026 papers`、`北京大学 DLIB ACL 2026 papers`）
**观察**: 2 次  |  **最后**: 2026-04-18  |  **来源**: "ACL 2026 国内研究组"

### 搜后不读
**踩坑**: 搜索返回潜在相关结果后，继续重新 reformulate query，而不是 open 已经看到的 hit 提取 evidence（连续 2+ search 不夹 open）
**原因**: 把"换 query"当成进度本身，搜索-只 loop 烧 budget 且不推进 state
**改用**: Enforce search-then-read——任何 search 后若结果相关立刻 open 至少 1-2 个源；只有结果明显无关才允许连续 search 换方向
**观察**: 1 次  |  **最后**: 2026-04-23  |  **来源**: "Nobel Peace Prize while serving"

### 缺时间感知
**踩坑**: 搜会议论文/时敏学术信息时不核实信息是否已发布（ACL 2026 在 4 月时 accept notification 还没出）
**原因**: 缺对学术会议生命周期（submission → review → acceptance → camera-ready → conf）的时间感知；继续搜只能拿到推测/占位内容
**改用**: 先核对会议日历与当前日期；未发布的 data 转搜实验室官网 News/Publications、arXiv 预印本、公众号喜报；或告知用户该数据尚未公开
**观察**: 1 次  |  **最后**: 2026-04-20  |  **来源**: "ACL 2026 NLP 组"
