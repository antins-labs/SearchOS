# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# East Money Fund F10 Data Access Skill

获取天天基金网 Fund F10 数据，包括基金股票持仓明细和累计买卖变动。

## 功能说明

### get_holdings - 获取基金持仓明细

获取基金最新报告期的股票持仓数据，包括 A 股和港股持仓。

**参数:**
- `code` (必填): 6位基金代码，如 "025925", "010350"
- `year` (可选): 查询年份，如 "2024", "2025"，不传则返回最新数据
- `topline` (可选): 返回的最大行数，默认 50

**返回数据结构:**
```json
{
  "fund_code": "025925",
  "fund_name": "景顺长城成长优选混合",
  "period": "2026Q2",
  "report_date": "2026-06-30",
  "years_available": [2026],
  "current_year": 2026,
  "holdings": {
    "a_shares": [
      {
        "rank": "1",
        "stock_code": "300502",
        "stock_name": "新易盛",
        "net_value_ratio": "9.89%",
        "shares": "14.83",
        "market_value": "8,999.38"
      }
    ],
    "hk_stocks": [
      {
        "rank": "1",
        "stock_code": "06181",
        "stock_name": "老铺黄金",
        "net_value_ratio": "9.05%",
        "shares": "37.16",
        "market_value": "20,522.92"
      }
    ]
  }
}
```

### get_changes - 获取基金重大交易变动

获取基金累计买入或卖出金额超出期初基金资产净值 2% 或前 20 名的股票明细。

**参数:**
- `code` (必填): 6位基金代码
- `change_type` (可选): 变动类型
  - `buy`: 累计买入 (默认)
  - `sell`: 累计卖出
- `year` (可选): 查询年份，不传则返回最新数据

**返回数据结构:**
```json
{
  "fund_code": "010350",
  "fund_name": "景顺长城品质长青混合A",
  "period": "2026Q2",
  "report_date": "2026-06-30",
  "change_type": "累计买入",
  "years_available": [2025, 2026],
  "current_year": 2026,
  "records": [
    {
      "rank": "1",
      "stock_code": "688498",
      "stock_name": "源杰科技",
      "amount": "66,072.57",
      "net_asset_ratio": "6.11%"
    }
  ]
}
```

## 使用示例

### 查询基金持仓
```json
{
  "function": "get_holdings",
  "code": "025925"
}
```

### 查询累计卖出
```json
{
  "function": "get_changes",
  "code": "010350",
  "change_type": "sell"
}
```

### 查询历史持仓
```json
{
  "function": "get_holdings",
  "code": "025925",
  "year": "2024"
}
```

## 数据来源

数据来自天天基金网 Fund F10 页面 API：
- 持仓明细: `fundf10.eastmoney.com/ccmx_{code}.html`
- 重大变动: `fundf10.eastmoney.com/ccbd_{code}.html`

## 注意事项

1. 基金代码必须是 6 位数字格式
2. 数据来自基金定期报告，存在报告期延迟
3. 部分新基金可能只有少量历史数据
4. 字段说明：
   - `net_value_ratio`: 占基金资产净值比例
   - `shares`: 持股数（万股）
   - `market_value`: 持仓市值（万元）
   - `amount`: 累计买入/卖出金额（万元）
