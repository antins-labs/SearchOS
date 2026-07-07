# Shanghai Ranking GRAS Access Skill

Extract university rankings from ShanghaiRanking's Global Ranking of Academic Subjects (GRAS).

## Overview

This skill provides access to ShanghaiRanking's authoritative academic subject rankings, covering 55 subjects across 5 major fields from 2017 to 2025. The rankings evaluate universities based on five objective indicators:

- **World-Class Faculty**: Faculty awards and recognition
- **World-Class Output**: Research output volume
- **High Quality Research**: Research quality metrics
- **Research Impact**: Citation and impact metrics
- **International Collaboration**: International research partnerships

## Available Functions

### list_subjects

List all available academic subjects with their codes and available years.

**Parameters:**
- `year` (integer, optional): Reference year for available versions (default: 2025)

**Example:**
```python
result = await execute({
    "function": "list_subjects",
    "year": 2024
})
```

**Returns:**
- List of subject categories (Natural Sciences, Engineering, Life Sciences, Medical Sciences, Social Sciences)
- Each subject's code, name, and available years
- Total subject count

### get_rankings

Get university rankings for a specific academic subject.

**Parameters:**
- `subject_code` (string, required): Subject code (e.g., "AS0101" for Mathematics)
- `year` (integer, optional): Ranking year (default: 2024, range: 2017-2025)
- `limit` (integer, optional): Maximum results (default: 100)
- `offset` (integer, optional): Pagination offset (default: 0)

**Example:**
```python
result = await execute({
    "function": "get_rankings",
    "subject_code": "AS0101",
    "year": 2024,
    "limit": 50
})
```

**Returns:**
- Subject information (code, name, category)
- List of universities with:
  - World rank
  - University name, code, logo URL
  - Country and country code
  - Total score
  - Individual indicator scores

### search_universities

Search for universities by name within rankings.

**Parameters:**
- `query` (string, required): University name search query
- `subject_code` (string, optional): Filter to specific subject
- `year` (integer, optional): Ranking year (default: 2024)
- `limit` (integer, optional): Maximum results (default: 50)

**Example:**
```python
# Search across all subjects
result = await execute({
    "function": "search_universities",
    "query": "Stanford",
    "year": 2024
})

# Search within a specific subject
result = await execute({
    "function": "search_universities",
    "query": "Oxford",
    "subject_code": "AS0210",  # Computer Science & Engineering
    "year": 2024
})
```

## Subject Codes Reference

### Natural Sciences
| Code | Subject |
|------|---------|
| AS0101 | Mathematics |
| AS0102 | Physics |
| AS0103 | Chemistry |
| AS0104 | Earth Sciences |
| AS0105 | Geography |
| AS0106 | Ecology |
| AS0107 | Oceanography |
| AS0108 | Atmospheric Science |

### Engineering
| Code | Subject |
|------|---------|
| AS0201 | Mechanical Engineering |
| AS0202 | Electrical & Electronic Engineering |
| AS0205 | Automation & Control |
| AS0206 | Telecommunication Engineering |
| AS0207 | Instruments Science & Technology |
| AS0208 | Biomedical Engineering |
| AS0210 | Computer Science & Engineering |
| AS0211 | Civil Engineering |
| AS0212 | Chemical Engineering |
| AS0213 | Materials Science & Engineering |
| AS0214 | Nanoscience & Nanotechnology |
| AS0215 | Energy Science & Engineering |
| AS0216 | Environmental Science & Engineering |
| AS0217 | Water Resources |
| AS0219 | Food Science & Technology |
| AS0220 | Biotechnology |
| AS0221 | Aerospace Engineering |
| AS0222 | Marine/Ocean Engineering |
| AS0223 | Transportation Science & Technology |
| AS0224 | Remote Sensing |
| AS0226 | Mining & Mineral Engineering |
| AS0227 | Metallurgical Engineering |
| AS0228 | Textile Science & Engineering |

### Life Sciences
| Code | Subject |
|------|---------|
| AS0301 | Biological Sciences |
| AS0302 | Human Biological Sciences |
| AS0303 | Agricultural Sciences |
| AS0304 | Veterinary Sciences |

### Medical Sciences
| Code | Subject |
|------|---------|
| AS0401 | Clinical Medicine |
| AS0402 | Public Health |
| AS0403 | Dentistry & Oral Sciences |
| AS0404 | Nursing |
| AS0405 | Medical Technology |
| AS0406 | Pharmacy & Pharmaceutical Sciences |

### Social Sciences
| Code | Subject |
|------|---------|
| AS0501 | Economics |
| AS0502 | Statistics |
| AS0503 | Law |
| AS0504 | Political Sciences |
| AS0505 | Sociology |
| AS0506 | Education |
| AS0507 | Communication |
| AS0508 | Psychology |
| AS0509 | Business Administration |
| AS0510 | Finance |
| AS0511 | Management |
| AS0512 | Public Administration |
| AS0513 | Hospitality & Tourism Management |
| AS0515 | Library & Information Science |

## Data Structure

### Ranking Entry
```json
{
  "rank": "1",
  "university": {
    "name": "Princeton University",
    "slug": "princeton-university",
    "code": "RI02848",
    "logo": "https://www.shanghairanking.com/logo/b1dad5288.png"
  },
  "country": "United States",
  "country_code": "us",
  "score": 388.8,
  "indicators": {
    "world_class_faculty": 80.9,
    "world_class_output": 194.6,
    "high_quality_research": 56.4,
    "research_impact": 43.0,
    "international_collaboration": 13.9
  }
}
```

## Notes

- The ranking data is fetched from ShanghaiRanking's Nuxt.js static payload files
- Rankings typically include 300-500 universities per subject
- Some subjects may not be available for all years (e.g., Oceanography available from 2018)
- Rank ranges (e.g., "401-500") are used for lower-ranked institutions
- Scores may be `null` for institutions in rank ranges

## Technical Details

- **Data Source**: ShanghaiRanking's GRAS website (www.shanghairanking.com)
- **Data Format**: JavaScript JSONP payloads parsed via Node.js
- **Caching**: Build hash is cached to minimize page fetches
- **Rate Limiting**: Consider implementing delays for bulk requests