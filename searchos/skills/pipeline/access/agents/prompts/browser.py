"""三个角色共用的浏览器契约。"""

BROWSER_GUIDANCE = """
## 本机站点会话
探测需要浏览器时使用 exec(code=..., browser=True)。用原生 Playwright
chromium.connect_over_cdp(os.environ['BROWSER_CDP_URL']) 连接，复用 browser.contexts[0]
及已有页面。三个角色共享此专用浏览器；宿主负责启动、代理、显示、保存会话和关闭。
脚本结束时停止自己的 Playwright 客户端连接，保留共享 browser/context/page。
交付 CLI 在 SKILL.md metadata 声明 searchos-browser-profile: managed，
searchos-browser-entries: scripts/access.py（多个入口用逗号分隔），host 为目标站点。
包只使用原生 Playwright 和普通 CLI，说明其他宿主须提供同一 BROWSER_CDP_URL 环境。

## 鼠标移动与页面滚动
进入正常业务页面并确认内容可用后，在搜索、打开结果和阅读正文等步骤中加入适度的原生鼠标移动与滚动。
按实际目标选择动作：通过 locator.bounding_box() 获取目标位置，使用 page.mouse.move(x, y, steps=...)
经过视口内少量中间点再移向目标；可小幅调整路径和短暂停顿，坐标使用当前主框架视口的 CSS 像素。
需要浏览后续内容或触发懒加载时，将鼠标移入对应内容区域，使用 page.mouse.wheel(0, delta_y) 分段滚动，
每段约四分之一到半个视口。根据实际可滚动容器和内容变化调整幅度；目标已可见或内容已满足任务时结束滚动。
wheel 返回后检查滚动位置或等待目标内容出现；定位后续控件可使用 locator.scroll_into_view_if_needed()。
动作与取数在当前脚本中顺序执行，保留已有页面位置，避免整页无目的往返、随机点击和后台循环。
动作间隔用于交互节奏；页面是否就绪依据元素、响应或内容变化判断。附加动作保持简短，与导航和取数共用30秒预算。
Builder 将实际采用的动作写入技能脚本或包内普通 helper，继续只依赖原生 Playwright；Planner 探测与 Validator 复验沿用同一原则。
记录动作前后的访问结果与阻碍，由实际证据判断效果。登录或验证需要用户接管时，立即停止鼠标、滚动和其他自动操作并保留当前页面。

## 用户接管与恢复
当前操作被真实登录对话框或验证页面阻挡时，立即打印下列完整 JSON 并结束本次脚本，
由宿主等待用户操作。此时只输出这个 JSON 对象，避免将信号嵌套到 steps、error 或诊断对象中：
{"status":"user_action_required","kind":"login","message":"请在浏览器中完成扫码登录","url":"https://example.com/login"}
kind 只使用 login 或 verification，URL 使用实际页面地址。框架保存原输入并接管用户等待；
保留正在显示登录或验证要求的页面。用户接管前停止依赖同一会话的重复导航和 API 探测。
用户确认后，临时 exec(code=...) 返回 status=user_action_completed、next_action=recheck_browser。
收到该回执后，发起新的探测检查当前页面并继续实际取数；该回执记录用户确认，业务结果须重新执行取得。
正式 CLI 在确认后自动重试一次；若仍要求用户操作，返回 user_action_completed=true 的受阻回执。
先检查当前页面和脚本逻辑，确需新操作时再请求用户处理。wait_external 保留 incomplete。
仅在当前页面仍受阻时发出信号，避免无条件打印登录要求。
探测与 CLI 应能从新打开的空白页导航到目标操作，恢复后沿用已保存的站点登录态。
停止同一外部条件下的修复和补验，继续其他能力及已有证据支持的公开路线。
每次执行最多30秒；导航使用有界等待。Cookie、认证 storage、连接地址留在运行环境，
输出只包含业务记录和必要的内容访问参数。禁止将 profile、storage_state 或凭据写入包。
"""
