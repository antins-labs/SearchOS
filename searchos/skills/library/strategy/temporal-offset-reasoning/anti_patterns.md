# Anti-patterns — temporal_offset_reasoning

## Index
- **单次搜索解时间推理** — 跨文档时间逻辑塞一个 query (×1, 2026-04-18)
- **未验时间可行性** — 搜尚未发生事件的结果 (×18, 2026-04-24)
- **过去/现在时态混淆** — 退役运动员当现役查 (×1, 2026-04-18)
- **锚点行政区划不匹配** — D.C. 不是州却按州查 (×1, 2026-04-18)
- **最近事件用二级源** — 事件刚发生就搜 news/report 有延迟 (×1, 2026-04-19)
- **多跳历史+生平链不分解** — 4-hop 问题一条 query 搜 (×1, 2026-04-18)

## Details

### 单次搜索解时间推理
**踩坑**: 构造 `"What painting was stolen from The Louvre exactly 56 years before the birth date of Serj Tankian"` 期望一次搜出结果
**原因**: 搜索引擎无法同时执行实体属性查找 + 跨文档时间逻辑推理
**改用**: 分步策略——先搜 `Serj Tankian birth date` 得 1967；本地计算 1967-56=1911；再搜 `Louvre painting stolen 1911`；永不让搜索引擎"理解"相对时间
**观察**: 1 次  |  **最后**: 2026-04-18

### 未验时间可行性
**踩坑**: 面对 "ACL 2026 论文"（在 2026-04 查询时会议尚未召开、论文集不存在）、"2027 会议结果" 这类**目标时间点尚未发生**的查询，直接以「论文」为关键词搜索甚至 dispatch 8 个并行 agent 搜 "不存在的数据"；各种变体包括 future conference papers / future event concrete data / future-dated acceptances
**原因**: 未做 temporal feasibility check；把 "2026 会议" 当作已发生处理；会议尚未召开时正式论文集不存在，录用名单仅散见于各实验室公众号/官网，无集中索引；搜索引擎无法返回尚不存在的数据，只能给出噪声或幻觉
**改用**: Step 0 必做——比较 target_time vs today。Target_time > today 时：(1) 立即返回"该事件尚未发生"；(2) 核对会议生命周期（submission → notification → conference），若在 notification 前告知"accepted list 尚未发布"，若在 notification 后、conference 前改搜「accepted papers list」「录用通知」「acceptance announcement」；(3) 若无可信来源应明确告知用户该信息可能尚未公开，而非反复尝试无效搜索；(4) 若非要数据则 pivot 到最近一届历史数据（ACL 2025 录用）或 CFP/submission statistics
**观察**: 18 次  |  **最后**: 2026-04-24  |  **来源**: "ACL 2026/2027 NLP 组录用情况（同 trace 多次 mine）"

### 过去/现在时态混淆
**踩坑**: 查到某人已退役就停止，没追溯其在职时的信息；但问题问的是"当时属于哪个队"而非"现在属于哪个队"
**原因**: Agent 未显式区分"过去状态"和"现在状态"；退役/卸任信息把 agent 当前时态思维锁住
**改用**: 问题涉及"当时的/前任的"表述时，显式回溯到目标时段的在职状态；以"YYYY 年在职期" 为约束重搜
**观察**: 1 次  |  **最后**: 2026-04-18

### 锚点行政区划不匹配
**踩坑**: 锚点定位到 Washington D.C.，但查询要求"同一个州的事件"，D.C. 不是州
**原因**: 模板假设锚点位置在某个州内，未考虑联邦特区/特别行政区等非州单位
**改用**: 检测到非标准行政区划（D.C.、Hong Kong、自治区等）时显式改用大都会区域/相邻州/国家级查询范围
**观察**: 1 次  |  **最后**: 2026-04-18

### 最近事件用二级源
**踩坑**: 事件 anchor date 刚过（<2 周），立即搜 Official News / University Announcements 等二级聚合源
**原因**: 二级源有 days-to-weeks 延迟；原始源（OpenReview 录用列表、官方 program、lab Twitter 实时频道）比二级聚合快得多
**改用**: 计算 delta = today − anchor_date。delta 小（<2 周）时优先搜 primary source（OpenReview、官方 program、lab X/Weibo 实时频道），而非 static news 页
**观察**: 1 次  |  **最后**: 2026-04-19  |  **来源**: "ACL 2026 事件刚发生查录用"

### 多跳历史+生平链不分解
**踩坑**: 4-hop 问题（"1920 年代上海刊物 → 领导运动的高校 → 21 世纪少儿剧中的演员 → 男一号结婚日期"）作为一条原始 query 直接搜，返回 0 evidence
**原因**: 搜索引擎无法跨 4 个 disparate 领域（历史事件 → 院校 → 童星 → 婚姻日期）一次推理；每 hop 需要独立 anchor-and-propagate
**改用**: 强制分解——(1) reverse_clue_search 锁 1920s 刊物和学生运动；(2) list_table_extraction 抽领导高校；(3) temporal_offset_reasoning 定 21 世纪初童星校友；(4) data_spec_retrieval 查男一号婚姻日期。每 hop 独立执行
**观察**: 1 次  |  **最后**: 2026-04-18  |  **来源**: "20 年代上海刊物多跳链"
