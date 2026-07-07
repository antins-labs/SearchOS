# Haodf.com Hospital Profile Extractor

This skill extracts structured hospital information from Haodf Online (好大夫在线), one of China's leading healthcare platforms.

## Overview

Haodf.com hosts comprehensive hospital profiles with detailed information including:
- Basic hospital information (name, grade, address, phone)
- Provincial and national rankings
- Visit statistics and patient service metrics
- Department listings with doctor counts
- Multiple campus locations with coordinates
- Hospital introductions and descriptions

## Available Functions

### get_hospital_basic_info

Retrieves comprehensive hospital basic information including:
- Hospital name and aliases
- Hospital grade (三甲, 三级, etc.)
- Character (公立/私立 - public/private)
- Contact information (phone numbers)
- Address and campus locations
- Hospital introduction
- Department statistics
- Health content count
- Disease specialties

**Example:**
```python
result = await execute({
    'function': 'get_hospital_basic_info',
    'hospital_id': 21
})
```

**Sample Output:**
```json
{
  "hospital_id": 21,
  "name": "北京大学人民医院",
  "common_name": "北京大学人民医院",
  "grade": "三甲",
  "character": "公立",
  "phone": "010-88326666(西直门院区总机),010-66583666(白塔寺院区总机)",
  "address": "西直门院区:北京市西城区西直门南大街11号;...",
  "campuses": [
    {
      "name": "西直门院区",
      "address": "北京市西城区西直门南大街11号",
      "longitude": "116.360841",
      "latitude": "39.94263"
    }
  ],
  "departments": {
    "total_departments": 66,
    "total_doctors": 1141
  }
}
```

### get_hospital_ranking

Retrieves hospital ranking and statistical data:
- Provincial ranking (e.g., 北京市第6名)
- National ranking (e.g., 全国第12名)
- Total visit count
- Number of patients served online
- Educational article count
- Live consultation count
- Annual "Good Doctor" awards

**Example:**
```python
result = await execute({
    'function': 'get_hospital_ranking',
    'hospital_id': 21
})
```

**Sample Output:**
```json
{
  "hospital_id": 21,
  "hospital_name": "北京大学人民医院",
  "provincial_rank": 6,
  "province": "北京市",
  "national_rank": 12,
  "statistics": {
    "total_visits": "478,488,202",
    "patients_served_online": "845,575",
    "educational_articles": "12,994",
    "live_consultations": "270"
  },
  "annual_good_doctors": 30
}
```

### get_hospital_departments

Retrieves complete department listing organized by category:
- Total department count
- Total doctor count
- Department categories (内科, 外科, etc.)
- Individual departments within each category
- Doctor count per department
- Ranking status per department

**Example:**
```python
result = await execute({
    'function': 'get_hospital_departments',
    'hospital_id': 21
})
```

### get_hospital_campuses

Retrieves all campus locations for the hospital:
- Campus name
- Full address
- Geographic coordinates (longitude, latitude)
- Status (active/inactive)

**Example:**
```python
result = await execute({
    'function': 'get_hospital_campuses',
    'hospital_id': 21
})
```

**Sample Output:**
```json
{
  "hospital_id": 21,
  "hospital_name": "北京大学人民医院",
  "campuses": [
    {
      "name": "白塔寺院区",
      "address": "北京市西城区阜内大街133号",
      "longitude": "116.372627",
      "latitude": "39.930699",
      "status": "active"
    },
    {
      "name": "西直门院区",
      "address": "北京市西城区西直门南大街11号",
      "longitude": "116.360841",
      "latitude": "39.94263",
      "status": "active"
    },
    {
      "name": "通州院区",
      "address": "北京市通州区漷马路与漷城西一路交汇处东北角",
      "longitude": "116.774387",
      "latitude": "39.780908",
      "status": "active"
    }
  ]
}
```

## How to Get Hospital IDs

Hospital IDs can be found in the hospital page URLs:
- https://www.haodf.com/hospital/21.html → hospital_id = 21
- https://www.haodf.com/hospital/261.html → hospital_id = 261

You can search for hospitals on haodf.com and extract the ID from the URL.

## Data Source

All data is extracted from the hospital profile pages on haodf.com by parsing the embedded `window.__INITIAL_STATE__` JSON data structure, which contains comprehensive structured information about each hospital.

## Notes

- All hospital data is publicly available on haodf.com
- Data is retrieved in real-time from the website
- Some hospitals may have limited data available depending on their profile completeness
- Field names in responses use descriptive English names while preserving Chinese content
- Rankings are based on "关注度" (attention/interest level) metrics from haodf.com