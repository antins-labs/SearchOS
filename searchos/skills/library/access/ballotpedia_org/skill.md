# Ballotpedia Access Skill

## Overview

This skill extracts structured political data from [Ballotpedia](https://ballotpedia.org), a nonpartisan online political encyclopedia covering American politics and elections.

## Site Structure

Ballotpedia uses MediaWiki and the following content patterns:

### Person Pages
- URL pattern: `/Person_Name`
- Contains `div.infobox.person` with widget-row based structure
- Key-value pairs use `.widget-key` and `.widget-value` classes
- Data includes: name, party, education, net worth, religious affiliation, prior offices

### Office/Cabinet Pages
- URL pattern: `/Office_Name` or `/President_Name_presidential_Cabinet`
- Sectioned layout with H2 headings
- Member lists in `<ul>` elements and `div.wrap` containers
- Contains position holders, confirmation dates, term information

### Election Pages
- Tables with class `table`, `wikitable`, or `table-responsive`
- Include columns for party, candidate, vote percentage, vote counts
- Often collapsible/expandable tables

## Technical Notes

### AWS WAF Protection
Ballotpedia uses AWS WAF with JavaScript challenges. Direct HTTP requests return a 202 status with challenge JavaScript. This skill uses Playwright browser automation to:
1. Load the page (returns challenge page)
2. Wait for WAF JavaScript to execute
3. Reload with valid session cookies
4. Extract content from the actual page

This requires ~8 seconds per page load.

### Content Patterns

**Person Infobox Structure:**
```html
<div class="infobox person">
  <div class="widget-row value-only Republican">Person Name</div>
  <div class="widget-row value-only black">
    <a href="/Party_Name">Party Name</a>
  </div>
  <div class="widget-row">
    <div class="widget-key">Label</div>
    <div class="widget-value">Value</div>
  </div>
  ...
</div>
```

**Election Table Structure:**
```html
<table class="table table-responsive table-hover mw-collapsible">
  <tr><th>Party</th><th>Candidate</th><th>Vote %</th><th>Votes</th></tr>
  <tr>
    <td>Republican</td>
    <td>John Smith Incumbent</td>
    <td>59.2%</td>
    <td>161,669</td>
  </tr>
</table>
```

## Functions

### `person`
Extracts biographical and political data from person pages:
- Name and party affiliation
- Education (high school, bachelor's, law degrees)
- Net worth and financial disclosures
- Religious affiliation
- Prior offices held
- Last election date

### `office`
Extracts officeholder listings from cabinet/office pages:
- Sectioned lists of position holders
- Names, links, and descriptions
- Confirmation/swearing-in information

### `election`
Extracts election results tables:
- Candidate names and parties
- Vote percentages and counts
- Winner determination

### `page`
Returns basic page metadata:
- Page title
- Table of contents sections
- Content length

## Usage Examples

```python
# Extract person data
result = await execute({
    'url': 'https://ballotpedia.org/Mick_Mulvaney',
    'function': 'person'
})
# Returns: {success: true, data: {name: 'Michael Mulvaney', party: 'Republican Party', ...}}

# Extract cabinet data
result = await execute({
    'url': 'https://ballotpedia.org/Donald_Trump_presidential_Cabinet,_2017-2021',
    'function': 'office'
})
# Returns: {success: true, sections: [{title: 'Cabinet members...', members: [...]}]}

# Auto-detect function
result = await execute({
    'url': 'https://ballotpedia.org/Alex_Azar'
})
# Function auto-detected as 'person' based on URL pattern
```

## Error Handling

The skill returns structured error responses:
- `validation`: Invalid URL or missing parameters
- `timeout`: AWS WAF challenge failed or page load timeout
- `scraping_error`: Failed to extract expected content

## Limitations

1. **Browser Dependency**: Must use Playwright; direct HTTP requests won't work due to WAF
2. **Rate Limiting**: ~8 seconds per page load; not suitable for bulk scraping
3. **Dynamic Content**: Some data loaded dynamically may not be captured
4. **Structure Changes**: Widget-row structure may change; not all person pages have identical fields

## Data Quality

Ballotpedia is maintained by Ballotpedia.org, a 501(c)(3) nonprofit. Data is:
- Often cited by major news organizations
- Regularly updated for elections and officeholders
- Includes official sources and citations

## See Also

- Ballotpedia API documentation (if available)
- Similar MediaWiki-based political encyclopedias