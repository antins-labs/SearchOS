---
name: canonical_list_extraction
description: 针对作品全集枚举任务，指导Agent优先定位并提取权威源（维基百科/专业数据库）中的结构化列表，避免碎片化搜索导致的预算耗尽。
trigger: 当任务要求列出某人的全部作品（游戏、电影、书籍、专辑）、完整履历或 credits 列表时。
success_rate: 0.0
status: seed
---

## 目标
解决Agent在执行“完整枚举”任务时，因缺乏明确的权威源导向，导致盲目打开多个低价值页面、陷入搜索循环并耗尽预算的问题。本技能旨在强制Agent优先锁定单一高密度信息源（如Wikipedia的主条目表格），实现“一次打开，完整提取”。

## 适用场景
- **游戏作品列表**: "列出小岛秀夫制作的所有游戏"、"Hideo Kojima gameography"。
- **影视作品列表**: "诺兰导演的电影列表"、"Leonardo DiCaprio filmography"。
- **出版物列表**: "Stephen King的书单"、"阿加莎·克里斯蒂作品年表"。
- **音乐专辑列表**: "Taylor Swift discography"。
- **游戏履历深度提取**: 需包含Demo、特别版或未公开发售作品的完整制作名单（如"Kojima productions credits"）。

## 核心原则
1. **权威源优先**: 首选 Wikipedia（通常包含完整的 Works/Table），其次选领域专用库（MobyGames, IMDb, Goodreads）。拒绝打开新闻文章、博客或零散论坛帖子。
2. **结构化定位**: 必须先找到具体的“列表章节”再进行提取，避免在人物简介中迷失。
3. **单源完整性**: 在一个高质量页面完成尽可能多的提取，仅在确认源数据缺失时才启用第二个源。
4. **禁止发散**: 严禁为了验证单一作品而单独搜索该作品名称，这会导致搜索爆炸。
5. **领域专用库优于通用百科**: 对于游戏等特定领域，MobyGames或专业Wiki（如Junker HQ）通常比Wikipedia包含更完整的Credits信息（含Demo、特别版），应优先或并行查询。
6. **并行冗余策略**: 面对高精度枚举任务（如要求包含Demo、重制版），应并行调度多个Agent分别查询不同权威源（如 Wikipedia + MobyGames + 专业Wiki），通过合并结果确保完整性，避免单一来源遗漏。

## 执行流程
1. **精准搜索**: 构造包含权威域的搜索词，如 `"[人物名] Wikipedia"` 或 `"[人物名] filmography site:imdb.com"`。
2. **锁定主页**: 打开排名第一的权威人物条目页，而非具体作品页。
3. **章节跳转**: 使用 `find` 指令直接跳转到关键词锚点（如 "Filmography", "Gameography", "Discography", "Works", "Credits"）。
4. **表格识别**: 确认是否存在标准 HTML 表格或列表结构。
5. **批量提取**: 提取该表格/列表中的所有条目。
6. **缺口判断**: 仅当权威源明确标注“incomplete”或列表明显中断时，才进行第二次针对性搜索（如 `"[人物名] credits MobyGames"`）。
7. **边缘条目补全**: 若任务要求包含Demo、特别版等边缘条目，且主Wiki列表不完整，立即转向MobyGames或GameFAQs等专业数据库，查找"Credits"页面以获取全量数据。

## 常见误区

- **场景**: 任务是获取某导演的全部电影，Agent开始逐个搜索电影名称。
    - ❌ 踩坑: `search "Inception Nolan"`, `open`, `search "Dunkirk Nolan"`... (导致搜索循环)
    - ✅ 应改用: `search "Christopher Nolan filmography Wikipedia"`, `open`, `find "Filmography"`, 提取整个表格。

- **场景**: Agent打开了人物介绍页，但一直在阅读生平事迹，未找到作品列表。
    - ❌ 踩坑: 持续 `find` 无关关键词或向下滚动，导致 NO_PROGRESS。
    - ✅ 应改用: 立即 `find "Filmography"` 或 `find "Works"`，直接定位到数据区。

- **场景**: 搜索结果中混杂了新闻文章（如“某导演十大最佳电影”）。
    - ❌ 踩坑: 打开 `.../best-movies-of-nolan` 试图提取列表（数据不全且非权威）。
    - ✅ 应改用: 跳过评论性文章，只打开 `.../wiki/Christopher_Nolan` 或 `imdb.com/name/...`。

- **场景**: 积累了大量证据节点但未生成最终答案。
    - ❌ 踩坑: 不断 `open` 新页面试图“补充”信息，导致 buffer 溢出或预算耗尽。
    - ✅ 应改用: 信任 Wikipedia 主表格的完整性，在提取完表格后立即汇总并结束任务。

- **场景**: 任务要求列出游戏制作人的所有作品（含Demo/特别版），Agent仅依赖Wikipedia。
    - ❌ 踩坑: 仅在Wikipedia提取主条目，遗漏了"Demo disc"、"Special Edition"等未被主表收录的边缘条目，导致覆盖率低。
    - ✅ 应改用: 并行分发Agent查询MobyGames或专业Wiki（如Junker HQ），利用专业数据库的Detailed Credits功能补全边缘条目。