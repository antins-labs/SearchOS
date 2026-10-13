# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Hiroshima National Peace Memorial Hall Access Skill

This skill provides structured access to information from the Hiroshima National Peace Memorial Hall for the Atomic Bomb Victims English website.

## About the Facility

The Hiroshima National Peace Memorial Hall for the Atomic Bomb Victims is a national facility built to:
- Keep records of atomic bomb victims
- Pray for lasting world peace
- Deepen international understanding of the atomic bombing horrors
- Pass down survivor memoirs to future generations

**Location**: Peace Memorial Park, Hiroshima (south of the Atomic Bomb Dome)
**Opened**: August 1, 2002
**Architect**: Kenzō Tange
**Admission**: Free

## Available Functions

### get_homepage
Returns homepage information including:
- Today's opening hours
- Current notices and announcements
- Main features and programs
- Calls to action for survivors, bereaved families, and educators

### get_visitor_info
Returns comprehensive visiting information:
- Seasonal opening hours (March-July, August, September-November, December-February)
- Closed dates (December 30-31)
- Admission details (Free)
- Transportation directions from:
  - JR Hiroshima Station (bus and streetcar options)
  - Hiroshima Port
  - Hiroshima Airport
- Parking information
- On-site facilities (wheelchair rental, lockers, resting room)

### get_floor_guide
Returns detailed floor-by-floor facility information:

**Ground Floor**:
- Inscription and philosophy
- 8:15 am Monument with fountain

**Upper Level**:
- Slope to Hall of Remembrance
- Special Exhibition Area (30-minute film presentations)
- Library (140,000+ memoirs, testimonies, photos, videos)
- Stratum Cross-Section display

**Lower Level**:
- Hall of Remembrance (360° panoramic photo, 140,000 tiles representing victims)
- Victims' Information Area (name and portrait search)

### get_about_info
Returns institutional information:
- Founding philosophy and inscription
- Basic information (founder, management, building details, architect)
- Historical timeline from 1985 to 2003

### get_faq
Returns frequently asked questions organized by category:
- About the facility
- Facilities and services
- Accessibility
- Victim registration
- Atomic bomb memoirs

### get_notices
Returns list of announcements and notices with dates, including visitor milestones and event information.

### get_projects
Returns list of main projects and initiatives:
- Registering Victims of the Atomic Bomb
- Atomic Bomb Memoirs
- Special Exhibitions
- Atomic Bomb Memoir Readings
- Survivor Testimony Videos
- Translation services
- Short Film Introduction

## Data Source

All information is fetched from the English section of the official website:
- https://www.hiro-tsuitokinenkan.go.jp/en/

The site is also available in Japanese, Chinese, and Korean.

## Usage Notes

- Opening hours vary by season (5:00 PM closing in winter, 7:00 PM in August)
- August 5-6 have extended hours (close at 8:00 PM)
- Free admission to all facilities
- Materials available in multiple languages (English, Chinese, Korean, Japanese, plus 20+ languages for selected content)
- Google Street View available for virtual tours
