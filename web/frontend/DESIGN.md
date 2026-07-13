# SearchOS 前端设计源真相 (DESIGN.md)

> 面向用户的 web 前端重构。基调:**Claude 暖棕编辑风**(warm-brown editorial)。
> 目标:消除"上世纪僵硬感",达到 ChatGPT/Claude 网页那种克制的高级感。
> 后端不动(沿用 WS/2s 轮询和现有事件结构)。

## 1. 形态总览

三栏 + 执行期动态揭示:

```
┌──────────┬─────────────────────────────────┬──────────────┐
│ 历史侧栏  │        对话主体 (主角)            │  执行抽屉      │
│ (可收起)  │   极简,一进来只见 composer        │ 推开式,执行才出 │
└──────────┴─────────────────────────────────┴──────────────┘
```

- **左 rail**:可收起的历史对话(+ 新对话 / 搜索 / 按日期分组的会话列表)。
- **中对话**:主角,max-width ~720px 居中。空态 = 居中极简 composer;执行后 = 流式回答 + 内联编排概览卡。
- **右抽屉**:**默认不出现**。query 执行后,assistant 消息内长出"编排概览卡";点卡 → **Claude artifacts 同款推开式抽屉**从右滑入,把对话压窄并排,可拖宽/最大化。关掉回到内联概览。每条 assistant turn 各自保留自己的概览卡。

### 揭示两层
- **概览态(内联,低高度)**:phase pills(`warmup→schema→dispatch→evaluate→synthesize`,当前脉冲) + agent chips(每派发点亮一个) + 活体计数("4 个 agent 在搜索 · 23 任务 · 覆盖 12/40")。
- **详情态(右抽屉)**:上 AgentWall(每 subagent 一卡,点开看完整 trace) + 下 tabs(Coverage / Evidence / Files / Events)。实时更新。

## 2. 设计 token

全部 token 化为 CSS 变量。两套主题:**默认浅色暖调**,深色暖夜为变体。

```css
/* 浅色暖调 (默认) */
--bg:          #F5F4EE;  /* 纸白底 */
--surface:     #FBFAF6;  /* 卡面/抬升 */
--surface-2:   #EFEDE4;  /* 次级面/hover */
--border:      #E3E0D6;  /* 低对比暖边框 */
--border-strong:#D6D2C4;
--text:        #28261F;  /* 暖墨主文 */
--text-dim:    #6B675C;  /* 次级文字 */
--text-faint:  #9A9488;  /* 三级/占位 */
--accent:      #C2603D;  /* 赭石/陶土 — 仅小面积:执行中/链接/当前phase */
--accent-soft: #E8D5C4;  /* 浅陶 — 高亮底/chip */
--ok:          #5E7C5A;  /* 完成态(暖橄榄,克制) */

/* 深色暖夜 (变体) */
--bg:          #1E1C1A;
--surface:     #292723;
--surface-2:   #322F2A;
--border:      #3A372F;
--text:        #ECE8DF;
--text-dim:    #9A9488;
--accent:      #D2754F;
```

**纪律**
- 禁止紫色渐变(AI 廉价信号)。
- 强调色只在极小面积出现(执行中脉冲/当前 phase/链接/选中);大面积永远是纸白 + 暖灰。
- 层次靠 1px 暖边框 + 留白,不用重投影。抽屉用极轻投影。

## 3. 字体

刻意避开 Inter/Roboto/Arial(AI 用烂)。全免费可商用。

- **标题 / wordmark**:`Fraunces`(可变衬线,光学尺寸,编辑杂志感的核心)
- **正文 / UI**:`Instrument Sans`(人文无衬线,温暖)
- **trace / 代码 / 表格数字**:`JetBrains Mono`

字阶(rem,1rem=16px):wordmark 1.5 / h 1.25 / body 0.9375(15px) / small 0.8125(13px) / mono 0.8125。行高 body 1.6(松)。

## 4. 间距 / 圆角 / 动效

- **8px 网格**:4 / 8 / 12 / 16 / 24 / 32 / 48 / 64,所有 margin/padding/gap 吸附。
- **圆角**:卡片 12px,chip/按钮 8px,输入框 12px。不用大圆角彩卡。
- **动效**(全 ≤250ms,ease-out,无花哨过场):
  - 消息淡入上浮 200ms
  - 流式打字 / phase pill 脉冲(accent 呼吸)
  - 抽屉滑入 240ms,对话列宽 cubic-bezier 过渡

## 5. 重构顺序(每步可单独验收)

0. **本文件 + 静态样张**(design-preview/) — 先确认基调。
1. **token 地基**:globals.css 重写为上述 CSS 变量 + 字体接入 + 8px 工具类。
2. **三栏外壳 + 历史 rail**:AppShell(rail 可收起 / 中对话 / 右抽屉槽位) + 极简着陆 composer。
3. **对话主体 + 内联编排概览卡**:流式 turn + phase pills + agent chips + 活体计数。
4. **推开式抽屉工作台**:复用 AgentWall/TraceDrawer/CoverageTable 重排进抽屉。
5. **打磨**:动效 / 空态 / 骨架屏 / 深色暖夜变体。

## 6. 参考

- Vercel AI Elements(reasoning/tool/workflow 块) — github.com/vercel/ai-elements
- assistant-ui — github.com/assistant-ui/assistant-ui
- Claude 反 AI 味设计指南(禁紫渐变/8px/编辑排版)
