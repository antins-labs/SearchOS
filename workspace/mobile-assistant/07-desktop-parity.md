> v0.3 更新：界面设计已由 [08 手机指令与结果入口](08-mobile-command-center.md) 取代。本页保留 v0.2 实施历史。

# v0.2 桌面功能对齐与移动适配

更新：2026-10-14。分支：`codex/mobile-assistant-prototype`。

## 当前产品基准

用户确认：移动端必须以现有桌面 SearchOS 为准，保留完整功能、数据和业务逻辑，调整小屏交互。原先独立的“助理 / 任务 / 收件箱”原型不再作为当前实施基准。

先实现完整研究工作区的移动入口，再增量接入远程绑定、定时任务和系统通知。研究内容不限定为某个业务领域。

## 当前页面结构

- `/`：桌面入口，同一工作区在窄屏下也提供移动导航。
- `/m`：移动工作区入口，在宽屏上也保持单栏。
- `/m/settings`：复用完整设置页，支持小屏分区跳转。
- `/m/skills`、`/m/skills/new`：复用技能库和技能创建页，返回链接保持在移动入口。
- 原独立原型的 tasks/inbox/schedules/reports/runs/conversations 等 URL 回到 `/m`，不再保留模拟任务与报告。

底部五个操作是“研究 / 历史 / 知识库 / 详情 / 设置”。切换历史、详情、知识库、设置时使用面板，不卸载主研究会话。详情在尚无会话时禁用；打开历史或开始研究后可用。

## 功能映射与复用

| 桌面功能 | 移动入口/布局 | 复用组件与逻辑 |
| --- | --- | --- |
| 新建搜索、追加要求、多轮追问、停止、重跑 | 研究页；输入区分为文本区与操作行 | ResearchWorkspace、useSearch、Conversation、Composer |
| Web / Local / Hybrid | 输入区上方来源选择 | LocalSourceControl、useLocalLibrary |
| 上传及选择本地文档 | 添加文件、知识库面板 | 原上传、索引与来源选择流程 |
| 手工 schema、表格/关系、CSV/TSV、撤销/重做 | 输入区表格配置按钮；复杂表格局部滚动 | 原 Composer schema 编辑器 |
| 研究档位、时间预算、技能、可信/排除来源 | 本次任务参数面板 | RunOverridesPopover |
| 历史搜索、收藏、归档、项目、标签、排序、改名/删除 | 历史抽屉 | HistoryRail；原历史 API |
| 知识库、主题、文档、索引、图谱/列表、原件预览 | 全屏知识库面板 | KnowledgeBasePanel 及其子组件 |
| 回答正文、引用、继续追问、复制、Markdown 下载 | 研究对话 | Answer、AnswerActions |
| 覆盖表格、列过滤、全屏表格、导出、补查 | 回答下方与详情中的 Coverage | CoverageTable、ResultExportMenu |
| 证据、冲突处理、重新核验 | 详情 Evidence 标签 | EvidenceList；原读写接口 |
| 子 Agent、调用轨迹、工具输入输出 | 详情中可展开 Agent 列表 | AgentWall、TraceDrawer、ToolCallDetailDialog |
| 待办任务、版本、分支、用量、文件、事件 | 详情横向标签栏 | FrontierPanel、VersionsPanel、ResourcePanel、FileTree/FileViewer 等 |
| 快速配置、模型、联网、技能、预算、策略、外观 | 全屏设置；原有分区不删减 | SettingsModal、SettingsPage 与全部 section |
| 技能目录、技能内容/文件、创建、验证历史 | 历史中的技能库入口 | SkillLibraryPage、SkillCreationPage |

“复用”意味着入口调用现有行为，不代表本轮重新验证了每一种写入或付费模型操作。Local 模式仍按桌面逻辑显示其适用的详情标签，不强行增加不适用的 Web 功能。

## 实施结构

原 `src/app/page.tsx` 中的业务编排完整提取到 `src/components/research/ResearchWorkspace.tsx`，桌面与移动路由同时调用它。SettingsProvider 对两个入口一致生效。没有新建第二套会话、搜索、历史或结果模型。

新增 `mobile-workspace.css` 处理安全区、底部导航、输入区、小屏设置和知识库布局；桌面三栏保留。移动详情默认折叠 Agent 列表，将完整视图标签放到列表之前，避免多 Agent 挤走结果入口。

`useWorkspaceBase` 保持完整设置和技能页在对应工作区内导航。原独立演示组件已移除。

## 当前边界

- 现在读取和调用真实后端；与 v0.1 不同，提交研究或修改设置会触发真实操作。
- 后端和前端仅监听本机回环地址。当前不是外网远程连接，也未开通手机公网访问。
- 定时任务、设备配对、认证网关、推送与 PWA 安装能力尚未接入。后续作为桌面工作区的增量能力设计。
- 后端仍使用现有 API_BASE 配置；真正跨设备部署时要统一安全访问入口和 WebSocket 访问方式。
- 原生 iPhone 键盘、后台连接、实际文件选择、通知权限需在后续设备接入阶段验收。

## 已验证与未验证

已在浏览器小屏检查：首页/输入、参数、schema 入口、全屏设置与模型页、历史加载与报告恢复、详情标签、文件列表、知识库空状态、技能导航。390 px 与 320 px 检查页面无整页横向溢出；宽屏保留桌面侧栏。

使用已有历史数据进行验证，没有发起新的搜索，没有修改模型配置、删除历史或触发补查/分支。上述写操作沿用原组件，不能把入口可见等同于全部端到端验证完成。

现有前端测试 91 项通过，改动文件 ESLint 通过，排除旧 demo 后的源码类型检查通过。全项目类型检查仍被旧的 `src/app/demo/page.tsx` 两处类型错误阻挡（历史条目缺字段、缺 localLibrary）；本轮不修改该演示文件。

本机 Python 环境缺少项目已声明的 python-multipart，已安装以启动现有 API；未修改依赖清单。

## 预览

- [移动工作区](http://127.0.0.1:3100/m)
- [桌面工作区](http://127.0.0.1:3100/)

前端在 `web/frontend` 执行 `npm run dev -- --hostname 127.0.0.1 --port 3100`；后端在仓库根目录执行 `./web/start.sh api`。截图存放在 `previews/workspace-*.jpg`。
