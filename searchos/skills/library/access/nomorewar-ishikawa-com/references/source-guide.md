# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Japanese Peace Museums Access Skill

This skill retrieves structured data about peace museums in Japan from the "戦争をさせない石川の会" (Ishikawa Association for Preventing War) website.

## Data Source

- **Website**: nomorewar-ishikawa.com
- **Page**: 日本国内の平和のための博物館 (Peace Museums in Japan)
- **Total Records**: 84 museums

## Available Functions

### 1. `list_all` - Get All Museums

Returns the complete list of all 84 peace museums with their IDs, names, and addresses.

```json
{
  "function": "list_all"
}
```

**Response includes:**
- `total_count`: Number of museums (84)
- `museums`: Array of museum objects with `id`, `name`, `address`

### 2. `search` - Search Museums

Search for museums by keyword in their name and/or address.

```json
{
  "function": "search",
  "query": "広島",
  "field": "all"
}
```

**Parameters:**
- `query` (required): Search keyword
- `field` (optional): Search scope - `"all"` (default), `"name"`, or `"address"`

### 3. `get_by_id` - Get Museum by ID

Retrieve a specific museum by its ID number (1-84).

```json
{
  "function": "get_by_id",
  "id": 59
}
```

**Example**: ID 59 returns the famous 広島平和記念資料館 (Hiroshima Peace Memorial Museum).

### 4. `list_by_prefecture` - Filter by Prefecture

List all museums located in a specific prefecture.

```json
{
  "function": "list_by_prefecture",
  "prefecture": "東京都"
}
```

**Common prefectures with museums:**
- 東京都 (Tokyo) - Multiple museums including wam, 東京大空襲・戦災資料センター
- 広島県 (Hiroshima) - 広島平和記念資料館, 原爆ドーム related facilities
- 長崎県 (Nagasaki) - 長崎原爆資料館, etc.
- 沖縄県 (Okinawa) - ひめゆり平和祈念資料館, etc.

## Sample Museums

| ID | Name | Address |
|----|------|---------|
| 1 | 笹の墓標展示館 | 北海道雨竜郡幌加内町字朱麹内 |
| 59 | 広島平和記念資料館 | 広島県広島市中区中島町１－２ |
| 74 | 長崎原爆資料館 | 長崎県長崎市平野町7番8号 |
| 78 | 沖縄県平和祈念資料館 | 沖縄県糸満市魔文仁６１４－１ |
| 83 | ひめゆり平和祈念資料館 | 沖縄県糸満市字伊原６７１－１ |

## Notes

- Data is sourced from the International Network of Peace Museums
- The page is in Japanese; all museum names and addresses are in Japanese
- Some museums are online-only (e.g., ID 21: 日本平和博物館)
- The website is a WordPress site with static table content
