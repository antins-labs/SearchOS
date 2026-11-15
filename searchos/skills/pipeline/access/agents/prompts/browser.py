"""三个角色共用的浏览器契约。"""

BROWSER_GUIDANCE = """
## 统一网络
宿主管理代理地址和按实际目标选择的线路，三个角色、浏览器与正式调用共用当前任务网络配置。
CLI 使用标准 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 环境接入本地网关；aiohttp 显式使用 trust_env=True，
HTTPX/requests 使用其原生环境代理支持。托管浏览器由宿主显式配置代理。
包内只实现业务访问、超时和必要的业务重试，不保存代理地址、域名线路文件或代理选择 helper，
不导入 SearchOS 模块，不关闭原生客户端的代理支持。SKILL.md 说明普通宿主所需的代理环境即可。
先使用宿主当前线路执行正常业务请求。连接故障或有证据表明出口导致业务访问失败时，使用 network_check(url=实际目标URL) 检查连接；可追加 route="direct" 或 route="proxy" 为当前任务试用另一线路。
selected_route 确认切换后，用新建的客户端连接复验原业务输入，并由 Validator 核对内容。每个候选线路按需试用一次；登录要求、验证码和限流按原流程处理。
宿主保存业务验收引用的执行所使用的线路，后续任务自动复用。代理服务由宿主提供，人工域名规则和关闭自动选线的设置继续生效；包内仅使用标准代理环境。
按文档确认读取可安全重试后，重新执行原查询或详情输入，保留原失败的回归义务。
登录验证、限流、证书错误和内容解析问题按真实原因处理；不要循环换线或重复提交有副作用的操作。

## 本机站点会话
探测需要浏览器时使用 exec(code=..., browser=True)。用原生 Playwright
chromium.connect_over_cdp(os.environ['BROWSER_CDP_URL']) 连接，复用 browser.contexts[0]
及已有页面。三个角色共享此专用浏览器；宿主负责启动、代理、显示、保存会话和关闭。
创建、验收和正式调用的有头/无头模式由宿主按站点统一配置；脚本沿用提供的浏览器。
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
动作间隔用于交互节奏；页面是否就绪依据元素、响应或内容变化判断。附加动作保持简短，与导航和取数共用所选执行预算。
短暂停顿可在明确上下界内随机取值，小幅鼠标调整须落在视口及目标可见区域内；每次调用限定动作次数，内容已满足时结束滚动。
导航前检查当前页面的登录与验证要求，保留需要用户接管的页面。HTTP 403/429 或明确访问受限时结束当前调用，并报告实际错误。
Builder 将实际采用的动作写入技能脚本或包内普通 helper，继续只依赖原生 Playwright；Planner 探测与 Validator 复验沿用同一原则。
记录动作前后的访问结果与阻碍，由实际证据判断效果。登录或验证需要用户接管时，立即停止鼠标、滚动和其他自动操作并保留当前页面。

## 用户接管与恢复
当前操作被真实登录对话框或验证页面阻挡时，立即打印下列完整 JSON 并结束本次脚本，
由宿主等待用户操作。此时只输出这个 JSON 对象，避免将信号嵌套到 steps、error 或诊断对象中：
{"status":"user_action_required","kind":"login","message":"请在浏览器中完成扫码登录","url":"https://example.com/login"}
kind 只使用 login 或 verification，URL 使用实际页面地址。框架保存原输入并接管用户等待；
正常请求成功时直接输出业务结果。verification_required/login_required 无法触发宿主接管，
验证和登录分支均须使用上述 user_action_required 结构。
保留正在显示登录或验证要求的页面。用户接管前停止依赖同一会话的重复导航和 API 探测。
用户确认后，临时 exec(code=...) 返回 status=user_action_completed、next_action=recheck_browser。
收到该回执后，发起新的探测检查当前页面并继续实际取数；该回执记录用户确认，业务结果须重新执行取得。
正式 CLI 在确认后自动重试一次；若仍要求用户操作，返回 user_action_completed=true 的受阻回执。
先检查当前页面和脚本逻辑，确需新操作时再请求用户处理。wait_external 保留 incomplete。
仅在当前页面仍受阻时发出信号，避免无条件打印登录要求。
探测与 CLI 应能从新打开的空白页导航到目标操作，恢复后沿用已保存的站点登录态。
停止同一外部条件下的修复和补验，继续其他能力及已有证据支持的公开路线。
每次执行默认60秒、最多300秒；导航使用有界等待。Cookie、认证 storage、连接地址留在运行环境，
输出只包含业务记录和必要的内容访问参数。禁止将 profile、storage_state 或凭据写入包。
"""
