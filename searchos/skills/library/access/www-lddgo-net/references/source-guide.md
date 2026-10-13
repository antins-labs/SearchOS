# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# LDDGO Country Detail Extractor

This skill extracts structured country information from www.lddgo.net country detail pages.

## Features

Fetches comprehensive country data including:
- Common and official names
- Capital city
- Currency (code, symbol, name)
- ISO 3166-1 codes (alpha-2, alpha-3, numeric)
- International Olympic Committee code
- Top-level domain (TLD)
- Location (continent and region)
- Language(s)
- Geographic coordinates (latitude, longitude)
- Area (in km²)
- Calling/phone code
- UN membership status
- Independent status
- Landlocked status
- Assignment status
- Country flag URL

## Functions

### get_country

Fetch country details by ISO 3166-1 alpha-3 code.

**Parameters:**
- `cca3` (required): 3-letter country code (e.g., 'FRA', 'USA', 'JPN')
- `country_name` (optional): Country name to improve URL matching

**Example:**
```json
{
  "function": "get_country",
  "cca3": "FRA"
}
```

### get_country_by_name

Fetch country details by name (requires cca3 code as well).

**Parameters:**
- `country_name` (required): Country name in English
- `cca3` (required): ISO 3166-1 alpha-3 code

**Example:**
```json
{
  "function": "get_country_by_name",
  "country_name": "France",
  "cca3": "FRA"
}
```

## Output Format

Returns a JSON object with the following structure:

```json
{
  "success": true,
  "url": "https://www.lddgo.net/en/common/country-detail?c=...",
  "cca3": "FRA",
  "common_name": "France",
  "official_name": "French Republic",
  "flag_url": "https://www.lddgo.net/js/third/tool/country/data/fra.svg",
  "capital": "Paris",
  "tld": ".fr",
  "independent_status": "true",
  "assignment_status": "officially-assigned",
  "un_member": "true",
  "currency": "EUR - € (Euro)",
  "location": "Europe - Western Europe",
  "language": "French",
  "latitude_longitude": "46,2",
  "area": "551695 km²",
  "calling_code": "+33",
  "landlocked": "false",
  "iso_3166_1_alpha_2_code": "FR",
  "iso_3166_1_alpha_3_code": "FRA",
  "iso_3166_1_numeric_code": "250",
  "international_olympic_committee_code": "FRA"
}
```

## Notes

- The website uses JavaScript to populate country data, so browser automation is required.
- The URL parameter `c` is the hex-encoded country name (UTF-8 bytes as hex string).
- The URL parameter `cca3` is the ISO 3166-1 alpha-3 country code.
- All data is returned as strings; boolean values like "true"/"false" may need conversion.
- Country flag URLs are relative paths that are converted to absolute URLs in the output.

## Supported Countries

This skill works with any country available on lddgo.net, including all UN member states
and many territories. Common cca3 codes include:

- USA (United States)
- CHN (China)
- IND (India)
- DEU (Germany)
- FRA (France)
- GBR (United Kingdom)
- JPN (Japan)
- BRA (Brazil)
- RUS (Russia)
- And many more...
