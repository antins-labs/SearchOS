# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# MU Health Care Laboratory Test Catalog Skill

This skill extracts structured medical reference ranges from the MU Health Care Laboratory Test Catalog at muhealth.testcatalog.org.

## Overview

The University of Missouri Health Care Laboratory Test Catalog, powered by Mayo Clinic Laboratories, provides comprehensive reference ranges for laboratory tests. This skill specializes in extracting and structuring CBC (Complete Blood Count) reference ranges and other test data.

## Features

### 1. Get Test Reference Ranges (`get_test_reference_ranges`)

Fetches structured reference ranges for a specific test code.

**Parameters:**
- `test_code` (optional, default: "CBCREF"): The test code identifier

**Example:**
```json
{
  "function": "get_test_reference_ranges",
  "test_code": "CBCREF"
}
```

**Returns:**
- Test name and code
- Structured reference ranges by analyte (RBC, Hemoglobin, WBC, etc.)
- Age-specific and sex-specific ranges where applicable

### 2. Search Test (`search_test`)

Searches for a test by name or code.

**Parameters:**
- `test_name` (optional): Test name to search for (e.g., "CBC", "Complete Blood Count")
- `test_code` (optional): Test code to look up directly

**Example:**
```json
{
  "function": "search_test",
  "test_name": "CBC"
}
```

## Supported Tests

The catalog includes reference ranges for various tests including:

- **CBCREF**: Complete Blood Count Reference Ranges
  - Red Blood Cell Count (RBC)
  - Hemoglobin
  - Hematocrit
  - Mean Corpuscular Volume (MCV)
  - Mean Corpuscular Hemoglobin (MCH)
  - Mean Corpuscular Hemoglobin Concentration (MCHC)
  - Red Cell Distribution Width (RDW, RDW-SD)
  - White Blood Cell Count (WBC)
  - Differential counts (Neutrophils, Lymphocytes, Monocytes, Eosinophils, Basophils)
  - Platelets
  - Mean Platelet Volume (MPV)
  - Immature Platelet Fraction (IPF)
  - Reticulocyte counts

## Output Structure

Reference ranges are returned in a structured format:

```json
{
  "success": true,
  "test_code": "CBCREF",
  "test_name": "CBC Reference Ranges",
  "url": "https://muhealth.testcatalog.org/show/CBCREF",
  "reference_ranges": {
    "Hemoglobin": {
      "analyte": "Hemoglobin",
      "ranges": [
        {"age_group": "Birth-7 days", "reference_range": "13.5-22.0 g/dL", "sex": "Male"},
        {"age_group": "Adults", "reference_range": "13.5-17.5 g/dL", "sex": "Male"},
        {"age_group": "Adults", "reference_range": "12.0-15.5 g/dL", "sex": "Female"}
      ]
    }
  }
}
```

## Notes

- The site uses bot protection; this skill uses browser automation with proper headers to access the content
- Reference ranges are age-specific and often sex-specific
- Units are preserved as provided in the original source (g/dL, fL, pg, ×10^12/L, etc.)
- Some tests may show "not established" for certain age groups

## Technical Details

- Uses Playwright for browser automation to handle JavaScript-rendered content
- Implements robust parsing for complex table structures
- Handles both single-column and multi-column reference range layouts
- Preserves scientific notation and special characters in values
