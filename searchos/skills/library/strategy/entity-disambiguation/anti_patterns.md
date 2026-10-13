# Anti-patterns — entity_disambiguation

## Index
- **人名裸搜** — 不加职业/限定词，结果混入同名实体 (×1, 2026-04-18)
- **未消歧义就假设属性** — 先锚定地点/年份再搜 (×2, 2026-04-18)
- **忽略反向排除** — 未用 `-keyword` 排除混淆项 (×1, 2026-04-18)
- **单来源即定论** — 只看一个博客就认定属性 (×1, 2026-04-18)
- **查询被截断** — 查询串中途断开失去精确匹配 (×4, 2026-04-18)

## Details

### 人名裸搜
**踩坑**: 直接搜 `"James Miller"`，结果混入运动员、演员、学者的条目
**原因**: 常见人名有多个知名同名实体，裸搜无法区分
**改用**: 加职业/作品/机构限定词，如 `"James Andrew Miller" journalist "Those Guys Have All the Fun"`
**观察**: 1 次  |  **最后**: 2026-04-18

### 未消歧义就假设属性
**踩坑**: 面对同名实体（"Peace Center"、"Mark Ross"）不先消歧义就直接假设地理范围（"Peace Center in the United States"）或赛季归属（"Mark Ross 2024 World Series"）
**原因**: 过早锚定隐含属性可能锁定错误实体；如果假设错了，下游的多跳推理全走歪
**改用**: 先用 `entity_disambiguation` 拿到候选实体的权威列表（维基百科 / Sports-Reference / IMDb），用最独特属性（州、位置、职位）确认唯一实体，再进入下游查询
**观察**: 2 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining"

### 忽略反向排除
**踩坑**: 搜 `"Roy Clark Show"` 未排除 "Hee Haw"，导致误认节目名
**原因**: 查询结果里最流行的同名/关联项会淹没目标，需要主动排除
**改用**: 加反向排除词 `"Roy Clark" country variety show -"Hee Haw"`，或 `"{entity}" -{混淆项}`
**观察**: 1 次  |  **最后**: 2026-04-18

### 单来源即定论
**踩坑**: 仅看一个博客就认定出生日期 / 出生地等关键属性
**原因**: 单源可能是谣传、UGC 或过时信息；尤其维基百科编辑战后不同版本的信息差异
**改用**: 至少核对 2 个独立权威来源（维基百科 + 官方传记 / 主流媒体报道 / 学术主页），冲突时溯源到原始文件
**观察**: 1 次  |  **最后**: 2026-04-18

### 查询被截断
**踩坑**: 搜索查询中途断开失去精确匹配，如 `"Find info about Eddie Newton, specifically which football team he was ass"`、`"Sara Hall ... I need to know wh"`、`"Hello Love performer who died and was connec"`
**原因**: 截断破坏实体消歧义所需的限定词，搜索引擎只看到前半段模糊名称，命中无关结果；且对 exact-match 要求的歌名/专有名词失效
**改用**: 发搜索前检查 query 完整性；专有名词、歌曲标题、完整问题用引号限定；不确定时重写为简短明确的 query 再发
**观察**: 4 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining"
