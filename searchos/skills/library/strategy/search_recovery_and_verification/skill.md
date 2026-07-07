---
name: search_recovery_and_verification
description: 搜索失败恢复与结果验证——结果过多 / 过少 / 过时 / 冲突 / 漂移
trigger: 当前搜索出现以下任一情况——结果过多（噪声）、过少（零命中）、过时、跨源冲突、命中偏离原意（语义漂移）
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
统一处理 5 类异常：noise（过多）、empty（过少）、stale（过时）、conflict（冲突）、drift（漂移）。提供分类诊断与对应恢复动作。

## 适用场景
- 发出 query 后结果不可用
- 结果之间互相矛盾
- 结果与问题原意已经偏离

## 规则（共 14 条）
1. **失败先分类**：noise / empty / stale / conflict / drift 五类，不同类对应不同恢复路径。
2. **noise → 收紧约束**：加 `site:` / 引号 / 时间窗 / 排除词，不要换 query。
3. **empty → 放宽约束**：去掉某个修饰词、换上位词、换语种；逐项放宽而不是一次全放。
4. **stale → 加时间约束**：`after:YYYY` / changelog / latest version doc。
5. **conflict → 看权威等级**：官方 > 学术 > 二手；权威等级相同时选时间最近。
6. **drift → 重写 query**：drift 是词义偏差信号，必须 rewrite 而不是继续加 query。
7. **rewrite 至少改两件事**：术语 + 语种、或 术语 + 问法；只改一项几乎无效。
8. **连续 3 次无新证据触发停损**：回到 plan，重新选搜索面或拆问题。
9. **每条候选答案必须 ≥ 2 个独立来源**：避免单源孤证。
10. **来源独立性判定**：同 vendor 不同页 ≠ 独立；不同 vendor 才独立。
11. **时间一致性校验**：所选证据的时间戳要落在问题约束的时间窗内。
12. **数值字段单位回检**：跨源数值在合并前必须单位统一。
13. **保留矛盾证据**：发现冲突时记录所有候选与各自来源，不要静默丢弃少数派。
14. **finalize 前抽样复读 ≥ 10%**：随机抽样重新打开来源验证，错误率 > 5% 整轮回退。

## 执行流程
1. 失败分类。
2. 套对应恢复动作。
3. 收敛后做来源独立性 + 时间 + 单位三项校验。
4. finalize 前抽样复读。

## 关联 skill
- `general_query_construction` — rewrite 时回流上游
- 各搜索面 skill — 分类后选回对应面再执行
