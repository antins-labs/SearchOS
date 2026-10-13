# Anti-patterns — list_table_extraction

## Index
- **逐行迭代提取** — 每个作品/行单独 find → SEARCH_LOOP (×1, 2026-04-18)
- **Entity-by-entity 遍历** — 对每个实体独立搜索 (×1, 2026-04-18)
- **隐式时间范围直接搜** — 未先解析事件起止年份 (×1, 2026-04-18)
- **"complete list of X" 搜 SEO 页** — 命中营销文/不全 Top 10 (×1, 2026-04-18)
- **官网在售车型库** — 缺历史停产款 (×1, 2026-04-18)
- **全量缓存后输出** — 找到源但因缓冲阻塞无输出 (×1, 2026-04-28)

## Details

### 逐行迭代提取
**踩坑**: 面对几十条目的作品列表，用 `find` / `search` 逐个查找年份或作品名，让 extraction 中间件逐条落袋
**原因**: 迭代模式步骤数爆炸，极易触发 SEARCH_LOOP / NO_PROGRESS，最终 DAG_FAIL
**改用**: 把整个表格视为一个对象——用 Python/Pandas 解析页面 HTML 中的表格，筛选年份列后一次性输出
**观察**: 1 次  |  **最后**: 2026-04-18

### Entity-by-entity 遍历
**踩坑**: 需要获取"14 个共和国的领导人"这类列表时，对每个实体发起独立搜索（`search "Head of Adygea"` × 14）
**原因**: Entity-by-entity 策略让搜索步骤数与实体数线性相关，极易触发循环限制或预算耗尽
**改用**: 构造聚合查询 `search "List of heads of republics of Russia"`，找包含全集的单一表格页（通常 Wiki 有 `List of X` 页面）
**观察**: 1 次  |  **最后**: 2026-04-18

### 隐式时间范围直接搜
**踩坑**: 面对"东印度公司统治期间的总督"这类隐式时间范围，直接搜 `"Governors-General of India during East India Company rule"` 并反复翻页
**原因**: 起止年份未显式化时无法判断哪些条目属于范围内，在页面间跳转最终超时
**改用**: 先查 `"East India Company rule India start end dates"` 明确年份（1757-1858），再搜完整 Governors-General 列表按年份过滤
**观察**: 1 次  |  **最后**: 2026-04-18

### "complete list of X" 搜 SEO 页
**踩坑**: 用查询词 `complete list of video games by Hideo Kojima`
**原因**: 这种查询容易导向 SEO 营销文章或不完整的 Top 10 榜单，缺官方全集
**改用**: 查 `Hideo Kojima Wikipedia` 直接打开实体页，在页面内定位 "Works" / "Games" 章节（Wiki 保证列全）
**观察**: 1 次  |  **最后**: 2026-04-18

### 官网在售车型库
**踩坑**: 搜 `{Brand} cars list` 或打开官网"车型库"页面，仅提取当前显示的车型
**原因**: 官网车型库通常只展示在售款，无法覆盖特定历史区间内发布但已停更的车型；缺精确发布日期
**改用**: 搜 `{Brand} models timeline 2022-2025` 或 `{Brand} vehicle history Wikipedia`，利用百科时间线表格或按年份的新闻合集
**观察**: 1 次  |  **最后**: 2026-04-18

### 全量缓存后输出
**踩坑**: 找到正确数据源后，试图在内存中处理/验证整个数据集再统一输出，导致 state_delta_stall、buffer_full，最终无任何结果
**原因**: 全量缓存策略在大数据集时触发缓冲区溢出或逻辑循环，无法提交部分结果，进程被阻塞
**改用**: 强制"边提取边输出"——发现条目后立即分批提交（如每 5-10 条），而非等待全集编译完成
**观察**: 1 次  |  **最后**: 2026-04-28
