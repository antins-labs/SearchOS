# Anti-patterns — multi_hop_bridge

## Index
- **一次塞整个长问句** — 把多跳问题原样交给搜索引擎 (×1, 2026-04-18)
- **忽略歧义实体** — 不加限定词导致错实体 (×1, 2026-04-18)
- **忘记回代验证** — 第二跳结果没校验单位/归属 (×1, 2026-04-18)
- **停在中间 hop 不继续** — 只跑第一跳就提交答案 (×4, 2026-04-18)
- **过早融合下游约束** — 中间跳未解就带 final constraint 搜 (×2, 2026-04-18)
- **计划中途截断** — 书面 plan 被截，后续 hop 被悄悄丢 (×1, 2026-04-18)

## Details

### 一次塞整个长问句
**踩坑**: 直接搜 "Where is the place Norman Allen Adie moved to the United States to work at located in?"
**原因**: 搜索引擎对长问句近乎字面匹配，命中概率极低；也不利于拆分 hop
**改用**: 先拆链 "Norman Allen Adie work place" → 拿到 Los Alamos → 再搜 "Los Alamos National Lab location"
**观察**: 1 次  |  **最后**: 2026-04-18

### 忽略歧义实体
**踩坑**: 搜 "Christian Mann" 不加限定，结果混入同名足球运动员
**原因**: 首跳若抓错实体，后续所有 hop 都走偏
**改用**: 加职业/作品/时期限定，如 "Christian Mann character TV show"；必要时走一遍 entity_disambiguation
**观察**: 1 次  |  **最后**: 2026-04-18

### 忘记回代验证
**踩坑**: 找到"Hvalbiartunnilin cost 800 million"却未确认货币单位
**原因**: 每跳拿到数字没检查计量口径，最终答案可能差一个量级
**改用**: 每跳结果立即回代原问题校验单位、时间、归属；对数值类立即追问 "…cost DKK" 或 "…cost currency"
**观察**: 1 次  |  **最后**: 2026-04-18

### 停在中间 hop 不继续
**踩坑**: 拿到第一跳结果（如 person → birth country, performer → siblings, Olympics host → monarch）后停下不继续；或首跳返回"Caribbean"这种模糊区域就把它当终点
**原因**: 把多跳问题当单跳处理；或没识别问题需要 2-4+ hops；或遇模糊结果当 dead end 而不是 disambiguate
**改用**: 拆链前先数有几跳。每拿到一个结果立刻把它塞进下一跳的 query；遇模糊结果先 narrow（region → specific nation）再继续，绝不中途停
**观察**: 4 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining (consolidated 12+)"

### 过早融合下游约束
**踩坑**: 中间跳还没解就把它和 final constraint 合并成一次查询，例如搜 "husband in Movie X" 之前没先查出演员；或搜 "cast of The Wall" 之前没先定位是哪座 Wall
**原因**: 搜索引擎被迫同时猜中间实体 + 过滤 final constraint，结果要么噪声要么空
**改用**: 每跳独立——先定中间实体（演员 Y / 具体城市的 Wall），再单独搜 final 条件；绝不跳步合并
**观察**: 2 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining"

### 计划中途截断
**踩坑**: Agent 自己写的 plan 中途断开（"2. Id..." 然后停），后续 hop 被悄悄丢
**原因**: Plan 写不完就开执行，只执行了第一跳；表面上 plan 看起来完成但实际缺步
**改用**: 执行前先把完整 plan 写全（N 跳就写全 N 步），数一遍再执行；plan 截断时先补完再动手
**观察**: 1 次  |  **最后**: 2026-04-18  |  **来源**: "DPO dataset mining (consolidated 6+)"
