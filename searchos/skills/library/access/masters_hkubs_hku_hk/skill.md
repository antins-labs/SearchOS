# HKU Business School Masters Programmes Access Skill

## Overview

This skill extracts structured data from HKU Business School's masters programmes website, providing comprehensive information on tuition fees, admissions schedules, and scholarships.

## Functions

### 1. get_tuition_fees

Retrieves complete tuition fee information for all 12 masters programmes offered by HKU Business School.

**Returns:**
- Full tuition fee table with programme names, fees, and deposits
- Structured content including payment terms and notes
- Metadata and page title

**Example Response:**
```json
{
  "success": true,
  "title": "Tuition Fee",
  "tuition_table": {
    "programmes": [
      {
        "programme": "Master of Accounting",
        "tuition_fee": "HK$ 426,000",
        "deposit": "HK$ 142,000"
      },
      {
        "programme": "Master of Finance",
        "tuition_fee": "HK$ 462,000",
        "deposit": "HK$ 154,000"
      }
    ],
    "metadata": {
      "headers": ["Programmes", "Tuition Fee*", "Deposit"]
    }
  }
}
```

### 2. get_admissions_schedule

Retrieves admissions requirements, schedule, and course exemption policies.

**Returns:**
- Admissions schedule and deadlines
- Eligibility requirements
- Course exemption and advanced standing policies by programme
- GMAT/GRE requirements
- English language test requirements

**Key Information Extracted:**
- Application rounds and deadlines
- Admission requirements for different programmes
- GMAT/GRE/IELTS/TOEFL requirements
- Course exemption policies for each programme
- Advanced standing options

### 3. get_scholarships

Retrieves comprehensive scholarship and financial aid information.

**Returns:**
- Dean's Master Fellowship details
- Entrance Scholarship information
- Merit-based Scholarship details
- Government schemes (Hong Kong Future Talents Scholarship)
- Financial aid options (Prodigy Finance, CEF, ENLS)

**Scholarships Covered:**
- HKU Business School Dean's Master Fellowship (HK$250,000 to full tuition)
- Entrance Scholarship (5% to 50% of tuition)
- Merit-based Scholarship (10%)
- Fargo Wealth Excellence Scholarship
- Hong Kong Future Talents Scholarship Scheme
- Continuing Education Fund (CEF)
- Extended Non-means-tested Loan Scheme (ENLS)

### 4. get_all_programmes

Returns a simplified list of all programmes with tuition fees.

**Returns:**
- List of all 12 masters programmes
- Tuition fees and deposits for each programme
- Total count of programmes

**Programme List:**
1. Master of Accounting
2. Master of Accounting Analytics
3. Master of Artificial Intelligence in Business
4. Master of Economics
5. Master of Family Wealth Management
6. Master of Finance
7. Master of Finance in Financial Technology
8. Master of Global Management
9. Master of Science in Business Analytics
10. Master of Science in Marketing
11. Master of Sustainable Accounting and Finance
12. Master of Wealth Management

### 5. search_programme_fees

Search for a specific programme's tuition fee using keyword matching.

**Parameters:**
- `programme_name` (string, required): Programme name or keyword to search for

**Example Request:**
```json
{
  "function": "search_programme_fees",
  "programme_name": "finance"
}
```

**Example Response:**
```json
{
  "success": true,
  "query": "finance",
  "matches": [
    {
      "programme": "Master of Finance",
      "tuition_fee": "HK$ 462,000",
      "deposit": "HK$ 154,000"
    },
    {
      "programme": "Master of Finance in Financial Technology",
      "tuition_fee": "HK$ 462,000",
      "deposit": "HK$ 154,000"
    }
  ],
  "count": 2
}
```

## Data Source

All data is extracted from:
- Primary URL: https://masters.hkubs.hku.hk/articles/
- Pages accessed:
  - `/articles/tuitionfee` - Tuition fee information
  - `/articles/admissionsschedule` - Admissions schedule and requirements
  - `/articles/scholarships` - Scholarships and financial aid

## Extraction Method

The skill uses:
- **aiohttp** for asynchronous HTTP requests
- **BeautifulSoup4** for HTML parsing
- Direct HTML extraction without browser automation
- Structured data parsing from clean HTML tables and content

## Notes

- All tuition fees are listed in Hong Kong Dollars (HK$)
- Fees are subject to university approval
- Programme-specific course exemptions may apply
- Application fee: HK$600 (non-refundable)
- Admission decisions typically available 1 month after deadline
- One intake per year (August/September)

## Rate Limits

- 2 requests per second
- 30 requests per minute

## Error Handling

All functions return:
- `success`: boolean indicating operation status
- `error`: error message if unsuccessful
- `details`: additional error information when available

## Use Cases

1. **Research**: Compare tuition fees across programmes
2. **Planning**: Understand application deadlines and requirements
3. **Financial Planning**: Calculate total costs including deposits
4. **Scholarship Search**: Identify funding opportunities
5. **Programme Comparison**: Search and compare programmes by fee ranges