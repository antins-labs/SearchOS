# 在云服务器部署自己的 SearchOS，并在 iPhone 上使用

本指南对应包含 `deploy/` 的代码版本。一个实例对应一个个人工作区，所有绑定设备均可信，
不提供陌生用户注册和多租户隔离。网页、执行引擎、定时计划和资料都运行、保存在服务器上；
手机和家里的电脑关机不会停止服务器任务。

当前提供的是**从源码构建的 Compose 部署包**，不是已经发布的官方镜像。
请确认取得的公开版本包含这些文件；不要把 GitHub 默认分支当作一定包含尚未合并的移动端代码。
本文步骤需在你自己的 Linux 服务器执行，不会改动原来 Mac 的常驻服务。

## 1. 准备服务器和域名

- 一台持续运行的 Linux 服务器，建议 Ubuntu 24.04 LTS、x86_64。个人试用可从 2 核 4 GB 评估；
  在服务器上构建网页、运行浏览器及处理 PDF 时，4 核 8 GB 更宽裕。这是估算，不是性能保证。
- 至少预留约 30 GB 空闲磁盘，再按资料和备份量增加。模型采用外部 API 时无需 GPU。
- 安装 Git、[Docker Engine 与 Compose 插件](https://docs.docker.com/engine/install/ubuntu/)。
  执行 `docker version`、`docker compose version` 确认可用，启用 Docker 的开机启动。
  使用有 Docker 操作权限的账户；不要为方便而公开 Docker API 或挂载 Docker socket 给应用。
- 一个你控制的域名，例如 `search.example.org`。将 A 记录指向服务器公网 IPv4；
  只有 IPv6 确实可用时才设置 AAAA。首次使用直接 DNS 解析，不叠加 CDN 或其他代理。
- 云防火墙/安全组允许 TCP 80、443 入站；SSH 仅按自己的管理需要开放。**不开放 8000、3100**。
  服务器必须能访问镜像仓库、Python/npm 依赖源、证书服务、所选模型/搜索服务和 Apple 推送服务。
- 准备自己的模型 API Key、搜索 API Key。费用由相应服务商分别收取。
  域名和服务器地域的接入要求请按云厂商指引完成。

本标准方案会提供**公网可达、受身份认证保护的 HTTPS 入口**，不等于私网。
只有你输入的资料才会上云，不会自动连接你的电脑或公司内网。

## 2. 获取代码、填写两个必要配置

获取包含本部署包的 SearchOS 发布版本，进入仓库根目录。若从 GitHub 克隆：

```bash
git clone https://github.com/antins-labs/SearchOS.git
cd SearchOS
test -f deploy/compose.yaml
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
```

如果 `test` 失败，说明该分支尚未包含部署包；切换到维护者提供的对应发布版本再继续，
不要重复创建配置或使用来路不明的镜像。首次试用后记录 `git rev-parse HEAD`，便于升级回退。

编辑 `deploy/.env`：

```dotenv
SEARCHOS_DOMAIN=search.example.org
SEARCHOS_EMAIL=你的真实联系邮箱
SEARCHOS_TIMEZONE=Asia/Shanghai
```

域名**不带 `https://`、端口、路径和末尾斜杠**。邮箱用于证书及 Web Push 联系信息。
模型密钥不用放在这里，之后登录网页填写。此文件被 Git 忽略。

## 3. 构建并启动

以下命令均在仓库根目录执行：

```bash
bash deploy/searchos.sh build
bash deploy/searchos.sh up
bash deploy/searchos.sh status
bash deploy/searchos.sh doctor
```

首次构建会下载依赖、Chromium 并编译网页，需要较长时间和网络连接。
三个服务为 `api`、`web`、`caddy`。API 与网页通过健康检查后才启动入口；
Caddy 自动申请及续期 HTTPS 证书。`up` 成功不代表公网 DNS、证书或手机已验收，
还需要实际打开 `https://你的域名/m`，确认浏览器没有证书警告。

```bash
# 查看日志；Ctrl-C 仅退出日志，不停止服务
bash deploy/searchos.sh logs
```

容器退出会按 `unless-stopped` 策略重启；手动停止的服务不会自行恢复。
Docker 本身也必须配置开机启动。健康检查异常用于显示状态，不会自动杀死或重启卡住的研究。
服务重启不保证中断任务自动续跑；当前只有一个 API worker，不能使用 `--scale api=2`。

`doctor` 不调用模型，检查 API、持久化目录、无头 Chromium 和隔离技能脚本。
返回 0 表示这些检查通过；1 表示基础运行检查失败；2 表示浏览器可用但技能沙箱不可用。
Docker 的 seccomp/AppArmor 或宿主机用户命名空间限制可能阻止 bubblewrap；
此时内置搜索/读取与依赖技能脚本的能力要分别验收，后者不能视为可用。
部署包不会关闭沙箱、使用 privileged 或授予 SYS_ADMIN 来绕过限制。
需要全部技能能力时，必须选用并验证支持该隔离机制的运行环境后再投入使用。
无图形桌面的云主机也不支持弹出本机浏览器完成 X 等网站的交互登录。

## 4. 管理员登录与模型配置

在**自己的服务器终端**执行：

```bash
bash deploy/searchos.sh token
```

这是管理员凭据，请存入自己的密码管理器，不要发到群聊、Issue、截图或 Git。
凭据只保存在私有数据卷中，不会通过公开页面读取；没有公开注册入口，也不存在先访问者抢占注册。
当前使用持久管理员凭据和设备配对，不是一次性注册码或用户名密码账户。

1. 打开 `https://你的域名/m`，选择“首次配置：管理员登录”，输入凭据。
2. 进入“我的 → 更多设置”，或者直接打开同域名 `/m/settings`。
3. 在“模型”配置自己的服务商、Base URL、API Key 和模型，检查各研究角色的模型绑定。
4. 在“联网与读取”选择可在服务器网络使用的搜索服务，例如 Serper 或 Tavily，填写 Key。
   内网 RagFlow、内部模型默认值不适合个人公网服务器；不要把未配置的默认项当作可用服务。
5. 查看“快速配置”，完成必要配置；从轻度搜索和小预算开始验证。

网页保存的密钥、模型配置会持久化，重建容器后保留。配置项显示“已填入”不等于已经通过真实调用验证。
模型套餐是否允许当前用途，以相应供应商规则为准。

## 5. iPhone 绑定与通知

1. iPhone 用 Safari 打开 `https://你的域名/m`。
2. 分享菜单 → 添加到主屏幕，从新图标重新打开。
3. 已登录的管理员设备进入“我的 → 连接与设备”，生成 8 位配对码。
4. 在 iPhone 主屏幕应用输入配对码。码有效 5 分钟且只能使用一次。
   只有一台手机时，也可以直接用管理员凭据登录。
5. 在消息通知设置主动开启通知，允许 iOS 授权，然后发送测试通知。
6. 发起一次小型搜索，退出页面，稍后返回查看报告；再创建一个几分钟后的定时任务进行验证。

iPhone Web Push 需要 iOS 16.4+ 的主屏幕 Web App，详见
[WebKit 官方说明](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)。
Safari 与主屏幕应用可能需要分别登录，建议在主屏幕应用内配对。
系统通知是否送达还受网络、通知授权和系统设置影响。

手机登录有效期为 30 天，到期重新配对即可，计划仍由服务器执行。
更换域名后需要重新登录并重新订阅推送。设备丢失时，在管理员设备撤销绑定。

## 6. 验收清单

- 未登录的浏览器不能读取任务、资料和设置；直接请求 `/api/history` 返回 401。
- iPhone 用蜂窝网络访问 HTTPS 页面，绑定、发任务、查看报告正常。
- 关闭电脑和手机页面后，服务器上的定时任务仍执行。
- 通知测试送达，点击后打开正确的 SearchOS 页面。
- `status` 中 API/网页为 healthy，手机显示主机在线、服务器托管。
- 空闲时重启 API，设备仍保持登录，已有配置与报告不丢失：
  `docker compose --env-file deploy/.env -f deploy/compose.yaml restart api`。
- 重启云主机后服务恢复；备份在另一个空卷恢复成功。

## 7. 数据、备份与恢复

`searchos_data` 命名卷包含全部个人状态：`assistant/`（SQLite、管理员凭据、推送密钥）、
`workspaces/`（研究记录）、`knowledge/`（知识库）、`secrets.env`、`web_settings.json`、
`skills/`（可编辑技能快照）、`local-index/`、`browser-auth/` 和 `home/`。
只有 API 挂载该卷，网页容器和 Caddy 不能读取其中的密钥。

技能库首次复制到数据卷，升级时保留用户修改，不自动覆盖；更新内置技能需要单独审查合并。
Caddy 证书存在另两个独立命名卷中，可由 Caddy 重新申请，不在应用备份内。

确认没有研究、资料索引或导入任务正在执行，再运行：

```bash
bash deploy/searchos.sh backup
# 或指定绝对路径
bash deploy/searchos.sh backup /安全目录/searchos-backup.tgz
```

备份命令会停止服务以获得一致快照，完成或失败后恢复原先运行的服务。
备份包含所有密钥，权限设为仅当前用户可读写；请加密保存到服务器之外，不要提交到 Git。
首次使用先备份一次，以后按数据变更频率备份；当前没有自动备份调度。

恢复只能写入**空数据卷**，不会覆盖现有资料。先准备相同版本代码/镜像与 `deploy/.env`，
再在新服务器运行；也可以用不同 Compose 项目名创建独立空卷：

```bash
# 同一台机器演练前先停旧实例，避免端口冲突和重复调度
bash deploy/searchos.sh stop
COMPOSE_PROJECT_NAME=searchos-restored bash deploy/searchos.sh restore /安全目录/searchos-backup.tgz
COMPOSE_PROJECT_NAME=searchos-restored bash deploy/searchos.sh up
```

以后管理此实例也要带同样的 `COMPOSE_PROJECT_NAME=searchos-restored`。
恢复会带回原来的活跃计划，启动前确认旧实例已停；不要同时运行两个恢复自同一备份的实例。
不要执行 `docker compose down -v`，它会删除数据卷。

## 8. 升级与回退

1. 确认任务空闲，记录当前 Git 提交/版本，执行备份并保存到服务器外。
2. 切换到明确的新发布版本，阅读变更说明。
3. 执行 `build`。构建期间旧服务仍运行；失败时不要继续升级。
4. 执行 `up` 替换容器，再执行 `status` 和手机验收。

若新版失败，先停止服务，切回旧代码并重新构建；涉及数据结构变化时，
必须在空卷恢复升级前的备份，不能只回退镜像后继续读取新版数据库。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| Docker 下载/构建失败 | 服务器到镜像、pip、npm、Chromium 和字体服务的网络；磁盘与内存；不要关闭 TLS 校验 |
| `up` 超时 | 查看 `status` 和 `logs`；首次技能复制、依赖启动需要时间；修复后重新 `up` |
| 证书申请失败 | 域名 A/AAAA 是否正确，80/443 是否被安全组或其他服务拦截；先检查 Caddy 日志 |
| 页面可开但 API 403 | 必须通过配置的 HTTPS 域名访问，不可混用 IP、HTTP 或其他域名；私网不等于可省略 HTTPS |
| 管理员登录 429 | 多次错误尝试会限流，等待 15 分钟后确认凭据再试 |
| 搜索失败 | 模型与搜索服务的 Key、余额、模型名、区域可达性；查看设置及任务错误 |
| 通知未到 | 主屏幕应用、iOS 版本、权限、真实联系邮箱、服务器到推送服务的网络 |
| 技能执行权限不足 | 镜像以非 root 运行，不提供宿主机管理权限；不要用 privileged 解决 |

如果需要私网部署，可复用 API/Web 镜像和数据卷，换成自己的私网 HTTPS 入口。
当前标准 Compose 面向公网域名自动证书；不附带 VPN、不自动配置 Tailscale。
请保留同源路径、Host/Origin、WebSocket 转发及 `SF_PUBLIC_ORIGIN`，不要只把域名换成局域网 IP。

## 维护者：镜像和验证

`.github/workflows/cloud-deploy.yml` 在 Linux Runner 构建并验证三个服务，
覆盖 HTTPS、未登录拒绝、管理员登录、一次性配对、重启后登录保持及备份恢复。
CI 的 `localhost` 使用本地 CA，仅测试脚本跳过其证书验证；真实部署必须使用有效 HTTPS 证书。
这不替代真实 iPhone、Apple 推送、模型搜索、云主机重启和 DNS/公网证书验收。

未来发布官方镜像时，使用固定版本标签，并在 `deploy/.env` 指定
`SEARCHOS_API_IMAGE`、`SEARCHOS_WEB_IMAGE`，拉取对应镜像后执行 `up`；
必须先实际发布镜像再将“直接拉取”写成默认安装方式。
