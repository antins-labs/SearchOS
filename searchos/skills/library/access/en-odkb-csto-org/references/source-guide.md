# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CSTO (Collective Security Treaty Organization) Access Skill

This skill retrieves structured information from the official CSTO website at [en.odkb-csto.org](https://en.odkb-csto.org/).

## About CSTO

The Collective Security Treaty Organization is an intergovernmental military alliance in Eurasia, consisting of Armenia, Belarus, Kazakhstan, Kyrgyzstan, Russia, and Tajikistan. The organization originated from the Collective Security Treaty signed in Tashkent on May 15, 1992, and was transformed into an international organization in 2002.

## Available Functions

### get_history
Retrieves the 25-year history timeline and organizational overview, including:
- Historical overview of the organization's creation
- Timeline of key years in CSTO history
- List of member states
- Organizational bodies (Collective Security Council, Council of Foreign Ministers, etc.)

**Example:**
```python
execute({"function": "get_history"}, ctx)
```

### get_sessions
Retrieves a list of CSTO Collective Security Council sessions with dates and summaries.

**Optional Parameters:**
- `year`: Filter sessions by year (e.g., "2022")
- `limit`: Maximum number of sessions to return (default: 20)

**Example:**
```python
# Get all sessions
execute({"function": "get_sessions"}, ctx)

# Get sessions from 2022
execute({"function": "get_sessions", "year": "2022"}, ctx)

# Get 5 most recent sessions
execute({"function": "get_sessions", "limit": 5}, ctx)
```

### get_session_detail
Retrieves detailed information about a specific session.

**Required Parameters:**
- `url`: The URL path of the session page

**Example:**
```python
execute({
    "function": "get_session_detail",
    "url": "/session/2022/sovet-kollektivnoy-bezopasnosti-23-noyabrya-v-erevane-obsudil-aktualnye-problemy-mezhdunarodnoy-i-re/"
}, ctx)
```

### get_news
Retrieves recent CSTO news items.

**Optional Parameters:**
- `limit`: Maximum number of news items to return (default: 15)

**Example:**
```python
execute({"function": "get_news", "limit": 10}, ctx)
```

### get_documents
Retrieves CSTO documents and treaties, including:
- Collective Security Treaty (1992)
- CSTO Charter (2002)
- UN Resolutions on CSTO cooperation
- Ministerial statements

**Optional Parameters:**
- `limit`: Maximum number of documents to return (default: 20)

**Example:**
```python
execute({"function": "get_documents"}, ctx)
```

### get_leadership
Retrieves the leadership history of CSTO, including:
- Secretaries General with their terms
- Deputy Secretaries General with their terms

**Example:**
```python
execute({"function": "get_leadership"}, ctx)
```

### get_structure
Retrieves the organizational structure of CSTO, including:
- Collective Security Council
- Permanent Council
- Secretariat
- Joint Staff
- Parliamentary Assembly
- Council of Ministers of Foreign Affairs
- Council of Ministers of Defense
- Committee of Secretaries of Security Councils
- Various working groups

**Example:**
```python
execute({"function": "get_structure"}, ctx)
```

## Return Format

All functions return a dictionary with:
- `success`: Boolean indicating if the request was successful
- `title`: Page title
- `url`: Source URL
- Function-specific data (e.g., `sessions`, `news`, `documents`, `history`)
- `error`: Error message if `success` is False

## Notes

- The site is primarily in English with some content in Russian
- Dates are returned in both raw format (DD.MM.YYYY) and ISO format (YYYY-MM-DD)
- Session and news URLs often contain Russian text in the path but the content is in English
- The site covers CSTO activities from 1992 to present
