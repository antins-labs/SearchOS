# Douban Books (book.douban.com) Access Skill

This skill provides structured access to Douban Books, one of China's largest book information platforms.

## Features

### 📚 Book Details (`get_book`)
Retrieve comprehensive book information including:
- Title and author(s)
- Rating and number of ratings
- ISBN, publisher, publication date
- Price, page count, binding
- Cover image URL
- Summary/description

### 🏢 Publisher Catalog (`get_press_books`)
List all books from a specific publisher with:
- Book title, cover, rating
- Publication info (author, year, price)
- Pagination support

### ✍️ Author Bibliography (`get_author_books`)
List all works by an author with:
- Book title, cover, rating
- Publication year
- Sort by time or rating
- Pagination support

### 🔍 Search (`search`)
Search for books by keyword (may require authentication for full results)

## Usage Examples

### Get a specific book
```python
params = {
    "function": "get_book",
    "subject_id": "1770782"  # The Kite Runner
}
```

### Browse publisher's catalog
```python
params = {
    "function": "get_press_books",
    "press_id": "2291",  # People's Publishing House
    "page": 1
}
```

### List author's works
```python
params = {
    "function": "get_author_books",
    "author_id": "4572453",
    "sortby": "time"  # or "score"
}
```

### Search books
```python
params = {
    "function": "search",
    "query": "追风筝的人",
    "start": 0
}
```

## ID Extraction

IDs can be extracted from Douban URLs:
- **Subject ID**: `book.douban.com/subject/1770782/` → `1770782`
- **Press ID**: `book.douban.com/press/2595` → `2595`
- **Author ID**: `book.douban.com/author/4572453/` → `4572453`

## Response Structure

All responses include:
- `success`: Boolean indicating if the request succeeded
- `error`: Error message if success is false
- Function-specific data fields

### Book Detail Response
```json
{
  "success": true,
  "subject_id": "1770782",
  "title": "追风筝的人",
  "rating": "8.9",
  "rating_count": 827434,
  "author": "卡勒德·胡赛尼",
  "publisher": "上海人民出版社",
  "isbn": "9787202061644",
  "price": "29.00元",
  "pages": "362",
  "cover_url": "https://...",
  "summary": "..."
}
```

### List Response (Press/Author)
```json
{
  "success": true,
  "books": [
    {
      "subject_id": "1770782",
      "title": "追风筝的人",
      "url": "https://book.douban.com/subject/1770782/",
      "cover_url": "https://...",
      "rating": "8.9",
      "pub_info": "卡勒德·胡赛尼 / 上海人民出版社 / 2006-5 / 29.00元"
    }
  ],
  "current_page": 1,
  "total_pages": 15
}
```

## Limitations

- Search functionality may redirect to login for some queries
- Some rare books may have limited information
- Rating data is user-generated and changes over time
- Rate limiting may apply for heavy usage