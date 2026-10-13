# Yahoo Finance 能力说明

## 已验证的 API 端点

### V8 Chart API

**端点**: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`

**用途**: 获取股票报价和历史价格数据

**参数**:
- `range`: 时间范围（1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max）
- `interval`: 数据粒度（1m, 2m, 5m, 15m, 30m, 60m, 1h, 1d, 5d, 1wk, 1mo, 3mo）
- `period1`: 开始时间戳（Unix timestamp）
- `period2`: 结束时间戳（Unix timestamp）

**验证测试**:

| 测试 | 参数 | 结果 |
|------|------|------|
| AAPL 日线 | range=1mo, interval=1d | ✓ 返回 22 条记录 |
| MSFT 日线 | range=1mo, interval=1d | ✓ 返回完整数据 |
| AAPL 小时线 | range=1mo, interval=1h | ✓ 返回 155 条记录 |
| AAPL 分钟线 | range=1mo, interval=5m | ✓ 返回 1717 条记录 |
| AAPL 周线 | range=1mo, interval=1wk | ✓ 返回 6 条记录 |
| 日期范围 | period1=1759507200, period2=1762108800 | ✓ 返回指定范围数据 |
| 无效代码 | symbol=INVALIDTICKER12345 | ✓ 返回 404 错误 |

**返回字段**:

Meta 字段:
- `symbol`: 股票代码
- `longName` / `shortName`: 公司名称
- `regularMarketPrice`: 当前价格
- `regularMarketChangePercent`: 涨跌幅百分比
- `regularMarketVolume`: 成交量
- `regularMarketDayHigh` / `regularMarketDayLow`: 日内高低价
- `fiftyTwoWeekHigh` / `fiftyTwoWeekLow`: 52周高低
- `currency`: 货币
- `fullExchangeName`: 交易所全名
- `exchangeTimezoneName`: 时区
- `regularMarketTime`: 市场时间戳
- `validRanges`: 支持的时间范围

OHLCV 字段（indicators.quote 数组）:
- `open`: 开盘价
- `high`: 最高价
- `low`: 最低价
- `close`: 收盘价
- `volume`: 成交量

## 未验证/不可用的 API

### V7 Quote API

**端点**: `https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}`

**状态**: 返回 401 Unauthorized

**原因**: 该 API 可能需要认证或已被弃用

### V10 Quote Summary API

**端点**: `https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}`

**状态**: 返回 401 Unauthorized

**原因**: 该 API 需要认证

## 功能映射

| 用户需求 | CLI 命令 | API 参数 |
|---------|---------|---------|
| 获取实时报价 | `quote.py {symbol}` | `range=1d&interval=1d` |
| 最近30天日线 | `history.py {symbol} --days 30` | `range=1mo&interval=1d` |
| 最近7天小时线 | `history.py {symbol} --days 7 --interval 1h` | `period1={ts1}&period2={ts2}&interval=1h` |
| 指定日期范围 | `history.py {symbol} --start YYYY-MM-DD --end YYYY-MM-DD` | `period1={ts1}&period2={ts2}` |

## 限制

1. **分钟级数据**: 仅提供最近7天
2. **数据延迟**: 可能有15-20分钟延迟
3. **速率限制**: 无认证 API 可能受速率限制
4. **无效代码**: 返回 HTTP 404

## 数据来源 URL

- 报价页面: `https://finance.yahoo.com/quote/{symbol}/`
- 历史数据页面: `https://finance.yahoo.com/quote/{symbol}/history`
- API 端点: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`