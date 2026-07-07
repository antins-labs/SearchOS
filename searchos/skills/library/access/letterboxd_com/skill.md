# Letterboxd Access Skill

Fetches movie and actor data from [Letterboxd](https://letterboxd.com), a social film discovery and review platform.

## Features

- **Film Details**: Extract comprehensive movie information including:
  - Title, year, poster image
  - Directors, cast list
  - Production studios
  - Average rating
  - Description and tagline
  - Film ID

- **Actor Filmography**: Get complete filmography for any actor:
  - Actor name and profile info
  - List of all films (up to ~125 per page)
  - Film titles with years and URLs
  - Internal IDs for cross-referencing

## Functions

### `get_film`

Fetch detailed movie information by film slug.

**Example:**
```python
result = await execute({
    'function': 'get_film',
    'slug': 'the-lord-of-the-rings-the-fellowship-of-the-ring'
})
```

**Returns:**
```json
{
  "title": null,
  "year": "2001",
  "poster_image": "https://a.ltrbxd.com/...",
  "url": "https://letterboxd.com/film/...",
  "directors": ["Peter Jackson"],
  "actors": [{"name": "Elijah Wood", "url": "/actor/elijah-wood/"}],
  "studios": [{"name": "New Line Cinema", "url": "/studio/new-line-cinema/"}],
  "average_rating": "4.5 out of 5",
  "film_id": "51930",
  "description": "...",
  "tagline": "..."
}
```

### `get_actor_filmography`

Get all films for an actor by their slug.

**Example:**
```python
result = await execute({
    'function': 'get_actor_filmography',
    'slug': 'cate-blanchett'
})
```

**Returns:**
```json
{
  "name": "Cate Blanchett",
  "slug": "cate-blanchett",
  "source_url": "https://letterboxd.com/actor/cate-blanchett/",
  "film_count": 125,
  "films": [
    {
      "name": "The Lord of the Rings: The Fellowship of the Ring (2001)",
      "slug": "the-lord-of-the-rings-the-fellowship-of-the-ring",
      "link": "/film/the-lord-of-the-rings-the-fellowship-of-the-ring/",
      "full_url": "https://letterboxd.com/film/the-lord-of-the-rings-the-fellowship-of-the-ring/",
      "lid": "2b5O",
      "uid": "film:51930"
    },
    ...
  ]
}
```

## Finding Slugs

The slug is extracted from the Letterboxd URL:

- Film: `https://letterboxd.com/film/the-turning-2013/` → slug: `the-turning-2013`
- Actor: `https://letterboxd.com/actor/cate-blanchett/` → slug: `cate-blanchett`

Common slug patterns:
- Films often include the year suffix for disambiguation: `inception`, `dune-2021`
- Actor slugs use lowercase with hyphens: `leonardo-dicaprio`, `scarlett-johansson`

## Data Sources

- **Film pages**: Parse JSON-LD structured data (`<script type="application/ld+json">`)
  - Includes directors, actors, studios, release year
  - Additional HTML metadata for ratings, descriptions
  - Internal IDs from JavaScript data

- **Actor pages**: Parse React component data attributes
  - `data-component-class="LazyPoster"` elements
  - Contains film names, slugs, and internal IDs

## Notes

- Letterboxd's JSON API endpoints (e.g., `/film/slug/json/`) return 403 due to Cloudflare protection
- This skill parses the published HTML pages instead
- Single-page filmography only (first ~125 films for prolific actors)
- Cloudflare may occasionally block requests; retry after a delay if needed