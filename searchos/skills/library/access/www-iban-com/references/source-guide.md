# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IBAN.com Access Skill

This skill provides programmatic access to IBAN.com's country code and IBAN structure data.

## Features

### 1. Get Country Codes (`get_country_codes`)

Retrieves the complete ISO 3166-1 country codes table with:
- Country name
- Alpha-2 code (e.g., US, GB, DE)
- Alpha-3 code (e.g., USA, GBR, DEU)
- Numeric code (e.g., 840, 826, 276)

Returns 249 countries/territories.

**Example:**
```python
# Get all country codes
execute({'function': 'get_country_codes'})

# Filter by alpha-2 code
execute({'function': 'get_country_codes', 'country_code': 'US'})

# Filter by alpha-3 code
execute({'function': 'get_country_codes', 'country_code': 'GBR'})

# Filter by country name (partial match)
execute({'function': 'get_country_codes', 'country_name': 'United'})
```

### 2. Get IBAN Structure (`get_iban_structure`)

Retrieves IBAN structure specifications for all supported countries, including:
- Country name and code
- SEPA membership status
- IBAN length
- Account check algorithm
- Branch code information
- IBAN format example

Data is organized into:
- SEPA countries (European payment area)
- Non-SEPA countries

**Example:**
```python
# Get all IBAN structures
execute({'function': 'get_iban_structure'})

# Filter by country code
execute({'function': 'get_iban_structure', 'country_code': 'DE'})

# Filter by country name
execute({'function': 'get_iban_structure', 'country_name': 'France'})
```

### 3. Validate IBAN (`validate_iban`)

Validates an IBAN number and returns:
- Cleaned IBAN (uppercase, no spaces)
- Country code extraction
- Check digits extraction
- Validation status (when available)

**Important:** The free IBAN validation service has daily rate limits per IP address. When the limit is exceeded, the function returns an error indicating this.

**Example:**
```python
# Validate an IBAN
execute({'function': 'validate_iban', 'iban': 'GB82WEST12345698765432'})

# IBAN with spaces (will be cleaned automatically)
execute({'function': 'validate_iban', 'iban': 'DE89 3704 0044 0532 0130 00'})
```

## Response Format

All responses include:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (if any)
- Data specific to the function called

### Country Codes Response
```json
{
  "success": true,
  "count": 249,
  "countries": [
    {"country": "Afghanistan", "alpha_2": "AF", "alpha_3": "AFG", "numeric": "004"},
    ...
  ],
  "source_url": "https://www.iban.com/country-codes"
}
```

### IBAN Structure Response
```json
{
  "success": true,
  "sepa_countries_count": 89,
  "non_sepa_countries_count": 22,
  "sepa_countries": [
    {
      "country": "Albania",
      "code": "AL",
      "sepa": "Yes",
      "length": "28",
      "account_check": "",
      "branch": "",
      "iban_example": "AL35202111090000000001234567"
    },
    ...
  ],
  "non_sepa_countries": [...],
  "source_url": "https://www.iban.com/structure"
}
```

### IBAN Validation Response
```json
{
  "success": true,
  "iban": "GB82WEST12345698765432",
  "country_code": "GB",
  "check_digits": "82",
  "is_valid": true
}
```

Or when rate limited:
```json
{
  "success": false,
  "error": "rate_limit_exceeded",
  "message": "Daily rate limit exceeded for free IBAN validation service",
  "iban": "GB82WEST12345698765432"
}
```

## Limitations

- **IBAN Validation Rate Limits**: The free tier has limited daily validations per IP
- **No Real-time Bank Data**: This skill does not access paid APIs for bank details or BIC codes
- **Static Data**: Country codes and IBAN structures are fetched from public pages

## Data Sources

- Country Codes: https://www.iban.com/country-codes
- IBAN Structure: https://www.iban.com/structure
- IBAN Checker: https://www.iban.com/iban-checker
