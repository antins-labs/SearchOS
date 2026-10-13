# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Federal Register Access Skill

Access structured data from the Federal Register (federalregister.gov) - the official daily publication for rules, proposed rules, notices, and presidential documents of the U.S. federal government.

## Capabilities

This skill provides reliable API access to:

- **Document Retrieval**: Get full metadata for any Federal Register document by document number
- **Document Search**: Search with powerful filters including:
  - Full-text keyword search
  - President name (for presidential documents)
  - Agency name or ID
  - Document type (Rule, Proposed Rule, Notice, Presidential Document)
  - Publication date range
  - CFR title/part references
  - Topic categories
- **Agency Information**: Browse and retrieve agency details
- **Topic Categories**: Access the Federal Register topic taxonomy
- **Public Inspection**: View documents before official publication

## Document Types

- **RULE**: Final rules and regulations
- **PRORULE**: Proposed rules
- **NOTICE**: Agency notices
- **PRESDOCU**: Presidential documents (Executive Orders, Proclamations, Memoranda, etc.)

## Example Queries

### Get a specific Executive Order
```
function: get_document
document_number: "2025-02096"
```
Returns: "Restoring Names That Honor American Greatness" (EO 14172)

### Search presidential documents by president
```
function: search_documents
president: "donald-trump"
publication_year: 2025
type: "PRESDOCU"
order: "newest"
```

### Search by agency and date range
```
function: search_documents
agency_slug: "environmental-protection-agency"
publication_date_gte: "2025-01-01"
publication_date_lte: "2025-01-31"
per_page: 50
```

### Full-text keyword search
```
function: search_documents
query: "clean air act"
order: "newest"
per_page: 20
```

### Get agency details
```
function: get_agency
agency_slug: "executive-office-of-the-president"
```

### List all agencies
```
function: list_agencies
```

### Browse topics
```
function: list_topics
```

### Get public inspection documents
```
function: get_public_inspection
available_on: "2025-01-31"
```

## Returned Data

Each document includes:
- Document number and citation (e.g., "90 FR 8629")
- Title and abstract
- Type and subtype (e.g., "Presidential Document" / "Executive Order")
- Publication date and signing date
- Agencies involved
- Executive order number / proclamation number (if applicable)
- Page range and volume
- CFR references
- Links to PDF, HTML, and XML full text
- Page view counts

## Notes

- The Federal Register API is free and does not require authentication
- Document numbers follow format: YYYY-NNNNN (year-sequential number)
- Citation format: Volume FR Page (e.g., "90 FR 8629")
- Presidential documents include Executive Orders, Proclamations, Memoranda, and Determinations
- The API respects rate limits; high-volume access should use appropriate delays
