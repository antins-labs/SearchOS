# DOJ USAO Career Center Job Listings

This skill provides access to attorney job vacancy listings from the U.S. Department of Justice (DOJ) USAO (U.S. Attorneys' Offices) Career Center at [justice.gov](https://www.justice.gov/usao/career-center/job-openings/attorneys).

## Overview

The DOJ Career Center maintains structured job vacancy tables for attorney positions across U.S. Attorneys' Offices nationwide. Each listing includes:
- Hiring organization (USAO district office)
- Job title
- State/location
- Posted/updated date
- Application deadline

Individual job detail pages contain comprehensive information including:
- Office description
- Job description and responsibilities
- Required and preferred qualifications
- Salary information
- Travel requirements
- Application process details

## Functions

### list_jobs

Lists current attorney job openings with optional filtering by state.

**Parameters:**
- `state` (optional): Two-letter state code to filter results (e.g., "VA", "CA", "NY")

**Returns:**
- Array of job listings with title, organization, state, dates, and detail URLs
- Total count of matching jobs

**Example:**
```json
{
  "function": "list_jobs",
  "state": "VA"
}
```

### get_job_detail

Retrieves complete details for a specific job posting.

**Parameters:**
- `job_url` (required): URL or path to the job posting
  - Full URL: `https://www.justice.gov/legal-careers/job/assistant-united-states-attorney-civil-77`
  - Relative path: `/legal-careers/job/assistant-united-states-attorney-civil-77`
  - Job ID: `assistant-united-states-attorney-civil-77`

**Returns:**
- Complete job details including organization, location, qualifications, salary, and application instructions

**Example:**
```json
{
  "function": "get_job_detail",
  "job_url": "/legal-careers/job/assistant-united-states-attorney-civil-77"
}
```

## Data Source

All data is fetched directly from the official DOJ USAO Career Center website. The listings are maintained by the U.S. Department of Justice and represent current attorney vacancies across federal judicial districts.

## Use Cases

- Job seekers looking for AUSA (Assistant U.S. Attorney) positions
- Career counseling and job placement services
- Legal employment market research
- Tracking federal attorney job openings by location
- Gathering detailed job requirements and qualifications for specific positions

## Notes

- Job listings are updated regularly; deadlines should be verified on the official site
- The DOJ may have multiple listings for the same position across different dates
- Some listings may have specific citizenship, security clearance, or bar membership requirements
- Application procedures may vary by district office
- The state filter uses two-letter state codes (e.g., "WI" for Wisconsin, "GA" for Georgia)