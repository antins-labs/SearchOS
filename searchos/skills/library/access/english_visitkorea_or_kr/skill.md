# Visit Korea Tourist Attraction Extractor

This skill fetches detailed tourist attraction information from the official Korean Tourism Organization website (english.visitkorea.or.kr).

## Features

- **Fetch by Content ID**: Retrieve attraction details using the `vconts_id` from visitkorea.or.kr URLs
- **Auto-detection of URL pattern**: Automatically tries both URL patterns when type is 'auto'
- **Comprehensive Data Extraction**: Returns structured infobox data including:

## Extracted Data Fields

| Field | Description |
|-------|-------------|
| `title` | Attraction name (English and Korean) |
| `description` | Full description text |
| `address` | Physical address in English and Korean |
| `operating_hours` | Opening hours and timing details |
| `holidays` | Closed days and holiday schedule |
| `admission_fees` | Ticket prices and fee information |
| `phone` | Contact phone number (Inquiries) |
| `website` | Official website URL |
| `parking` | Parking availability |
| `activities` | Available activities (if applicable) |
| `age_limit` | Age restrictions (if applicable) |
| `main_image` | Primary image URL |

## Usage

### Fetch Attraction Information

```
function: fetch_attraction
vconts_id: "78636"
url_type: "auto"  # optional: "contents", "locIntrdn", or "auto" (default)
```

## URL Patterns Supported

1. **contentsView**: `/svc/contents/contentsView.do?vcontsId={id}`
2. **rgnContentsView**: `/svc/whereToGo/locIntrdn/rgnContentsView.do?vcontsId={id}`

## Example Results

### National Museum of Korean Contemporary History (78636)

```json
{
  "title": "National Museum of Korean Contemporary History (대한민국역사박물관)",
  "address": "198 Sejong-daero, Jongno-gu, Seoul 서울특별시 종로구 세종대로 198 (세종로)",
  "operating_hours": "Regular hours 10:00-18:00 * Wednesdays and Saturdays 10:00-21:00",
  "holidays": "New Year's Day, the day of Seollal & Chuseok",
  "admission_fees": "Free",
  "phone": "+82-2-3703-9200",
  "website": "www.much.go.kr",
  "parking": "Available (10 spaces)"
}
```

### Museum Kimchikan (66201)

```json
{
  "title": "Museum Kimchikan (뮤지엄 김치간)",
  "address": "(4-6th floor, Maru Art Center), 35-4 Insadong-gil, Jongno-gu, Seoul",
  "operating_hours": "10:00-18:00 (Last admission 17:30)",
  "holidays": "Mondays, January 1, Seollal & Chuseok holidays, Day of Christmas",
  "admission_fees": "Adults 5,000 won / Teenagers 3,000 won / Children 2,000 won",
  "phone": "+82-2-2088-8531",
  "website": "www.kimchimuseum.com"
}
```

## Finding vconts_id

The `vconts_id` can be found in the URL of any attraction page on english.visitkorea.or.kr:

- URL: `https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=78636`
- vconts_id: `78636`

## Error Handling

- Returns `success: false` with error message if:
  - vconts_id is missing or invalid
  - Page does not exist or returns 404
  - Network error occurs

## Technical Notes

- Uses HTTP GET requests (no API key required)
- Parses HTML with BeautifulSoup
- Extracts data from the infobox sections on content pages
- Handles both English and Korean text in addresses and names