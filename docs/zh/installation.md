# 安装 SearchOS

[English](../installation.md) | **简体中文**

推荐在 macOS 或 Linux 上使用仓库根目录的一键安装脚本。脚本会创建独立的 `.venv`、安装 SearchOS 与 Access Skill 依赖、下载 Playwright Chromium，并通过 `npm ci` 安装锁定版本的 Web 前端依赖。

## 环境要求

- Python 3.11 或更高版本
- Node.js 20.9 或更高版本（使用 Web 前端时）
- npm

脚本会优先选择 `python3.13`、`python3.12`、`python3.11`，避免 macOS 自带的旧版 `python3` 被误用。

## 一键安装

```bash
./install.sh
source .venv/bin/activate
```

安装完成后可直接运行：

```bash
searchos
./web/start.sh
```

首次启动 SearchOS 时，配置向导会引导选择模型提供商并写入 `.env`。

## 安装模式

```bash
./install.sh --core          # 仅安装 CLI/TUI 与 Web 后端的基础 Python 依赖
./install.sh                 # 默认：基础依赖 + 全部 Access Skill + Chromium + Web 前端
./install.sh --all           # 再加入评测、可选搜索/浏览后端与可观测性依赖
./install.sh --dev           # 默认安装基础上加入 pytest 与 Ruff
./install.sh --all --dev     # 完整开发环境
./install.sh --no-web        # 不安装 Web 前端依赖
./install.sh --no-browser    # 不下载 Chromium
```

可通过环境变量或参数指定解释器与虚拟环境：

```bash
PYTHON=/path/to/python3.12 ./install.sh
./install.sh --python /path/to/python3.12 --venv .venv-searchos
```

## 手动安装

如果不使用安装脚本，可以按需安装依赖组：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .             # CLI/TUI 与 Web 后端
python -m pip install -e ".[access]"  # 仓库内 Access Skill
python -m pip install -e ".[dev]"     # 测试与静态检查
python -m pip install -e ".[all]"     # 所有可选运行依赖
```

手动安装 Access Skill 后，如需运行基于浏览器的 Skill，还需执行：

```bash
python -m playwright install chromium
```

Web 前端使用锁文件安装：

```bash
npm ci --prefix web/frontend
```

## 安装自检

一键安装脚本会自动运行以下检查：

```bash
python -m pip check
searchos --help
```

如果 `./web/start.sh` 提示 Python 版本过低或找不到 SearchOS，请先执行 `./install.sh`；启动脚本会优先使用仓库中的 `.venv`。

## `searchos` 命令指向其他仓库

如果 `python -m searchos` 可以启动，但 `searchos` 的错误堆栈指向另一个目录，说明 Shell 命中了其他环境安装的同名命令。先检查：

```bash
command -v searchos
head -n 5 "$(command -v searchos)"
```

然后激活当前仓库的一键安装环境并刷新 Shell 缓存：

```bash
source .venv/bin/activate
hash -r
command -v searchos
```

最后一条命令应输出当前仓库的 `.venv/bin/searchos`。无需激活时，也可以直接运行：

```bash
./.venv/bin/searchos
```

不要通过补充错误堆栈中要求的 API Key 来绕过这个问题；那会继续运行另一个仓库的代码。
