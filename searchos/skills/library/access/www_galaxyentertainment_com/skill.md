# Galaxy Entertainment Group Investor Relations Skill

Fetches financial reports and investor announcements from Galaxy Entertainment
Group's official investor relations website at www.galaxyentertainment.com.

## Available Functions

### financial_reports

Retrieves annual and interim financial reports dating back to 2005.

**Parameters:**
- `report_type` (optional): Filter by report type
  - `Annual Report` - Annual financial reports
  - `Interim Report` - Half-year interim reports
  - `Sustainability Report` - ESG and sustainability reports
- `year` (optional): Filter by specific report year (e.g., 2024)
- `limit` (optional): Maximum number of results to return

**Example Response:**
```json
{
  "reports": [
    {
      "date": "2026-04-09",
      "title": "Annual Report 2025",
      "type": "Annual Report",
      "year": 2025,
      "url": "https://www.galaxyentertainment.com/uploads/investor/...",
      "filename": "933511f1374a0e17d56a9ff97670ec6a25c84314.pdf"
    }
  ],
  "total": 41,
  "filtered_count": 1
}
```

### financial_results

Retrieves recent investor announcements, including monthly returns, quarterly
financial data, meeting results, and regulatory disclosures.

**Parameters:**
- `doc_type` (optional): Filter by document type
  - `Monthly Return` - Monthly equity issuer returns
  - `Financial Data` - Quarterly selected unaudited financial data
  - `Meeting Results` - AGM/EGM poll results
  - `Directors` - Director appointments and changes
  - `Disclosure` - Next day disclosure returns
- `limit` (optional): Maximum number of results to return

**Example Response:**
```json
{
  "announcements": [
    {
      "date": "2026-06-04",
      "title": "Monthly Return of Equity Issuer on Movements in Securities...",
      "type": "Monthly Return",
      "url": "https://www.galaxyentertainment.com/uploads/investor/...",
      "filename": "38b01261f24047e5d181691c05b76bb55912472f.pdf"
    }
  ],
  "total": 5,
  "filtered_count": 1
}
```

## Source Data

Data is scraped from:
- Financial Reports: `/en/investor/financial-reports`
- Financial Results: `/en/investor/financial-results`

The site provides static HTML pages with direct PDF download links, no
JavaScript rendering required.

## Notes

- Financial reports archive spans 20+ years (2005 to present)
- Reports include both English and may include Traditional Chinese versions
- PDF URLs use content-hashed filenames for integrity
- Date parsing handles multiple formats from the site's historical data