# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ACL Wiki Best Paper Awards

Fetches best paper award data from the ACL Wiki, which maintains structured tables of award-winning papers from major computational linguistics conferences.

## Data Source

- **URL**: https://www.aclweb.org/aclwiki/Best_paper_awards
- **Conferences Covered**: ACL, NAACL, EMNLP, IJCNLP
- **Data Range**: 2001-2019 (last updated July 2021)
- **Total Papers**: ~80 award-winning papers

## Available Functions

### list_conferences

Lists all conferences with best paper awards and their statistics.

**Example**:
```json
{
  "function": "list_conferences"
}
```

**Returns**:
- Conference names (ACL, NAACL, EMNLP, IJCNLP)
- Paper counts per conference
- Year range for each conference

### list_awards

Lists all best paper awards, optionally filtered by conference.

**Parameters**:
- `conference` (optional): Filter by conference name (ACL, NAACL, EMNLP, or IJCNLP)

**Examples**:
```json
{
  "function": "list_awards"
}
```

```json
{
  "function": "list_awards",
  "conference": "ACL"
}
```

**Returns**:
- Paper title
- Author(s)
- Year
- Conference
- URL to ACL Anthology (when available)

### get_awards_by_year

Gets all best paper awards for a specific year across all conferences.

**Parameters**:
- `year` (required): The year to filter by (e.g., "2019")

**Example**:
```json
{
  "function": "get_awards_by_year",
  "year": "2019"
}
```

**Returns**:
- All award-winning papers from the specified year
- Conference for each paper
- Paper details including title, author, and anthology URL

## Data Fields

Each award entry includes:
- `year`: Year the award was given (2001-2019)
- `author`: Author name(s)
- `title`: Paper title
- `url`: Link to ACL Anthology entry (may be null for some entries)
- `conference`: The conference (ACL, NAACL, EMNLP, or IJCNLP)

## Notable Papers

Some famous award-winning papers include:
- **BERT** (NAACL 2019): "Pre-training of Deep Bidirectional Transformers for Language Understanding"
- **Accurate Unlexicalized Parsing** (ACL 2003): Dan Klein and Chris Manning
- **Discriminative Training Methods for HMMs** (EMNLP 2002): Michael Collins

## Notes

- The ACL Wiki is a community-maintained resource; some entries may be incomplete
- A few anthology URLs may be missing or malformed in the source data
- The wiki page was last updated in July 2021; for more recent awards, check the official ACL Anthology
- Papers without proper anthology links will have `url: null`
