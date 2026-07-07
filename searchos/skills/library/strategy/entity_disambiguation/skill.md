---
name: entity_disambiguation
description: 当问题中的实体存在同名、拼写近似或信息冲突时，通过精准检索与交叉验证锁定唯一正确实体。
trigger: 当问题包含人名、地名、机构、作品等实体，且该实体可能与其他同名或近似实体混淆（如“James Andrew Miller” vs “James Andrews
  Miller”），或需要区分同名不同人/事物时。
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - entity
  - person
  - organization
  attribute_types:
  - canonical_name
  - identifier
  coverage_gap_pattern: ambiguous_entity_reference
cost_hint: mid
effectiveness_score: 0.0
---

# entity_disambiguation

## 目标
解决“同名异义”或“拼写近似”导致的实体识别错误问题。通过构造高区分度的查询、利用权威来源（维基百科、官方文档、权威数据库）和交叉验证关键属性（职业、时间、地点、成就、关联实体），确保锁定唯一正确的实体。

## 适用场景
- 人名：找出“James Andrew Miller（记者）”而非“James Andrews Miller”或同名运动员。
- 机构/节目：确认“Hee Haw”是 Roy Clark 主持的国家乡村综艺节目，而非“The Roy Clark Show”。
- 赛事：区分“Queensland Head of the River”与其他州的同名赛艇赛事。
- 作品：定位“Those Guys Have All the Fun: Inside the World of ESPN”的作者身份。
- 地名：确认“Balneário Camboriú”在巴西而非其他同名地点。

## 不适用场景
- 问题已给出唯一且明确的实体标识（如 ISBN、ORCID、官方 URL）。
- 仅需统计或计算，不涉及实体唯一性判断（如“1995-96 赛季公牛队 113-87 比分出现次数”）。
- 实体本身无歧义，仅需检索属性（如“瑞士某公司 200 单位收入 CHF500,000”）。

## 核心原则
1. **高区分度查询**：在搜索中加入“职业、时间、地点、成就、关联实体”等限定词，最大限度缩小范围。
2. **权威来源优先**：优先使用维基百科、官方站点、权威数据库（IMDb、Sports-Reference、DBLP）作为验证基准。
3. **交叉验证**：至少两个独立来源对同一关键属性（出生日期、职务、作品列表）给出一致信息，才视为确认。
4. **迭代澄清**：若首轮结果仍含歧义，追加更细粒度限定（如“not the footballer”、“born 1960”）直至唯一。

## 标准执行流程
1. **识别歧义点**  
   判断实体是否可能同名、拼写近似或跨领域重名，列出潜在混淆对象。
2. **提取区分属性**  
   从问题中提取可唯一标识该实体的属性：职业、国籍、时间段、代表作品、关联人物/机构。
3. **构造首轮精准查询**  
   将实体名与区分属性组合成查询，如 `"James Andrew Miller" journalist ESPN author`。
4. **锁定权威页面**  
   优先打开维基百科、官方传记、IMDb、DBLP 等页面，快速定位 infobox 或首段关键信息。
5. **交叉验证关键事实**  
   用第二来源（新闻报道、官方公告、学术主页）验证出生日期、职务、作品列表等。
6. **处理剩余歧义**  
   若仍有冲突，追加限定词（“not the actor”、“born 1972”）或反向排除（`-football -soccer`）。
7. **确认唯一实体**  
   当所有关键属性在多源一致且无冲突时，标记该实体为最终答案。
8. **记录标识符**  
   将维基百科 URL、ORCID、IMDb ID 等唯一标识附在答案后，方便后续引用。

## 检索策略模板
- 人名：`"{Full Name}" {profession} {key_work_or_affiliation} site:wikipedia.org`
- 作品/节目：`"{Title}" {host_or_creator} {genre} {year} site:imdb.com OR site:wikipedia.org`

