# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# European Elections Voting Guide Access Skill

This skill retrieves structured voting information from the official European Parliament elections website (elections.europa.eu) for EU member countries.

## Overview

The elections.europa.eu website provides comprehensive voting guides for each EU member state, including:
- Election dates and polling hours
- Number of MEPs to be elected
- Voting system details
- Candidate and party information
- Voter eligibility requirements
- Registration procedures and deadlines
- Polling station information
- Required documents
- Accessibility support
- Alternative voting methods (mail, proxy, online)

The site uses an expand/collapse accordion pattern that requires JavaScript rendering to extract content properly. This skill uses Playwright to render the pages and extract the structured Q&A data.

## Functions

### get_country_voting_info

Retrieves complete voting information for a specific EU country.

**Parameters:**
- `country_code` (required): Two-letter ISO country code (e.g., 'fr', 'de', 'it', 'gr')
- `language` (optional): Language code, defaults to 'en'
- `sections` (optional): Filter to specific topics by keyword

**Returns:**
- `title`: Page title (e.g., "How to vote in France")
- `intro`: Introduction paragraph with key dates
- `lastReviewed`: Date when information was last updated
- `sections`: Array of Q&A pairs with `question` and `answer` fields
- `country_code`: The country code queried
- `source_url`: The full URL of the source page

**Example:**
```json
{
  "function": "get_country_voting_info",
  "country_code": "fr"
}
```

### list_available_countries

Returns a dictionary of all available EU country codes and their names.

**Example:**
```json
{
  "function": "list_available_countries"
}
```

## Available Country Codes

| Code | Country | Code | Country |
|------|---------|------|---------|
| at | Austria | lv | Latvia |
| be | Belgium | lt | Lithuania |
| bg | Bulgaria | lu | Luxembourg |
| hr | Croatia | mt | Malta |
| cy | Cyprus | nl | Netherlands |
| cz | Czech Republic | pl | Poland |
| dk | Denmark | pt | Portugal |
| ee | Estonia | ro | Romania |
| fi | Finland | sk | Slovakia |
| fr | France | si | Slovenia |
| de | Germany | es | Spain |
| gr | Greece | se | Sweden |
| hu | Hungary | ie | Ireland |
| it | Italy | | |

## Typical Sections Returned

Each country's voting guide includes approximately 18 standard Q&A sections:

1. What is the date of the elections?
2. How many Members are elected?
3. How are the Members elected?
4. Who are the candidates?
5. Which political parties can I vote for?
6. What is the threshold for political parties to be elected?
7. How many and which constituencies exist?
8. Is there a legal obligation to vote?
9. Who is eligible to vote?
10. Where can I vote?
11. Where should I register to vote?
12. What is the deadline for registering to vote?
13. What documents do I need to bring to the polling station?
14. What support can I have as a voter with a disability?
15. Where can I find easy-to-read information?
16. Can I vote by mail/post?
17. Can I vote online?
18. Can I vote by proxy?

## Usage Notes

- The site content is in multiple EU languages; use the `language` parameter to request a specific language version
- Information is updated periodically; check the `lastReviewed` date for currency
- Some country-specific variations exist in the questions (e.g., "Can I vote by mail?" vs "Can I vote by post?")
- Use the `sections` filter to retrieve only relevant information if you don't need the full guide

## Technical Details

The skill uses Playwright browser automation because:
1. The site uses JavaScript to render expand/collapse sections
2. The Q&A content is hidden until DOM interaction occurs
3. The accordion structure (li.expand-container > h2 + div.expand-container-content) requires DOM traversal

The extraction process:
1. Navigates to the country-specific URL
2. Waits for DOM content to load
3. Evaluates JavaScript to extract structured data from the accordion
4. Cleans up UI artifacts (share button text) from the content
5. Returns structured Q&A data with metadata
