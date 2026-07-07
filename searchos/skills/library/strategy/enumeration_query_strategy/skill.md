---
name: enumeration_query_strategy
description: 针对枚举类问题（如作品列表、成员名单）的搜索策略，旨在通过定位权威聚合页避免搜索死循环。
trigger: 当任务要求列出某实体的多项属性（如“所有作品”、“历任成员”）且当前搜索陷入停滞或无进展时。
success_rate: 0.0
status: seed
---

## 目标
解决Agent在面对“列举所有X”类型问题时，因缺乏明确目标源而陷入搜索死循环（Search Loop）或因预算耗尽导致0覆盖率的问题。本技能指导Agent快速定位包含完整列表的权威聚合页面（如Wikipedia列表页、IMDb、MobyGames），以最小成本获取最大信息量。

## 适用场景
*   **作品列表查询**: 查询某导演、作家、设计师的所有作品（如“Hideo Kojima的游戏作品”、“Stephen King的书单”）。
*   **成员名单查询**: 查询某组织、乐队的历任成员。
*   **奖项/事件枚举**: 查询某奖项的历届得主或某类历史事件列表。
*   **特征**: 目标信息通常集中在Wikipedia的“作品目录”章节、专业数据库（IMDb, MobyGames）或官方传记页面。

## 核心原则
1.  **聚合优先**: 优先搜索包含“list”、“filmography”、“discography”、“works”、“credits”等聚合性关键词的页面，避免逐个搜索单项。
2.  **权威源锁定**: 优先访问Wikipedia、IMDb、MobyGames、Goodreads等已知的高质量数据库，而非零散的新闻文章或博客。
3.  **死胡同即转**: 遇到页面无列表或连续2次操作无进展，必须立即更换搜索关键词或数据源，禁止原地重复操作。

## 执行流程
1.  **构造聚合查询**:
    *   构造搜索词：`[实体名] + [works/list/filmography/discography]`。
    *   示例：`Hideo Kojima games list` 或 `Hideo Kojima filmography`。
2.  **筛选权威节点**:
    *   在搜索结果中优先点击 Wikipedia（特别是带有 "Works" 或 "Discography" 子页面）、IMDb、MobyGames 等域名。
    *   避免点击缺乏结构化数据的新闻通稿或单一作品介绍页。
3.  **定位与提取**:
    *   打开页面后，使用 `find` 定位列表区块（如“Video games”、“Directed by”表格）。
    *   批量提取列表项，确保覆盖全面。
4.  **失败回退**:
    *   若首选源（如Wikipedia）内容不全或无法访问，立即切换第二梯队源（如 `[Entity] site:imdb.com` 或 `[Entity] site:mobygames.com`）。

## 常见误区

*   **场景**: 搜索结果不理想或打开的页面无目标列表。
    *   ❌ **踩坑**: 重复执行相同的搜索命令，或在无关页面反复查找（导致 `NO_PROGRESS` 和 `SEARCH_LOOP`）。
    *   ✅ **应改用**: 立即修改搜索关键词，添加特定站点限制（如 `site:wikipedia.org`）或更换数据库关键词（如将 "games" 改为 "credits"）。

*   **场景**: 需要枚举大量条目。
    *   ❌ **踩坑**: 试图逐个搜索每个作品名称来拼凑列表，迅速耗尽预算。
    *   ✅ **应改用**: 坚持寻找“总表页”或“作品目录页”，一次性获取所有条目。

*   **场景**: 页面包含多个分类（如Director, Producer, Writer）。
    *   ❌ **踩坑**: 仅提取第一个可见列表，遗漏其他分类下的作品。
    *   ✅ **应改用**: 扫描整个页面结构，确认所有相关分类（如 "Game Design", "Writing"）均已覆盖。