# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# SciSpace Journal Access Skill

## Overview

This skill provides access to SciSpace journal pages at scispace.com. The site hosts structured journal metadata and academic content.

## Important: CAPTCHA Protection

**SciSpace uses AWS WAF image-based CAPTCHA protection** that cannot be reliably automated. When accessing journal pages, you may encounter:

1. **Human Verification Page** - A CAPTCHA challenge page with status 405
2. **Image Selection Puzzle** - Requires selecting images matching a category (e.g., "Choose all the clocks")
3. **Interactive Verification** - Requires clicking "Begin", solving the puzzle, and clicking "Confirm"

### CAPTCHA Response

When a CAPTCHA is detected, the skill returns:
```json
{
  "success": false,
  "error": "CAPTCHA_REQUIRED",
  "error_details": {
    "type": "AWS WAF Image CAPTCHA",
    "description": "This site requires solving an image-based CAPTCHA to access content"
  },
  "captcha_info": {
    "has_begin_button": true,
    "puzzle_question": "Choose all the clocks",
    "has_confirm_button": true
  }
}
```

## Functions

### get_journal_info

Attempts to access a SciSpace journal page and extract metadata.

**Parameters:**
- `url` (optional): Full journal URL
  - Example: `https://scispace.com/journals/journal-of-the-institute-of-telecommunications-professionals-3jwh2biv`
- `journal_slug` (optional): Journal identifier from URL
  - Example: `journal-of-the-institute-of-telecommunications-professionals-3jwh2biv`

**Returns:**
- If CAPTCHA is triggered: Error with CAPTCHA details
- If successful: Journal metadata including title, description, and other information

**Example Call:**
```python
result = await execute({
    "function": "get_journal_info",
    "journal_slug": "journal-of-the-institute-of-telecommunications-professionals-3jwh2biv"
}, ctx)
```

### check_captcha_status

Checks if a specific URL requires CAPTCHA verification.

**Parameters:**
- `url` (required): The URL to check

**Returns:**
- `requires_captcha`: Boolean indicating if CAPTCHA is required
- `captcha_type`: Type of CAPTCHA if present

**Example Call:**
```python
result = await execute({
    "function": "check_captcha_status",
    "url": "https://scispace.com/journals/example-journal"
}, ctx)
```

### extract_journal_slug

Extracts the journal slug from a SciSpace URL.

**Parameters:**
- `url` (required): The journal URL

**Returns:**
- `journal_slug`: The extracted slug identifier

**Example Call:**
```python
result = await execute({
    "function": "extract_journal_slug",
    "url": "https://scispace.com/journals/journal-of-the-institute-of-telecommunications-professionals-3jwh2biv"
}, ctx)
# Returns: {"success": true, "journal_slug": "journal-of-the-institute-of-telecommunications-professionals-3jwh2biv"}
```

## Limitations

1. **CAPTCHA Cannot Be Bypassed**: The AWS WAF image-based CAPTCHA requires human visual recognition and interaction. This skill detects and reports the CAPTCHA but cannot solve it.

2. **Access May Be Intermittent**: Even when CAPTCHA is not immediately triggered, subsequent requests may require verification.

3. **No API Alternative**: SciSpace does not provide a public API for accessing journal metadata without browser interaction.

## Technical Details

- **User Agent**: Uses Chrome browser user agent for compatibility
- **Browser**: Playwright Chromium in headless mode
- **Timeout**: 30-second navigation timeout
- **CAPTCHA Detection**: Checks for "Human Verification" title and HTTP 405 status

## Error Handling

The skill returns structured error responses:

| Error | Description |
|-------|-------------|
| `CAPTCHA_REQUIRED` | AWS WAF CAPTCHA is blocking access |
| `Unknown function` | Invalid function name provided |
| `URL parameter is required` | Missing required URL parameter |
| `Browser error` | Playwright/navigation error |

## Use Cases

1. **Check Journal Availability**: Use `check_captcha_status` to see if a journal page is accessible
2. **Extract Journal Slug**: Use `extract_journal_slug` to parse URLs
3. **Attempt Access**: Use `get_journal_info` to try accessing journal metadata (may hit CAPTCHA)

## Notes

- The skill uses a real Chrome browser user agent for better compatibility
- CAPTCHA challenges are common on this site and cannot be automated
- Journal metadata extraction is only possible when CAPTCHA is not triggered
