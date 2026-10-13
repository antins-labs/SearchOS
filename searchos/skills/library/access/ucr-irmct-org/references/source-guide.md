# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# UN ICTR/MICT Case Documents Access Skill

This skill provides structured access to the United Nations International Criminal Tribunal for Rwanda (ICTR) and Mechanism for International Criminal Tribunals (MICT) case documents database at [ucr.irmct.org](https://ucr.irmct.org).

## Overview

The database contains legal documents from international criminal tribunals, including:
- Judgments and sentences
- Trial and appeals chamber decisions
- Court orders
- Transcripts
- Indictments
- Motions and applications
- Witness lists
- And more

## Functions

### get_case_detail

Retrieve basic case information including the case ID, case number, and defendant/description.

**Parameters:**
- `case_number` (required): Case number (e.g., "ICTR-97-23", "MICT-13-38")

**Example:**
```json
{
  "function": "get_case_detail",
  "case_number": "ICTR-97-23"
}
```

**Returns:**
```json
{
  "success": true,
  "case": {
    "case_id": 1484,
    "case_number": "ICTR-97-23",
    "description": "KAMBANDA, JEAN"
  }
}
```

### get_documents

Retrieve documents for a case with optional filtering by language and document type.

**Parameters:**
- `case_number` (required): Case number
- `language` (optional): Language filter (ENG, FRA, KIN, HBS, OTH)
- `doc_type` (optional): Document type filter (Jdg, Dec, Ord, TRA, IND, etc.)

**Example:**
```json
{
  "function": "get_documents",
  "case_number": "ICTR-97-23",
  "language": "ENG",
  "doc_type": "Jdg"
}
```

**Returns:**
```json
{
  "success": true,
  "case_number": "ICTR-97-23",
  "language_filter": "ENG",
  "doc_type_filter": "Jdg",
  "total_documents": 2,
  "documents": [
    {
      "document_id": 2000546682,
      "title": "KAMBANDA - APPEAL JUDGEMENT",
      "case_number": "ICTR-97-23",
      "document_type": "Jdg",
      "document_type_desc": "Judgement/Sentence",
      "document_source": "APC",
      "document_source_desc": "Appeals Chamber",
      "filing_date": "20/10/2000",
      "language": "ENG",
      "document_path": "http://icr.icty.org/LegalRef/..."
    }
  ]
}
```

### get_documents_by_category

Retrieve documents grouped by document type, showing counts and document lists per category.

**Parameters:**
- `case_number` (required): Case number

**Example:**
```json
{
  "function": "get_documents_by_category",
  "case_number": "ICTR-97-23"
}
```

**Returns:**
```json
{
  "success": true,
  "case_number": "ICTR-97-23",
  "total_documents": 42,
  "categories": {
    "Dec": {
      "type_code": "Dec",
      "type_description": "Decision",
      "count": 19,
      "documents": [...]
    },
    "TRA": {
      "type_code": "TRA",
      "type_description": "Transcript",
      "count": 12,
      "documents": [...]
    }
  }
}
```

### search_documents

Search documents with text query and date range filters.

**Parameters:**
- `case_number` (required): Case number
- `query` (optional): Text to search in document titles
- `date_from` (optional): Start date (DD/MM/YYYY format)
- `date_to` (optional): End date (DD/MM/YYYY format)

**Example:**
```json
{
  "function": "search_documents",
  "case_number": "ICTR-97-23",
  "query": "appeal",
  "date_from": "01/01/2000",
  "date_to": "31/12/2000"
}
```

## Document Types

| Code | Description |
|------|-------------|
| Jdg | Judgement/Sentence |
| Dec | Decision |
| Ord | Order |
| TRA | Transcript |
| IND | Indictment |
| REV | Revised Indictment |
| ADL | Amended Indictment |
| MOT | Motion |
| APP | Application |
| WIT | Witness List |
| SUB | Submission |
| REQ | Request |
| BRP | Pre-Trial Brief |
| BRI | Brief |
| WSS | Warrant Search |
| WAA | Warrant Arrest |
| TAP | Court Recording/Video |

## Document Sources

| Code | Description |
|------|-------------|
| APC | Appeals Chamber |
| JUD | Trial Chamber |
| TCI | Trial Chamber I |
| TII | Trial Chamber II |
| PRE | President |
| REG | Registry |

## Languages

| Code | Language |
|------|----------|
| ENG | English |
| FRA | French |
| KIN | Kinyarwanda |
| HBS | Bosnian/Croatian/Serbian |
| OTH | Other |

## Case Number Format

Case numbers follow the format:
- **ICTR-XX-XX**: International Criminal Tribunal for Rwanda cases (e.g., ICTR-97-23)
- **MICT-XX-XX**: Mechanism for International Criminal Tribunals cases (e.g., MICT-13-38)

## Notes

- Document paths in the results link to PDF files hosted on the ICTY/MICT document repository
- Some cases may have large document sets; consider using language or document type filters
- Date format throughout the API is DD/MM/YYYY
- The database primarily contains documents from completed ICTR cases and ongoing MICT cases
