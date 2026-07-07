# Zhihu Zhuanlan Article Access Skill

This skill retrieves article content from Zhihu's Zhuanlan (知乎专栏) platform at `zhuanlan.zhihu.com`.

## ⚠️ Important Notice

Zhihu has implemented **strong anti-scraping protections** that block automated browser access:
- All automated requests are redirected to a login/CAPTCHA page
- Direct API calls return `403 Forbidden` with error code `10003`
- This protection applies regardless of browser fingerprinting countermeasures

The skill is structured to work when:
- Zhihu loosens their anti-scraping measures
- Users provide valid login credentials (future enhancement)
- A different access method is discovered

## Parameters

### function (required)
- `get_article`: Retrieve article content by ID or URL
- `close`: Close the browser client and release resources

### article_id (optional)
The numeric article ID from the URL path (e.g., `667602045` from `/p/667602045`)

### url (optional)
The full article URL as an alternative to providing `article_id`

## Usage Examples

### Example 1: Get article by ID
```python
result = await execute({
    'function': 'get_article',
    'article_id': '667602045'
})
```

### Example 2: Get article by URL
```python
result = await execute({
    'function': 'get_article',
    'url': 'https://zhuanlan.zhihu.com/p/667602045'
})
```

### Example 3: Close client when done
```python
result = await execute({
    'function': 'close'
})
```

## Response Structure

### Successful Access (when anti-scraping allows)
```json
{
    "success": true,
    "article": {
        "id": "667602045",
        "title": "文章标题",
        "content": "完整文章内容...",
        "excerpt": "文章摘要",
        "author": {
            "id": 12345,
            "name": "作者名",
            "url_token": "author_token",
            "avatar_url": "https://..."
        },
        "column": {
            "id": 67890,
            "name": "专栏名称"
        },
        "created": 1234567890,
        "updated": 1234567890,
        "comment_count": 42,
        "voteup_count": 128,
        "url": "https://zhuanlan.zhihu.com/p/667602045"
    }
}
```

### Blocked Access (current typical response)
```json
{
    "success": false,
    "error": "access_blocked",
    "message": "Article requires login or CAPTCHA verification. Access blocked by Zhihu anti-scraping system.",
    "article_id": "667602045",
    "redirect_url": "https://www.zhihu.com/signin"
}
```

## Error Codes

- `access_blocked`: Zhihu redirected to login/CAPTCHA page (most common)
- `missing_function`: No function parameter provided
- `missing_article_id`: Neither article_id nor url provided for get_article
- `article_not_found`: Article page loaded but could not extract data
- `fetch_error`: Network or browser error occurred
- `invalid_function`: Unknown function specified

## Technical Implementation

### Anti-Scraping Measures Implemented
The skill attempts to bypass detection using:
1. Playwright with headless Chrome in stealth mode
2. Browser fingerprint randomization
3. Proper Chinese locale and timezone
4. Session cookie establishment via homepage visit
5. Realistic user agent and viewport settings

### Data Extraction Strategies
When access is permitted, data is extracted via:
1. `window.INITIAL_STATE` JavaScript object (primary)
2. Embedded JSON in script tags (fallback)
3. DOM scraping from article elements (last resort)

### API Endpoint (blocked)
The ideal endpoint would be:
```
GET https://zhuanlan.zhihu.com/api/articles/{article_id}
```
But this returns `403` with error: "请求参数异常，请升级客户端后重试" (Request parameter error, please upgrade client)

## Testing Results

All tested articles were blocked:
- https://zhuanlan.zhihu.com/p/667602045 → Blocked
- https://zhuanlan.zhihu.com/p/539778208 → Blocked
- https://zhuanlan.zhihu.com/p/20028520 → Blocked
- https://zhuanlan.zhihu.com/p/19763968 → Blocked

## Future Enhancements

To make this skill work, consider:
1. **Authentication**: Add support for logged-in sessions via cookie injection
2. **Residential Proxies**: Use rotating residential IP addresses
3. **Rate Limiting**: Implement request delays and session rotation
4. **Alternative Sources**: Check if Zhihu provides any public APIs or RSS feeds

## Alternative Approaches

For accessing Zhihu content, users might need to:
1. Use the official Zhihu mobile app or website manually
2. Consider third-party APIs that have partnerships with Zhihu
3. Use paid web scraping services with residential proxies
4. Check if the content is available via RSS readers (some columns offer RSS)

## Related Skills

Consider using specialized web scraping services or platforms that maintain access to heavily protected sites like Zhihu.