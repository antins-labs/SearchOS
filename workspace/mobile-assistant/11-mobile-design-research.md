# 移动端设计调研 · 2026-10-19

本轮目标：先完成独立的产品与交互原型，再评审正式移动端改造。用户选择「原生 iPhone 风格：克制、清晰、轻量」。本文件记录公开资料与设计判断；不会将示例原型视为已接入能力。

## 参考资料与采用方式

| 资料 | 核实内容 | 对 SearchOS 的应用 |
| --- | --- | --- |
| [Apple Human Interface Guidelines：Tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars) | 标签栏用于主要区域之间的导航，保持位置与含义稳定 | 保留「助理 / 任务 / 我的」；新建不是第四个标签；详情用返回路径 |
| [Apple：UI Design Dos and Don’ts](https://developer.apple.com/design/tips/) | 主要内容适配屏幕、不横向滚动；建议至少 44×44 pt 触控区域；重视对比、间距与对齐 | Web 原型将主要操作设为至少 44 CSS px；正文 16–17 px，元信息 12–13 px；不照搬桌面宽表格 |
| [Apple Design Resources](https://developer.apple.com/design/resources/) | 提供官方 Figma、Sketch UI Kit 等设计资源 | 后续 Figma 组件稿的优先模板来源；本轮用原生导航、分组列表、字阶和单一蓝色强调色表达，不复制受许可约束的资源文件 |
| [Figma：Apple UI Kit 使用说明](https://help.figma.com/hc/en-us/articles/24037833895831-Get-started-with-Apple-s-UI-kit) | 说明 Apple 组件库使用与许可入口 | 需要团队维护 Figma 时再引入；本轮交付可运行 HTML 原型，不宣称生成了 Figma 文件 |
| [Apple：Notifications](https://developer.apple.com/design/human-interface-guidelines/notifications?changes=_4) | 通知简短、有价值、避免重复与泄露敏感内容；前台反馈不应过度打扰 | 系统通知只显示「报告已准备好」与站内目标；打开后直达结果。站内消息保留未读与任务关联 |
| [Apple：Managing notifications](https://developer.apple.com/design/human-interface-guidelines/managing-notifications?changes=_1__6&language=objc) | 用户可以控制通知与投递偏好 | 定时计划保存后再说明提醒价值；通知被拒绝仍能在任务页读结果 |
| [Things：Features](https://culturedcode.com/things/features/) | 按时间组织、快速添加、简洁列表与渐进展开 | 借鉴轻量列表和时间信息层级；SearchOS 的执行任务与重复计划分开，不照搬待办打勾模型 |
| [Mobbin](https://mobbin.com/) | 移动端真实产品界面与流程参考库 | 可作为后续竞品流程审查入口；此次仅核实公开入口，未把付费流程截图当作已研究依据 |

## Skill 候选

| Skill | 来源与侧重 | 本轮判断 |
| --- | --- | --- |
| UI UX Pro Max | [原作者仓库](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)：可搜索的风格、色彩、可访问性和跨平台设计知识 | 可用于设计规范与交付检查，不应直接让通用风格推荐决定个人助理的信息架构 |
| frontend-design | [Anthropic 原始 SKILL.md](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)：有意识的视觉方向、内容相关设计和界面文案 | 借鉴先确定设计意图再选样式的方式；用户已选原生 iPhone，保持平台熟悉感 |
| Sites（现有工具） | 本地 HTML 交互、浏览器预览和验证 | 用于原型呈现；不注册或发布新的托管站点 |

本轮查阅与比较了公开 skill，没有全局安装第三方包。官方 skill 目录辅助查询遇到本机 Python 证书链错误，改以可访问的公开原作者页面核实候选；没有关闭证书校验。Skill 是工作方法，UI Kit 是组件模板，二者都不能替代用户流程设计。

## 设计判断

以下为针对 SearchOS 的设计决策，不是参考资料对产品的直接要求。

1. **首页的主动作是交办。** 一次输入、一条来源摘要；深度、时限等留在二级选项。
2. **结果拥有独立阅读空间。** 任务会话适合补充要求，报告页适合连续阅读；大输入框不占据报告正文。
3. **执行与计划是不同对象。** 执行有进展、结果、异常；计划有频率、下次运行和启停。
4. **资料首先是输入范围。** 使用全高选择页和明确确认操作；知识库维护置于「我的」，复杂图谱留在桌面。
5. **状态必须可以解释。** 主机离线时保存草稿，不假装任务已交付；任务失败提供重试；通知未开启不阻止使用。
6. **用排版区分信息。** 大标题、分组列表、细分隔线、局部有色图标；仅把报告与需要关注的信息做成突出卡片，避免层层套卡。
7. **触控优先。** 整行可点击，保留文字标签；关键动作靠近拇指，键盘出现时避免底部导航挤压编辑区。

下一份：[12 原型规格与验收](12-native-mobile-prototype.md)。
