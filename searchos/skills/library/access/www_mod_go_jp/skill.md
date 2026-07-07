# Japan Ministry of Defense (MOD) - Minister Information Access Skill

This skill fetches information about Japan's defense ministers, vice-ministers, and parliamentary vice-ministers from the official Ministry of Defense website (www.mod.go.jp).

## Overview

The Japan Ministry of Defense maintains structured pages with information about current and previous officials. This skill provides access to:

- **Current officials** (Japanese page): Current Minister of Defense, Vice-Minister, and Parliamentary Vice-Ministers
- **Previous officials** (Japanese page): Historical list of all previous ministers and officials
- **Previous officials** (English page): Historical list with English names and dates

## Available Functions

### 1. get_current_ministers_ja

Retrieves information about current officials from the Japanese page.

**Parameters**: None (other than function name)

**Returns**:
```json
{
  "success": true,
  "data": {
    "language": "ja",
    "url": "https://www.mod.go.jp/j/profile/minister/index.html",
    "retrieved_at": "ISO timestamp",
    "current_minister": {
      "name": "小泉　進次郎",
      "reading": "こいずみ　しんじろう",
      "position": "防衛大臣 (Minister of Defense)",
      "term": "2025（令和7）年10月21日～",
      "profile_url": "https://www.kantei.go.jp/jp/104/meibo/daijin/..."
    },
    "current_vice_minister": {...},
    "current_parliamentary_vice_ministers": [...]
  }
}
```

### 2. get_previous_ministers_ja

Retrieves historical list of previous officials from the Japanese page.

**Parameters**: None (other than function name)

**Returns**:
```json
{
  "success": true,
  "data": {
    "language": "ja",
    "url": "https://www.mod.go.jp/j/profile/minister/index.html",
    "retrieved_at": "ISO timestamp",
    "previous_ministers": [
      {
        "name": "中谷　元",
        "reading": "なかたに　げん",
        "term_start": "令和6年10月1日",
        "term_end": "令和7年10月21日",
        "activity_url": "https://..."
      },
      ...
    ],
    "previous_vice_ministers": [...],
    "previous_parliamentary_vice_ministers": [...],
    "previous_assistant_ministers": [...]
  }
}
```

### 3. get_previous_ministers_en

Retrieves historical list of previous officials from the English page.

**Parameters**: None (other than function name)

**Returns**:
```json
{
  "success": true,
  "data": {
    "language": "en",
    "url": "https://www.mod.go.jp/en/about/previous_ministers.html",
    "retrieved_at": "ISO timestamp",
    "ministers_of_defense": [
      {
        "name": "NAKATANI Gen",
        "title": "Mr.",
        "term_start": "October 2024",
        "term_end": "October 2025"
      },
      ...
    ],
    "state_ministers": [...],
    "parliamentary_vice_ministers": [...]
  }
}
```

### 4. get_profile

Retrieves detailed biographical information for a specific official from their profile page.

**Parameters**:
- `url` (required): The profile URL (obtained from profile_url field in minister data)

**Returns**:
```json
{
  "success": true,
  "data": {
    "url": "https://www.kantei.go.jp/jp/104/meibo/daijin/...",
    "retrieved_at": "ISO timestamp",
    "name": "小泉　進次郎",
    "reading": "こいずみ　しんじろう",
    "position": "防衛大臣",
    "birth_date": "昭和５６年４月１４日",
    "birth_place": "神奈川県",
    "biography": [
      "平成１６年　３月 関東学院大学経済学部卒業",
      "平成１８年　５月 米国コロンビア大学大学院政治学部修了",
      ...
    ]
  }
}
```

## Data Sources

- **Japanese current ministers**: `https://www.mod.go.jp/j/profile/minister/index.html`
- **English previous ministers**: `https://www.mod.go.jp/en/about/previous_ministers.html`
- **Individual profiles**: Links to `kantei.go.jp` (Prime Minister's official website)

## Notes

1. The Japanese page provides more detailed information including name readings in hiragana
2. Profile pages are hosted on the Prime Minister's website (kantei.go.jp), not the MOD site
3. All dates are kept in their original format (Japanese era calendar for Japanese, Gregorian for English)
4. Activity URLs link to archived pages showing the minister's official activities during their term

## Error Handling

All functions return a consistent structure:
```json
{
  "success": true/false,
  "data": {...},  // only when success is true
  "error": "..."  // only when success is false
}
```

Common errors:
- Missing required parameters
- Network timeout (30 seconds)
- Invalid profile URL
- Page structure changes on MOD website