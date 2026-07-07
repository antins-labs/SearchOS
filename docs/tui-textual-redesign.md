# SearchOS TUI 重构方案：迁移到 Textual

## 1. 背景与问题

当前 TUI（`searchos/tui/app.py` + `dashboard.py`）是 **prompt_toolkit 全屏 App + Rich 渲染成 ANSI 字符串塞进 `FormattedTextControl`** 的混合架构。它有一个结构性缺陷：

- **两套独立的屏幕模型**。Rich 按自己的 cell-width 把内容渲染成 ANSI，prompt_toolkit 再用自己的字宽计算把这段 ANSI 排进全屏窗口。
- **第三方分歧无法消除**。Python 侧（Rich/pt 一致）把 East-Asian-Ambiguous 宽度字符（`◆ ▶ ○ ● → · │ ─` 连框线）一律算 1 格，但终端在 `zh_CN.UTF-8` 下常画成 2 格；emoji（`📋🔍🔧`）步进也不一致。
- **全屏 diff 累积错位**。prompt_toolkit 靠「与上一帧 diff + 光标增量重绘」更新。一旦某格错位，diff 基准就错，**错位持续累积、不自愈** → 表现为「运行时间一长就乱码」。
- **不断增长的全量重绘**。orchestrator 流每帧把整个缓冲区 Rich→ANSI 再裁剪，开销随运行时长上升。

增量补丁（去 emoji / 周期清屏 / 逐行裁宽）只能压制，不能根治，因为「双渲染模型 + 全屏 diff」这个 bug 源还在。

## 2. 目标

1. **根除乱码**：单一渲染/布局/字宽模型，错位被约束在单个 widget 内、随重绘自愈，不跨屏累积。
2. **流式输出 append-only**：orchestrator 的 reasoning / content / 工具调用作为追加日志，不再每帧重渲染历史；支持原生上滚查看历史。
3. **保留现有交互**：常驻输入行、运行中排队、Esc/Ctrl-C 中断本轮、idle banner / running dashboard / done 答案三态。
4. **最大化复用**：`dashboard.py` 里 `_render_agents` / `_render_progress` / `_render_frontier` / `_render_events` / `_render_tool_call` 等已经返回 Rich renderable，可直接被 Textual widget 复用。

## 3. 为什么是 Textual

- Textual 是 Rich 作者的全屏 TUI 框架，**Python 里最接近 Claude Code 的 Ink** 的对应物：单一 compositor、按 widget 区域差分重绘、内建虚拟滚动。
- **单一字宽模型**：整屏只有 Textual 一套布局，没有「框架 A 渲染好再塞进框架 B」的二次排版。
- **错位被隔离**：Textual 对每个 widget 做 clipping + 独立重绘，单个 glyph 误判只污染该 widget 当前行、下一帧覆盖掉，不会像 pt 那样全屏累积。
- **`RichLog` widget**：天生 append-only + 可滚动，正是 orchestrator 流要的东西。
- **复用 Rich renderable**：现有 dashboard 的 section 渲染函数原样可用。
- 纯 Python，依赖 Rich（项目已用），引入成本低。

> 备选 D'（不引依赖）：用 prompt_toolkit 非全屏模式，把完成的流 print 到 scrollback、底部只托管一小块活动区。能复刻 Claude Code 的 scrollback 体验，但要自己处理底部区重绘、输入、与 scrollback 的边界，工程量并不比 Textual 小，且仍是手搓 compositor。**故推荐 Textual。**

## 4. 目标架构

### 4.1 Widget 树（运行态）

```
SearchOSApp(App)
└── Screen
    ├── #panels  (Vertical, dock=top, 固定高度 ≈ 屏高的一半上限)   ← 状态面板在上
    │   ├── AgentsPanel       (Static, render() -> dashboard._render_agents())
    │   ├── ProgressPanel     (Static, render() -> dashboard._render_progress())
    │   ├── FrontierPanel     (Static, render() -> dashboard._render_frontier())
    │   └── EventsPanel       (Static, render() -> dashboard._render_events())
    ├── #stream  (RichLog, 填满剩余空间, auto_scroll=True)          ← orchestrator 流在下、贴着输入实时滚动
    ├── #statusbar (Static, dock=bottom, height=1, reverse)         ← stats + 模式提示
    └── #input    (Input, dock=bottom, height=1)                    ← 常驻输入
```

- idle 态：隐藏 `#panels` / `#stream`，显示 `#banner`（Static，logo + 欢迎）。
- done 态：`#stream` 顶部插入答案（`Markdown`/`VerticalScroll`），面板切成最终汇总；或保留面板 + 在 statusbar 显示覆盖率/证据/耗时。
- 三态通过切换容器的 `display` 属性实现（全部预挂载，按 mode 显隐），避免频繁 mount/unmount。

### 4.2 数据流

```
session.run(query, on_event=app._on_event)
        │  (同一 asyncio 事件循环内的同步回调)
        ▼
app._on_event(event):
   1) app.dashboard.feed(event)            # 更新数据模型（面板用）
   2) app.post_message(TrajectoryEvent(e)) # 线程/循环安全地投递给 Textual
        ▼
app.on_trajectory_event(msg):              # 在 Textual 事件循环里处理
   - assistant.reasoning  -> #stream.write(Text(dim italic))
   - assistant.content    -> #stream.write(Text(white))
   - orchestrator_tool_call -> #stream.write(⏺ tool(args))   # 调用即时显示
   - orchestrator_tool      -> #stream.write(  ⎿ result)      # 结果到达后追加
   - 其它(step/dispatch/harness...) 只更新模型，面板由定时器刷新
```

- **面板刷新**：`set_interval(0.5, app._poll)`，内部 `dashboard.poll_state()` 读 `search_state.json`，然后对四个面板 `widget.refresh()`（覆盖矩阵规模有界，开销低）。
- **流刷新**：事件驱动 append，不轮询、不重渲染历史。

### 4.3 工具调用「先显示、后回填」在 append-only 下的处理

`RichLog` 是追加式，不便原地改已写行。改用 Claude-Code 同款的两行式：

- 收到 `orchestrator_tool_call`：立即追加 `⏺ tool(args)` 一行。
- 收到 `orchestrator_tool`（结果）：追加 `  ⎿ result` 一行。

orchestrator 多数是「一轮一个工具调用」，结果紧跟其后，⎿ 自然落在 ⏺ 下方，视觉上与原地回填等价。仅当多个工具调用并发在途时 ⎿ 可能不严格紧贴对应 ⏺——对 orchestrator 属罕见，可接受。

> 这样还能**顺带去掉** dashboard 里的 `_pending_stream` 回填逻辑和 `_orch_stream` 缓冲 deque——流不再需要被持有/重渲染。

## 5. 模块改动计划

| 文件 | 改动 |
|---|---|
| `searchos/tui/app.py` | **重写**为 `SearchOSApp(textual.App)`：compose 布局、BINDINGS、`on_input_submitted`、运行/排队/中断生命周期、`_on_event`、`on_trajectory_event`、`_poll` 定时器、三态显隐。`run_tui()` 签名不变，内部改 `SearchOSApp(...).run()`。 |
| `searchos/tui/widgets.py` | **新增**：`AgentsPanel/ProgressPanel/FrontierPanel/EventsPanel/Banner` 等 Static 子类，`render()` 直接返回 dashboard 对应 renderable；`TrajectoryEvent(Message)` 自定义消息。 |
| `searchos/tui/dashboard.py` | **瘦身为纯数据模型 + section 渲染器**：保留 `feed/poll_state/_apply/stats_line` 和 `_render_agents/_render_progress/_render_coverage_matrix/_render_frontier/_render_events/_render_tool_call`。**删除** `render_ansi/render_stream_ansi/render_status_ansi`（行切片裁剪）、`_orch_stream` deque、`_pending_stream`（流改由 App 直接 append 到 RichLog）。 |
| `pyproject.toml` | dependencies 增加 `textual>=0.80`（与 rich 13.9 兼容）。 |

### 交互与生命周期映射

- `BINDINGS = [("ctrl+d", "quit"), ("ctrl+c", "interrupt"), ("escape", "interrupt")]`
  - `action_interrupt`：running 则 `self._run_task.cancel()` 并提示「已请求中断…」；非 running 则 `self.exit()`。
- `on_input_submitted`：running 则入队 `self._queue` 并提示「已排队 N 条」；否则 `_start_run(text)`。
- `_run` 协程：`await session.run(...)` → 读 `report.md` → done 态显示答案与汇总；`CancelledError` → 「已中断」；`finally` 若队列非空则取下一条继续。

## 6. CJK / emoji 稳健性（即使在 Textual 下）

- 覆盖矩阵、面板等**对齐敏感**的栅格区：继续用 ASCII 安全符号 + `box=None`，避免歧义宽度字符进入表格列。
- `#stream`（RichLog）是流式文本、非栅格，emoji/符号错位无害，可保留 `⏺ ⎿ ✻` 等观感符号。
- Textual 的 per-widget clipping 保证：即便某 glyph 被终端画宽，污染只限该 widget 当前行，下帧覆盖，不跨屏累积。

## 7. 分阶段落地

1. **P1 脚手架**：加 textual 依赖；`app.py` 搭出 idle banner + 输入 + Esc 退出的空壳，跑通 `run_tui()`。
2. **P2 流式**：接 `RichLog` + `_on_event`/`TrajectoryEvent`，跑通 reasoning/content/工具调用的 append（含两行式工具调用）。
3. **P3 面板**：迁移四个面板 widget + `_poll` 定时器，复用 dashboard renderable。
4. **P4 三态**：idle/running/done 显隐切换、答案渲染、排队/中断/续跑生命周期。
5. **P5 清理**：删除 dashboard 中的 ANSI 裁剪 / 流缓冲遗留；长时运行回归（重点验证「时间一长不再乱码」）。

## 8. 风险与权衡

- **新依赖**：引入 textual（纯 Python，依赖已有的 rich）。可接受。
- **工具调用配对**：append-only 下并发工具调用的 ⎿ 可能不严格紧贴 ⏺。orchestrator 场景罕见；若要严格配对，可在结果行前缀带上工具名（`⎿ search → ...`）消歧。
- **done 态最终面板**：当前 done 把整块 dashboard 再渲染一次；新方案可保留面板 widget 的最后状态 + 答案区，无需重渲染整屏。
- **回退**：保留旧 `app.py` 为 `app_pt.py` 一个版本周期，`run_tui` 走开关，验证稳定后删除。

## 9. 复用 / 丢弃清单

- **复用**：`LiveDashboard` 全部 `feed/_apply/poll_state` 事件与状态逻辑；所有 `_render_*` section 渲染函数；LOGO/banner 内容；session 集成与 `run_async` 的浏览器服务收尾。
- **丢弃**：`render_ansi/render_stream_ansi/render_status_ansi`（行切片）、`_orch_stream`/`_pending_stream`（流改 append）、prompt_toolkit 的 `HSplit/Window/FormattedTextControl/ANSI` 全套布局桥接、`_term_size/_rich_to_ansi` 等手搓尺寸工具。
