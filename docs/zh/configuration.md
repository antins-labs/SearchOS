# 配置体系分层

[English](../configuration.md) | **简体中文**

SearchOS 的配置分两条主线：**密钥留在 `.env`，其余一切可调项留在 overlay
（`web_settings.json`）**。overlay 是 Web 与 CLI/TUI 共享的单一用户配置源，**最后
叠加、优先级最高**。理解每层"谁写、谁读、何时读"即可推断任何配置改动的生效时机。

```
L5  per-run 请求覆盖        POST /api/search 请求体（effort / max_time / skills）
L4  overlay（唯一用户配置源） web_settings.json —— effort / skills / models /
                            run_defaults / advanced；Web 与 TUI 共同读写
L3  显式 SF_* 覆写（高级/兼容） .env 中的 SF_PROFILES__* / SF_ROLES__* 等，深合并
L2  SF_PROVIDER 预设        providers.py 按厂商生成默认 profiles / roles
L1  .env（只放密钥）         各 *_API_KEY 值 —— process env 基础层
```

**precedence**：代码默认 → `SF_*` env（L2/L3）→ overlay（L4）。冲突时 overlay 赢。
`SF_*` 仍可用（power user / 向后兼容），但**不再是推荐路径**；日常配置走
`searchos --setup`、Web 设置页、或 TUI 的 `/effort` `/skill` `/search` `/config`。

## 各层职责

| 层 | 谁写 | 谁读 | 读取时机 |
|---|---|---|---|
| L1 `.env` | 手动 / `searchos --setup` / web 设置页（仅密钥值） | 所有进程启动 `load_dotenv` | 进程启动一次 |
| L2 预设 | `SF_PROVIDER` 环境变量 | `config/providers.py` | `Settings()` 构造时 |
| L3 覆写 | `.env` 中的 `SF_PROFILES__*` 等 | `config/settings.py` validator | `Settings()` 构造时 |
| L4 overlay | web 设置 API / TUI 命令 / 向导（`web/api/settings_store.py` + `config/web_overlay.py`） | `load_and_apply()`；每次变更即时应用 | 启动 + 每次写入 |
| L5 per-run | 前端 Composer 的 run overrides | `web/api/routes/search.py` | 每次发起搜索 |

## overlay 的四个区

- **effort**：预算档位（low/medium/high/max）+ 逐 knob 覆盖（并发、迭代、每代理
  搜索/发现数、墙钟上限、skill router top-k）。见 `config/effort.py` 的 `EFFORT_KEYS`。
- **skills**：`access_only` / `access_deny` / `strategy_deny` / `orchestrator_deny`。
  （env 层的 `SEARCHOS_SKILL_LAYERS_DISABLED` / `SEARCHOS_SKILL_ONLY` 仍作为高级
  调试开关保留，但常规路径是 overlay / UI。）
- **models**：provider 连接、模型卡（custom_profiles / profile_overrides）、角色
  绑定、`search_provider`、`browser_backend`。
- **advanced**：effort 覆盖不到的一等公民 knob——`llm_max_retries`、
  `browser_disk_cache_dir`、`https_proxy`。`https_proxy` 不是 `settings` 字段，
  `apply_to_runtime()` 会把它**反向导出到 `os.environ` 的 `HTTP_PROXY`/`HTTPS_PROXY`**
  （空值则移除），因此 `.env` 里不再需要代理；`search_max_results` 走 `run_defaults`。

## 密钥流转

- **`.env` 只放密钥值**（各 `*_API_KEY` / `RAGFLOW_USER_ID` 等），是唯一的密钥
  持久化点。三个写入口：手动编辑、`searchos --setup`、web 设置页
  （`PUT /api/settings/provider` 与 `PUT /api/settings/keys`）——共用
  `searchos/config/env_file.py` 的原子写（tmp + `os.replace`，原位替换保留注释）。
- 代理（`HTTPS_PROXY`）**不再当作 .env key**：它属 overlay 的 advanced 区，经
  `PUT /api/settings/advanced` 写入、运行时导出到 `os.environ`。
- Web API 写 `.env` 时变量名走**白名单**（各预设/profile 的 `api_key_env` +
  搜索/浏览后端 key），值经 `validate_env_value` 校验（拒绝换行、引号、`#` 等，
  防 .env 行注入）。
- **任何 API 响应与日志绝不包含密钥值**——只有 `key_set` / `api_key_set` 布尔。
  代理 / 缓存目录**不是密钥**，其值会在设置页回显、可编辑。
- 跨进程并发写（TUI 与 web 同时改 `.env`）是 last-writer-wins；进程内 web 侧
  在一把 asyncio 锁下串行。

## 从旧 .env 迁移

`load_and_apply()` 启动时调 `migrate_legacy_env_into_overlay()`：把旧
`.env`/env 里的 `SF_ENABLE_SKILLS` / `SF_SEARCH_PROVIDER` / `SF_BROWSER_DISK_CACHE_DIR`
/ `HTTP(S)_PROXY` **非破坏性地 seed 进 overlay**（overlay 对应字段为空时才写），
行为不变、幂等。物理清理 `.env` 里这些旧行走显式动作：重跑 `searchos --setup`
结束时会提示确认删除（值已进 overlay）。Web 侧因 overlay 优先，旧 .env 行自动失活。

## CLI/TUI 与 Web 的一致性

- 搜索后端：CLI 的 `_setup_provider` 与 web 的 `init_search_provider` 都读
  overlay 的 `models.search_provider`（未配时回落 `SF_SEARCH_PROVIDER` → 按 key 推断
  → ragflow）。
- TUI 的 `/effort`、`/skill`、`/search`、`/model`、`/config` 都**写回 overlay 并
  `save_overlay()`**，重启后保留、与 web 设置页同源。
- `/config`（无参）打开 **交互式设置面板**（`searchos/tui/config_modal.py`，
  Claude-Code 风格：↑↓ 选择、回车 编辑/切换/进入子菜单、←→ 切换枚举值、Esc 逐级
  返回，改动即时生效并落盘）——覆盖与 web 设置页对等的全部区：Model（角色绑定 /
  模型卡增删改 / Provider 连接增删改 + key 录入）、Search（后端 / key / 结果数 /
  代理）、Browse（浏览后端 / Jina key / 缓存目录）、Budget（effort / 墙钟 / 重试）、
  Runtime（技能总开关）。`/model` 直达 Model 区；`/config <项> <值>` 仍可快改。
- 面板里录入的 API key **值走 `.env` 原子写**（与 web/向导同一写入点），界面只显示
  ●已设置/○未设置，绝不回显。

## 生效时机（快照 vs 实时读）

| 配置 | 读取方式 | 运行时改 env 后 |
|---|---|---|
| 模型 API key（`profile.api_key_env`） | `get_model_for()` 每次调用现读 `os.environ` | 新 session 立即生效 |
| `SERPER_API_KEY` / `TAVILY_API_KEY` / `RAGFLOW_*` | 每次构造搜索 provider 时现读 | 下次搜索立即生效 |
| `SF_PROVIDER` / `SF_MODEL` / `SF_API_BASE` / `SF_JINA_API_KEY` 等 `SF_*` | `settings = Settings()` **import 时快照** | 需 `reload_settings_in_place()` |

Web 端点改 env 后统一走 `settings_store.update_env()` 事务：

```
锁内：os.environ 先行更新 → Settings() dry-run（失败则回滚 environ，不落盘）
    → .env 原子写盘 → reload_settings_in_place() → 重放 L4 覆盖层
```

最后一步的重放是**必须的**：原地重建单例会把 effort 档位等 web 设置重置回
env 基础值，`apply_to_runtime()` 负责把 L4 增量重新压回去。

切换 provider 预设时还会：清空 L4 的 role 覆写与 per-profile 字段覆写（预设的
profile 名整体更换，旧值必然悬空或错配）、清除上一家厂商遗留的
`SF_MODEL`/`SF_FAST_MODEL`/`SF_API_BASE` 覆写（除非请求中显式指定）。运行中的
session 不受影响——模型结构在 `SearchSession` 构造时已快照。

L4 还承载 per-profile 定制（web 设置页 Models 区的 profile 卡）：

- **字段覆写**（`models.profile_overrides`）：对预设/内置 profile 的
  model / api_base / api_key_env 做稀疏覆盖，可单字段清除还原。之所以不走
  L3 的 `SF_PROFILES__*`：env 变量名寻址不了带点的 profile 名（如
  `qwen3.5-35b`），且切换预设时无法安全清理 .env 行。
- **自定义 profile**（`models.custom_profiles`）：用户新建的完整 profile
  （model + 协议 + api_base + api_key_env），跨 provider 切换保留，可绑定到
  任意角色；`main`/`judge`/`fast`/`synthesis`/`reformat` 为预设保留名不可用。

## 相关模块

- `searchos/config/settings.py` — Settings 单例 + `reload_settings_in_place()`
- `searchos/config/profiles.py` — `ModelProfile` / `ROLE_NAMES` / 内置默认 profiles
- `searchos/config/providers.py` — `SF_PROVIDER` 预设注册表（见 [providers.md](providers.md)）
- `searchos/config/env_file.py` — `.env` 原子读写、值校验、`remove_env_keys`
- `searchos/config/web_overlay.py` — overlay 数据模型、`apply_to_runtime()`、迁移函数（Web 与 CLI/TUI 共享）
- `searchos/config/effort.py` — effort 档位（TUI `/effort` 与 web 共用）
- `web/api/settings_store.py` — L4 overlay 的写事务（锁 + dry-run 回滚 + reload 重放）
- `web/api/routes/models.py` / `routes/settings.py` — 设置 API 端点
