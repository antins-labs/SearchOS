# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Cannabis Regulations AI - Country Legality Extractor

## Overview

This skill extracts structured cannabis legality information from country profile pages on [www.cannabisregulations.ai](https://www.cannabisregulations.ai). The site provides standardized, template-based country profiles with detailed legal information about cannabis/marijuana laws worldwide.

## Why This Skill

The generic web reader often fails to properly extract the structured legal data from this site due to:
- Dynamic content loading that requires JavaScript rendering
- Template-based structure that needs specialized parsing
- Zero evidence returned on multiple page opens with standard readers

This dedicated extractor uses Playwright to render the pages and parse the standardized template fields.

## Available Functions

### get_country_legality

Fetches comprehensive cannabis legality information for a specific country.

**Parameters:**
- `country` (string, optional): Country name (e.g., "Ecuador", "Kazakhstan", "Antigua and Barbuda")
- `url` (string, optional): Full URL to the country page (will be constructed from country name if not provided)

**Returns:**
```json
{
  "country": "Ecuador",
  "title": "Is Weed Legal in Ecuador? 2026 Cannabis Laws Explained",
  "summary": "Ecuador decriminalized personal cannabis use, but the 10-gram table was repealed in 2023...",
  "legal_status": "Decriminalized",
  "overview": "Recreational marijuana in Ecuador is decriminalized in principle but enforcement has tightened...",
  "key_facts": {
    "Legal Status of:": "Decriminalized",
    "Governing Body": "Agency for Regulation, Control and Sanitary Surveillance (ARCSA); National Police...",
    "Potency/ Product Limits": "Personal-use thresholds removed November 2023",
    "Regulating Entity": "Organic Comprehensive Criminal Code (COIP) Articles 220, 364...",
    "Import Export Rules for the Country": "Recreational cannabis import and export are prohibited..."
  },
  "url": "https://www.cannabisregulations.ai/country-legality/ecuador-marijuana",
  "success": true
}
```

### extract_legal_status

A lighter-weight function that returns just the legal status and summary for a country.

**Parameters:**
- `country` (string, optional): Country name
- `url` (string, optional): Full URL to the country page

**Returns:**
```json
{
  "country": "Kazakhstan",
  "legal_status": "Illegal",
  "summary": "Marijuana is illegal in Kazakhstan. Under 5g is an administrative offense...",
  "url": "https://www.cannabisregulations.ai/country-legality/kazakhstan-marijuana",
  "success": true
}
```

## Data Extracted

Each country profile includes:

1. **Legal Status**: Illegal / Decriminalized / Legal / Medical Use Only
2. **Summary**: One-sentence overview of the cannabis law
3. **Overview**: Detailed explanation of recreational and medical cannabis laws
4. **Key Facts**:
   - Governing Body: Regulatory agencies responsible for enforcement
   - Potency/Product Limits: THC limits, possession thresholds, etc.
   - Regulating Entity: Specific laws and codes governing cannabis
   - Import/Export Rules: Cross-border movement regulations

## Example Usage

**Query:** "What is the cannabis legal status in Ecuador?"

```json
{
  "function": "get_country_legality",
  "country": "Ecuador"
}
```

**Query:** "Is marijuana legal in Kazakhstan?"

```json
{
  "function": "extract_legal_status",
  "country": "Kazakhstan"
}
```

**Query:** "Get cannabis laws for Antigua and Barbuda"

```json
{
  "function": "get_country_legality",
  "country": "Antigua and Barbuda"
}
```

## Supported Countries

The site covers countries worldwide. URL pattern:
```
https://www.cannabisregulations.ai/country-legality/{country-slug}-marijuana
```

Where `{country-slug}` is the lowercase country name with spaces replaced by hyphens (e.g., "antigua-and-barbuda").

## Notes

- Pages include a disclaimer that the information is for informational purposes only and does not constitute legal advice
- The site appears to be updated regularly (dates show 2026 in examples)
- Content includes specific penalties, thresholds, and enforcement agency details
- Some pages may be slower to load; the extractor includes retry logic for reliability
