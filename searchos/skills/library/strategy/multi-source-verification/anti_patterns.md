# Anti-patterns — multi_source_verification

## Index
- **不验存在性就搜属性** — 把"找不到"当"关键词不准" (×1, 2026-04-18)
- **直接搜多源交集** — NO_PROGRESS + SEARCH_LOOP (×1, 2026-04-18)
- **直接搜特定子集** — 互联网没维护此交集页 (×1, 2026-04-18)
- **复杂布尔搜索串** — 长 AND/OR 查询搜索引擎不稳定 (×1, 2026-04-18)
- **未拆分原子事实** — 多事实问题一次性搜 (×1, 2026-04-18)
- **单源未交叉确认** — 首结果直接当答案 (×1, 2026-04-18)
- **缺 temporal overlap 验证** — 授荣誉/任职时间未对齐 (×3, 2026-04-18)
- **假定 anchor fact 为真** — 未验证前提条件本身 (×1, 2026-04-18)

## Details

### 不验存在性就搜属性
**踩坑**: 搜"2023 年韩国伍德斯托克音乐节"的演出阵容，前几个链接只有社交媒体讨论，继续变换 `lineup` `performers list` 关键词，默认实体存在
**原因**: 将"找不到信息"归因为"关键词不准"，忽略了"实体可能根本不存在"这个强信号
**改用**: 先走否定性验证：搜 `[entity] cancelled` / `[entity] fake OR hoax`；若找到辟谣/取消公告立即终止
**观察**: 1 次  |  **最后**: 2026-04-18

### 直接搜多源交集
**踩坑**: 连续 3+ 次搜"既在 Billboard 榜单上又获得 MTV 提名的歌曲"，触发 NO_PROGRESS 和 SEARCH_LOOP 最终 DAG_FAIL
**原因**: 搜索引擎索引中不存在直接包含该特定交集的页面；单次搜索无法合成交集
**改用**: 立即拆分为两个子任务：分别获取 Billboard 完整榜单 + MTV 提名完整列表；在 Python 里做交集
**观察**: 1 次  |  **最后**: 2026-04-18

### 直接搜特定子集
**踩坑**: 搜 `"Nobel Peace Prize laureates who were heads of state"`
**原因**: 互联网极少维护这类特定交集的页面；搜索结果噪声大或根本没有
**改用**: 搜 `"List of Nobel Peace Prize laureates"` 拿超集全量列表，再本地筛选"曾任国家元首"
**观察**: 1 次  |  **最后**: 2026-04-18

### 复杂布尔搜索串
**踩坑**: 使用极长搜索串如 `"Billboard Global 200 AND MTV EMA nominees AND 2020..2022"`
**原因**: 搜索引擎对复杂布尔逻辑支持不稳定，容易漏掉数据；且命中率骤降
**改用**: 分别搜两个源的完整列表，本地 Python 环境做精确过滤
**观察**: 1 次  |  **最后**: 2026-04-18

### 未拆分原子事实
**踩坑**: 问题含多个独立事实（"第 15 任 first lady""第二位被刺杀总统""母亲婚前姓"），发 broad undifferentiated search 想一次解决
**原因**: 搜索引擎无法从单一 query 推理出嵌套关系（ordinal → person → mother → maiden name）；每个事实需要独立锁定
**改用**: 拆成原子事实，每个通过权威源（如 White House 历史列表）单独验证；前一个确认后才链到下一个
**观察**: 1 次  |  **最后**: 2026-04-18  |  **来源**: "future wife name 15th first lady mother"

### 单源未交叉确认
**踩坑**: 单次搜索返回 "Calvert" 就直接作为答案输出，没验证 Calvert 是否是 county、SMECO 总部是否确实在 Calvert County
**原因**: 未做 cross-checking；模型接受了第一个看起来合理的字符串
**改用**: 单源命中后至少用第二个独立源核实关键属性（Calvert 是否是 Maryland 的 county + SMECO 的 HQ 是否在 Calvert）
**观察**: 1 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining"

### 缺 temporal overlap 验证
**踩坑**: 问题要求"授荣誉时正在任某职"，却只检查"曾经任过该职 + 曾经拿过该奖"两个独立事实，漏掉"两者同时成立"的约束
**原因**: 一生传记把任职期跨度压缩，easy 放进假阳性——某人任总理后 10 年才获奖也被算入
**改用**: 为每个候选同时取"授奖精确日期"和"任职 start-end 区间"，离线检查日期落在区间内；不重叠则淘汰
**观察**: 3 次  |  **最后**: 2026-04-18  |  **来源**: "Nobel Peace Prize while serving"

### 假定 anchor fact 为真
**踩坑**: 问题带了一个 anchor fact（如"Lorentz 是 Rijke 的学生"），代理接受此前提直接搜下游属性
**原因**: anchor fact 本身可能是错的/未验证；跳过前提验证让错误传导到整个链
**改用**: 追下游属性前先用 2+ 独立源验证 anchor（`"Was Lorentz Rijke's student?"`）；anchor 被否就 pivot 整个策略
**观察**: 1 次  |  **最后**: 2026-04-18  |  **来源**: "doctoral students of Pieter Rijke Nobel"
