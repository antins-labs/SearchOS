# U.S. Senate States Access Skill

This skill fetches information about U.S. Senators from the official senate.gov website, specifically from the state profile pages at `https://www.senate.gov/states/{STATE}/intro.htm`.

## Features

### Get Senators by State
Retrieve detailed information about current U.S. Senators for any state, including:
- Senator name and party affiliation
- Official website URL
- Photo URL
- Hometown
- Contact page URL
- Senate office building address
- Washington, DC mailing address
- Phone number
- Committee assignments link
- Biographical Directory link and ID

### List All States
Get a complete list of all U.S. states and territories with their two-letter codes and profile URLs.

### Get State History
Retrieve historical information about a state's Senate representation, including:
- When the state joined the Union
- First senators
- Longest-serving senators
- Notable leadership positions

## Usage Examples

### Get Senators for Oklahoma
```json
{
  "function": "get_senators_by_state",
  "state_code": "OK"
}
```

### Get Senators for Ohio
```json
{
  "function": "get_senators_by_state",
  "state_code": "OH"
}
```

### List All Available States
```json
{
  "function": "list_all_states"
}
```

### Get State History
```json
{
  "function": "get_state_history",
  "state_code": "WV"
}
```

## Response Format

### Senators Response
```json
{
  "success": true,
  "state_code": "OK",
  "state_name": "Oklahoma",
  "senators": [
    {
      "state_code": "OK",
      "name": "James Lankford",
      "party": "R",
      "website": "https://www.lankford.senate.gov",
      "photo_url": "https://bioguide.congress.gov/bioguide/photo/L/L000575.jpg",
      "hometown": "Oklahoma City",
      "contact_url": "https://www.lankford.senate.gov/contact/email",
      "committee_assignments_url": "https://www.senate.gov/general/committee_assignments/assignments.htm#LankfordOK",
      "bioguide_url": "https://bioguide.congress.gov/search/bio/L000575",
      "bioguide_id": "L000575",
      "office_address": "731 Hart Senate Office Building",
      "mailing_address": "731 Hart Senate Office Building\nWashington DC 20510",
      "phone": "(202) 224-5754"
    }
  ],
  "senator_count": 2,
  "state_history": "Oklahoma became the 46th state in the Union on November 16, 1907..."
}
```

### States List Response
```json
{
  "success": true,
  "states": [
    {"code": "AL", "name": "Alabama", "profile_url": "https://www.senate.gov/states/AL/intro.htm"},
    {"code": "AK", "name": "Alaska", "profile_url": "https://www.senate.gov/states/AK/intro.htm"},
    ...
  ],
  "total_count": 50
}
```

## State Codes

All 50 U.S. states plus territories are supported:
- 50 states: AL, AK, AZ, AR, CA, CO, CT, DE, FL, GA, HI, ID, IL, IN, IA, KS, KY, LA, ME, MD, MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ, NM, NY, NC, ND, OH, OK, OR, PA, RI, SC, SD, TN, TX, UT, VT, VA, WA, WV, WI, WY

## Data Sources

- **Website**: https://www.senate.gov
- **State Profiles**: https://www.senate.gov/states/{STATE}/intro.htm
- **Biographical Directory**: https://bioguide.congress.gov

## Notes

- This skill uses direct HTTP requests with HTML parsing (BeautifulSoup) for efficient data extraction
- No browser automation is required
- All senator information is sourced from official U.S. Senate websites
- The Bioguide ID can be used to query the Congress.gov API for additional legislative data
- Photo URLs may be either from bioguide.congress.gov or senate.gov local storage

## Error Handling

The skill returns structured error responses:
- `invalid_state_code`: The provided state code is not valid
- `missing_state_code`: Required state_code parameter was not provided
- `not_found`: The state page was not found (404 error)
- `http_error`: HTTP error occurred during request
- `no_senators_found`: Page loaded but no senator data was found