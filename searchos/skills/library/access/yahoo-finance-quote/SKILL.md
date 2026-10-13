---
name: yahoo-finance-quote
description: 从 Yahoo Finance 获取股票实时报价、历史价格数据（支持指定日期范围）及公司基本信息。适用于查询美股、港股等证券的行情数据。
metadata:
  searchos-category: access
  host: finance.yahoo.com
---

# Yahoo Finance 股票数据技能

从 Yahoo Finance 获取股票报价和历史价格数据。

## 能力概览

| 命令 | 用途 | 输出 |
|------|------|------|
| `get-quote` | 获取股票实时报价和基本信息 | 当前价格、涨跌幅、52周高低、交易量等 |
| `get-history` | 获取历史价格数据（支持日期范围） | OHLCV 日线/小时线数据 |

## 使用指南

### 获取实时报价

```bash
python scripts/quote.py AAPL
python scripts/quote.py MSFT --output quote.json
```

输出字段：
- `symbol`: 股票代码
- `name`: 公司名称
- `price`: 当前价格
- `change_percent`: 涨跌幅百分比
- `volume`: 成交量
- `day_high` / `day_low`: 日内最高/最低价
- `fifty_two_week_high` / `fifty_two_week_low`: 52周高低
- `currency`: 货币
- `exchange`: 交易所

### 获取历史价格

```bash
# 最近30天日线
python scripts/history.py AAPL --days 30

# 指定日期范围
python scripts/history.py AAPL --start 2026-09-01 --end 2026-10-12

# 不同时间粒度
python scripts/history.py AAPL --days 5 --interval 1h
python scripts/history.py AAPL --days 30 --interval 1d
python scripts/history.py AAPL --days 365 --interval 1wk

# 输出到文件
python scripts/history.py AAPL --days 30 --output history.json
```

支持的 interval 参数：
- `1m`, `5m`, `15m`, `30m`, `60m`, `1h`: 分钟/小时线
- `1d`: 日线（默认）
- `1wk`: 周线
- `1mo`: 月线

## 参数说明

### quote.py

| 参数 | 必填 | 说明 |
|------|------|------|
| `symbol` | 是 | 股票代码（如 AAPL, MSFT） |
| `--output`, `-o` | 否 | 输出 JSON 文件路径（默认打印到 stdout） |

### history.py

| 参数 | 必填 | 说明 |
|------|------|------|
| `symbol` | 是 | 股票代码 |
| `--days` | 二选一 | 获取最近 N 天数据 |
| `--start`, `--end` | 二选一 | 指定日期范围（格式 YYYY-MM-DD） |
| `--interval`, `-i` | 否 | 时间粒度，默认 `1d` |
| `--output`, `-o` | 否 | 输出 JSON 文件路径 |

## 输出格式

### quote.py 输出

```json
[
  {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "price": 336.64,
    "change_percent": -1.11,
    "currency": "USD",
    "exchange": "NasdaqGS",
    "volume": 37881199,
    "day_high": 338.61,
    "day_low": 330.7,
    "fifty_two_week_high": 345.34,
    "fifty_two_week_low": 243.42,
    "market_time": "2026-10-09 20:00:00",
    "source_url": "https://finance.yahoo.com/quote/AAPL/"
  }
]
```

### history.py 输出

```json
{
  "symbol": "AAPL",
  "interval": "1d",
  "data": [
    {
      "date": "2026-10-09",
      "open": 331.7,
      "high": 338.61,
      "low": 330.7,
      "close": 336.64,
      "volume": 37855000
    }
  ],
  "source_url": "https://finance.yahoo.com/quote/AAPL/history"
}
```

## 错误处理

- 无效股票代码：返回错误信息，退出码 1
- 网络错误：返回错误信息，退出码 1
- 参数缺失：显示帮助信息，退出码 1

## 数据来源

所有数据来自 Yahoo Finance Query API：
- 报价数据：`https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`
- 历史数据：同上，支持 period1/period2 时间戳参数

## 依赖

- Python 3.7+
- 仅使用标准库（urllib, json, datetime）

## 限制

- API 无需认证，但可能受速率限制
- 分钟级数据仅提供最近7天
- 数据可能有15-20分钟延迟