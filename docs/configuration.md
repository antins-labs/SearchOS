# 配置体系分层

SearchOS 的配置由五层叠加而成，**上层覆盖下层**。理解每层"谁写、谁读、何时读"
即可推断任何配置改动的生效时机。

```
L5  per-run 请求覆盖        POST /api/search 请求体（effort / max_time / skills）
L4  web 覆盖层              web_settings.json（web 设置页写入的增量）
L3  显式 env 覆写           SF_PROFILES__* / SF_ROLES__*（深合并到默认值上）
L2  SF_PROVIDER 预设        providers.py 按厂商生成默认 profiles / roles
L1  process env / .env      密钥 + 全部 SF_* knob 的基础层
```

## 各层职责

| 层 | 谁写 | 谁读 | 读取时机 |
|---|---|---|---|
| L1 `.env` | 手动编辑 / TUI 向导（`searchos --setup`）/ web 设置页 | 所有进程启动时 `load_dotenv` | 进程启动一次 |
| L2 预设 | `SF_PROVIDER` 环境变量 | `config/providers.py` | `Settings()` 构造时 |
| L3 覆写 | `.env` 中的 `SF_PROFILES__*` 等 | `config/settings.py` validator | `Settings()` 构造时 |
| L4 web 覆盖层 | web 设置 API（`web/api/settings_store.py`） | API 启动 `load_and_apply()`；每次变更即时应用 | 启动 + 每次 PUT |
| L5 per-run | 前端 Composer 的 run overrides | `web/api/routes/search.py` | 每次发起搜索 |

## 密钥流转

- **`.env` 是唯一的密钥持久化点**。三个写入口：手动编辑、TUI 配置向导、web 设置页
  （`PUT /api/settings/provider` 与 `PUT /api/settings/keys`）——共用
  `searchos/config/env_file.py` 的原子写（tmp + `os.replace`，原位替换保留注释）。
- Web API 写 `.env` 时变量名走**白名单**（各预设/profile 的 `api_key_env` +
  搜索/浏览后端 key），值经 `validate_env_value` 校验（拒绝换行、引号、`#` 等，
  防 .env 行注入）。
- **任何 API 响应与日志绝不包含密钥值**——只有 `key_set` / `api_key_set` 布尔。
- 跨进程并发写（TUI 与 web 同时改 `.env`）是 last-writer-wins；进程内 web 侧
  在一把 asyncio 锁下串行。

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
- `searchos/config/env_file.py` — `.env` 原子读写与值校验
- `searchos/config/effort.py` — effort 档位（TUI `/effort` 与 web 共用）
- `web/api/settings_store.py` — L4 覆盖层的持久化与运行时应用
- `web/api/routes/models.py` / `routes/settings.py` — 设置 API 端点
