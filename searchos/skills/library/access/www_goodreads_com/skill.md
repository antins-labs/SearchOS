# Goodreads Access Skill

Extract structured data from Goodreads pages including book details, author information, and Choice Awards winners.

## Features

### Book Page Parsing (`parse_book`)

Extracts comprehensive book information from any Goodreads book page:

**Data Sources:**
- JSON-LD structured data (standard Schema.org)
- `__NEXT_DATA__` Apollo state (rich Goodreads-specific data)
- Open Graph meta tags (fallback)

**Extracted Fields:**
- Basic: `title`, `title_complete`, `book_id`, `url`, `web_url`, `description`, `image`, `format`, `pages`, `language`
- Authors: `authors`, `author_urls`, `author_details` (name, ID, URL, role)
- Ratings: `rating.average`, `rating.count`, `rating.review_count`
- Advanced: `rating_stats.distribution` (1-5 star breakdown), `genres`, `series`, `awards`, `detailed_awards`

**Example:**
```python
result = await execute({
    "function": "parse_book",
    "url": "https://www.goodreads.com/book/show/1"
})

# Returns:
{
    "success": True,
    "book_id": "1",
    "title": "Harry Potter and the Half-Blood Prince",
    "title_complete": "Harry Potter and the Half-Blood Prince (Harry Potter, #6)",
    "authors": ["J.K. Rowling"],
    "author_details": {
        "name": "J.K. Rowling",
        "legacy_id": 1077326,
        "url": "https://www.goodreads.com/author/show/1077326",
        "role": "Author"
    },
    "rating": {"average": 4.58, "count": 3732159, "review_count": 73366},
    "rating_stats": {
        "average": 4.58,
        "ratings_count": 3732159,
        "reviews_count": 73366,
        "distribution": [20490, 39978, 246908, 877950, 2546833]
    },
    "genres": ["Fantasy", "Fiction", "Young Adult", "Harry Potter", "Magic"],
    "series": [{"title": "Harry Potter", "position": "6"}],
    "pages": 652,
    "awards": "Locus Award Best Young Adult Novel (2006), ..."
}
```

### Author Page Parsing (`parse_author`)

Extracts author profile and their books:

**Extracted Fields:**
- `name`, `author_id`, `url`, `canonical_url`, `image`, `description`, `book_count`
- `books`: List of books with `title`, `url`, `book_id`, `average_rating`, `ratings_count`, `cover`

**Example:**
```python
result = await execute({
    "function": "parse_author",
    "url": "https://www.goodreads.com/author/show/1077326.J_K_Rowling"
})

# Returns:
{
    "success": True,
    "author_id": "1077326",
    "name": "J.K. Rowling",
    "description": "Although she writes under the pen name J.K. Rowling...",
    "image": "https://images.gr-assets.com/authors/1596216614p8/1077326.jpg",
    "books": [
        {
            "title": "Harry Potter and the Philosopher's Stone (Harry Potter, #1)",
            "url": "https://www.goodreads.com/book/show/42844155-harry-potter...",
            "book_id": "42844155",
            "average_rating": 4.47,
            "ratings_count": 11661833,
            "cover": "https://i.gr-assets.com/images/S/compressed..."
        },
        ...
    ]
}
```

### Choice Awards Parsing (`parse_choice_awards`)

Extracts winners from Goodreads annual Choice Awards:

**Extracted Fields:**
- `year`, `title`, `description`, `logo_image`
- `categories`: List of award categories with winners

**Example:**
```python
result = await execute({
    "function": "parse_choice_awards",
    "url": "https://www.goodreads.com/choiceawards/best-books-2024"
})

# Returns:
{
    "success": True,
    "year": "2024",
    "title": "Announcing the Winners of the 2024 Goodreads Choice Awards!",
    "categories": [
        {
            "name": "Fiction",
            "winner": {
                "title": "The Wedding People",
                "image_url": "https://i.gr-assets.com/images/S/compressed..."
            }
        },
        {
            "name": "Historical Fiction",
            "winner": {
                "title": "The Women",
                "image_url": "https://i.gr-assets.com/images/S/compressed..."
            }
        },
        ...
    ]
}
```

## Data Quality

### Book Pages

The skill exploits Goodreads' Next.js hydration data (`__NEXT_DATA__`) which contains the full Apollo GraphQL state. This provides:

- Rating distribution (exact count per star)
- Detailed award information with designation (WINNER/NOMINEE)
- Series position information
- Primary and secondary contributors with roles

For pages without this data, it gracefully falls back to JSON-LD and Open Graph meta tags.

### Reliability

- **HTTP-only**: No browser automation required, fast and reliable
- **Multiple data sources**: Prioritizes the richest available data
- **Error handling**: Returns structured errors with descriptive messages
- **Rate limiting**: Consider adding delays between requests for bulk processing

## Notes

1. **URL format**: Supports both legacy IDs (e.g., `/book/show/1`) and slug URLs
2. **Author ID extraction**: Handles both numeric IDs and slug URLs
3. **Year inference**: Automatically extracts year from Choice Awards URL
4. **Pre-fetched HTML**: Can parse provided HTML with `html` parameter to avoid duplicate HTTP requests

## Technical Details

- Uses `httpx` for HTTP requests with standard browser headers
- Uses `BeautifulSoup4` for HTML parsing
- No external API calls or authentication required
- All parsing is done locally on the fetched HTML