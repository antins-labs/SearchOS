# Anti-patterns — ranking_top_n

## Index
- **一步到位搜榜+属性** — 通用搜索期待单查询返榜单+所有字段 (×1, 2026-04-18)
- **拼榜时间不一致** — 榜单+属性来自不同快照 (×1, 2026-04-18)
- **无锁榜步骤/zero-steps** — 不识别为 ranking 任务或迭代搜不锁榜 (×3, 2026-04-18)
- **模糊版本** — 911 GT3 没指定 991/992 (×1, 2026-04-18)
- **未锚定官方 aggregator** — 不搜官方录用/meta list 先行 (×3, 2026-04-19)
- **未锁官方榜就补字段** — 跳过 Top-N 锁定直接 enrich (×2, 2026-04-18)
- **Niche 域不用专业源** — 冷门榜单用通用搜索 (×1, 2026-04-23)
- **动态页解析 stall** — 官方 live 页 heavy script 抽取失败 (×1, 2026-04-23)

## Details

### 一步到位搜榜+属性
**踩坑**: 搜 `top 5 fastest production cars Nürburgring wheelbase` 或 `全球市值前3 科技公司 CEO 薪酬` 期望一次返完整榜单+附加字段
**原因**: 返回的媒体文章混杂改装车/过时数据；附加属性不在搜索摘要中
**改用**: 分两步——先 `site:en.wikipedia.org "List of Nürburgring Nordschleife lap times"` 锁榜，再逐车型查官方规格
**观察**: 1 次  |  **最后**: 2026-04-18

### 拼榜时间不一致
**踩坑**: 用 Bloomberg 榜单 + Wiki 属性 → 可能把"上周榜"配上"去年薪酬"
**原因**: 不同源快照时间不同，市值/排名已变动；拼接产生不存在的组合
**改用**: 锁榜和补字段都注明数据截止时间，整个流程内使用同一快照
**观察**: 1 次  |  **最后**: 2026-04-18

### 无锁榜步骤/zero-steps
**踩坑**: 面对明显 ranking 任务（如"2023/24 Premier League top 15 goals"）要么 0 步不动，要么迭代搜索 + 逐页打开但没有明确的"锁定列表"步骤
**原因**: 没把问题识别为 ranking 任务；或动态排名数据分散，通用搜索结果不一致导致搜索循环
**改用**: 一看到 "Top N" / "ranked" / "榜" 立即走 ranking_top_n 流程：先搜权威官方源（年报、交易所文件、Wiki 表格、联赛官方 stats）锁定完整列表，再补字段
**观察**: 3 次  |  **最后**: 2026-04-18  |  **来源**: "Premier League top 15 goals"

### 模糊版本
**踩坑**: 搜 `911 GT3 wheelbase` 未指定具体版本
**原因**: 同名系列含多个子型号（991/992/RSR），参数不同
**改用**: 使用官方榜单中的精确名称如 `911 GT3 RS (992) 2023`；必要时加年款/代号
**观察**: 1 次  |  **最后**: 2026-04-18

### 未锚定官方 aggregator
**踩坑**: 面对"ACL 2026 国内录用""mainstream NLP groups performance" 类 survey 任务，要么并行搜每个实体，要么广泛搜没先找聚合页
**原因**: 搜索引擎把 news/blog 排在官方列表前；权威 aggregator（conference 官方 accepted papers、行业 roundup 文章）通常一次给全集，不先锚就陷入 N 次独立搜索
**改用**: Step 1 必须是 `ACL 2026 accepted papers list site:aclweb.org` 或 `"ACL 2026 国内录用统计"`——找官方/行业聚合页，再 list_table_extraction + 过滤；只有聚合源缺失时才 fallback 单实体
**观察**: 3 次  |  **最后**: 2026-04-19  |  **来源**: "ACL 2026 国内主流 NLP 组"

### 未锁官方榜就补字段
**踩坑**: 要从 Top-N 列表过滤子集（如 "SIPRI Top 100 中的德国公司 + 成立日期"），跳过官方 PDF/Excel 下载直接搜单个公司；或者拿到榜单但对非 production 车型未过滤就追加 wheelbase
**原因**: 绕过 ranking_top_n 必须的第一步"锁定官方榜"——下游所有 query 都成了无根飘萍；也缺 categorical filter 导致 enrich 错数据
**改用**: 严格两步：(1) 先 `site:sipri.org "top 100" 2024 filetype:pdf OR filetype:xlsx` 拿全榜；(2) 按国家过滤 + 验证 production 限定，再 enrich 额外字段
**观察**: 2 次  |  **最后**: 2026-04-18  |  **来源**: "SIPRI Top 100 German companies"

### Niche 域不用专业源
**踩坑**: 冷门/专业 ranking（motorsport lap times、特定行业 leaderboard、regional records）用通用搜索 + 标准 reformulation，陷入循环
**原因**: Niche ranking 往往在专业爱好者站、行业出版物、官方组织数据库，不在通用搜索 top rank；标准 "search for ranking" 假设主流可见
**改用**: 先识别 domain-specific 权威源（Nürburgring 的 Bridge to Gantry、motorsport 的 FIA、industry association）；用已知源名 + 术语查询，或直接搜厂商新闻稿看 claimed time
**观察**: 1 次  |  **最后**: 2026-04-23  |  **来源**: "Top 5 production Nürburgring"

### 动态页解析 stall
**踩坑**: 打开官方联赛/榜单的 live 页，heavy JS/dynamic scripts 导致 extractor buffer_full / state_delta_stall / 0 evidence
**原因**: Live 页通过 dynamic scripts 呈现数据，抽取器无法解析；但同数据的历史版本往往以静态结构化表格存在于其他源
**改用**: 优先静态结构化源（Wiki 的 "X Season" 页、主要体育新闻 summary），用 `site:wikipedia.org [Season] [League] top scorers` 做 site-restricted 查询保证干净提取
**观察**: 1 次  |  **最后**: 2026-04-23  |  **来源**: "Premier League 2023/24 top 15"
