# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# UN Membership Data Access Skill

This skill fetches structured data from the United Nations official website (un.org) about UN membership and organ compositions.

## Available Functions

### get_member_states

Retrieves a complete list of all 193 UN member states with their admission dates.

**Returns:**
- `count`: Total number of member states
- `members`: Array of objects containing:
  - `name`: Country name
  - `admission_date`: Date of UN admission in DD-MM-YYYY format

**Example:**
```json
{
  "count": 193,
  "members": [
    {"name": "Afghanistan", "admission_date": "19-11-1946"},
    {"name": "Albania", "admission_date": "14-12-1955"},
    ...
  ]
}
```

### get_security_council

Retrieves current Security Council membership including permanent and non-permanent members.

**Returns:**
- `total_members`: 15
- `permanent_members`: Array of 5 permanent member country names
- `non_permanent_members`: Array of objects containing:
  - `country`: Country name
  - `term_end_year`: Year when term ends
- `source_url`: Link to official page

**Example:**
```json
{
  "total_members": 15,
  "permanent_members": ["China", "France", "Russian Federation", "United Kingdom", "United States"],
  "non_permanent_members": [
    {"country": "Algeria", "term_end_year": 2025},
    ...
  ]
}
```

### get_icj_judges

Retrieves current International Court of Justice judges with their roles and membership details.

**Returns:**
- `total_judges`: Number of current judges
- `judges`: Array of objects containing:
  - `name`: Judge's name
  - `country`: Country of origin
  - `role`: "President", "Vice-President", or "Judge"
  - `member_since`: Date information
- `source_url`: Link to official ICJ page

### get_organ_overview

Retrieves overview information about all principal UN organs (General Assembly, Security Council, ECOSOC, Trusteeship Council, ICJ).

**Returns:**
- `organs`: Dictionary keyed by organ name with descriptions
- `source_url`: Link to official overview page
- `note`: Guidance for getting detailed membership lists

## Data Sources

- Member States: https://www.un.org/en/about-us/member-states
- Security Council: https://www.un.org/securitycouncil/content/current-members
- ICJ Judges: https://www.icj-cij.org/en/current-members
- Organ Overview: https://www.un.org/en/about-us/membership-of-principal-un-organs

## Technical Notes

- Member states data is fetched via direct HTTP requests (reliable)
- Security Council and ICJ data may require browser automation for full content
- All data is parsed from official UN web pages
- Date formats follow the UN's DD-MM-YYYY convention for admission dates
