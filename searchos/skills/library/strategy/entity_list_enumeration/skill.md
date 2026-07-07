---
name: entity_list_enumeration
description: 针对需要列举多个实体（如作品列表、获奖名单）的任务，通过定位权威聚合页（如Wikipedia）提取结构化表格，避免陷入逐个搜索的死循环。
trigger: 当用户请求“列出所有...”、“...有哪些”、“...的列表”或需要统计某类实体数量，且预期结果包含多个条目时。
success_rate: 0.0
status: seed
---

## 目标
解决Agent在面对“列举类”问题时，容易陷入逐个检索实体或反复进行无效搜索的死循环。本技能旨在引导Agent优先寻找包含完整信息的聚合页面，直接提取结构化列表（如Wiki表格），一次性解决任务。

## 适用场景
1.  **作品检索**：查询某导演的电影列表、某歌手的专辑列表、某作家的书单。
    *   *例：List all video games directed by Hideo Kojima.*
2.  **成员/组成部分**：查询某乐队的成员、某公司的子公司、某国家的省份。
    *   *例：Members of the Beatles.*
3.  **记录/奖项**：查询某奖项的历年得主、某球队的历史战绩。
    *   *例：List of Nobel Prize winners in Physics.*

## 核心原则
1.  **聚合优先**：严禁针对单个实体进行逐个搜索。必须优先搜索能够包含所有目标实体的“容器页面”（如Wikipedia、IMDb、Fandom）。
2.  **关键词修饰**：搜索词必须包含暗示“集合”或“列表”的修饰词（如 "list", "filmography", "discography", "wiki", "all"）。
3.  **结构化提取**：打开页面后，优先定位 `<table>`、`<ul>` 等结构化标签，而非阅读正文段落。
4.  **直达而非探索**：对于知名实体，严禁执行“探索是否存在列表”或“确定信息源”的预热步骤。应默认权威列表（如Wikipedia Filmography）存在，直接构建查询并访问，避免因探索导致的搜索死循环。

## 执行流程
1.  **查询构建**：
    *   将原问题转换为集合查询。
    *   **零探索原则**：若实体具有高知名度，跳过“寻找来源”的步骤，直接搜索具体页面。
    *   *错误*：`search "Hideo Kojima games"`
    *   *正确*：`search "Hideo Kojima video games list wiki"` 或 `search "Hideo Kojima filmography"`
2.  **目标筛选**：
    *   在搜索结果中，优先选择标题包含 "List of...", "Filmography", "Discography", "Wikipedia" 的链接。
    *   忽略新闻文章、单个作品介绍页或 Top 10 排行榜文章。
3.  **页面打开与定位**：
    *   打开权威聚合页（通常是 Wikipedia 或专业数据库站）。
    *   使用 `find` 功能定位页面中的表格区域（如寻找 "Games" 或 "Filmography" 章节标题下的表格）。
4.  **批量提取**：
    *   从表格或列表中提取所有实体名称。
    *   如果表格跨页或折叠，需确保完整性。

## 常见误区

*   **场景**：试图通过多次搜索单个实体来拼凑列表。
    *   ❌ **踩坑**：`search "Hideo Kojima first game"`, `search "Hideo Kojima second game"`... 导致 `dispatch_budget_exhausted` 且覆盖率低。
    *   ✅ **应改用**：`search "Hideo Kojima gameography"` 直接获取完整列表。

*   **场景**：打开了新闻文章或博客而非数据百科。
    *   ❌ **踩坑**：打开 "Top 5 Hideo Kojima Games" 的文章，导致列表不完整。
    *   ✅ **应改用**：打开 "Hideo Kojima filmography - Wikipedia" 页面。

*   **场景**：在页面内盲目浏览正文。
    *   ❌ **踩坑**：阅读长段落文本尝试寻找游戏名，效率极低且易遗漏。
    *   ✅ **应改用**：直接查找 `<table>` 元素或 "Games developed" 章节。

*   **场景**：试图“探索”来源而非“直达”来源。
    *   ❌ **踩坑**：执行 `task="探索...确定是否有完整列表"`。对于知名实体（如Christopher Nolan），这种探索性任务极易导致 `NO_PROGRESS` 和 `SEARCH_LOOP`，因为Agent在没有具体提取目标的情况下反复搜索。
    *   ✅ **应改用**：直接假设权威页面存在，执行 `search "Christopher Nolan filmography wiki"` 并立即进入提取阶段。