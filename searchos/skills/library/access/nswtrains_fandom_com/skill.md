# NSW Trains Fandom Wiki Access Skill

This skill retrieves train line information from the NSW Trains Fandom wiki (nswtrains.fandom.com), a community-maintained encyclopedia of Sydney Trains and NSW TrainLink services.

## Features

### Search Pages
Search the wiki for pages matching a query:
```python
execute({
    "function": "search",
    "query": "North Shore",
    "limit": 10
})
```
Returns page titles, snippets, and metadata for matching pages.

### Get Train Line Details
Retrieve comprehensive information about a specific train line:
```python
execute({
    "function": "get_line",
    "title": "T7 Olympic Park line"
})

# Or by page ID
execute({
    "function": "get_line",
    "pageid": 4809
})
```
Returns:
- `infobox`: Parsed infobox data (colour, stations count, operator, rolling stock, etc.)
- `introduction`: Page introduction/summary text
- `sections`: List of page sections
- `categories`: Wiki categories the page belongs to

### Get Stations Table
Extract the stations table from a train line page:
```python
execute({
    "function": "get_stations",
    "title": "T1 North Shore and Western line"
})
```
Returns:
- `stations`: List of stations with name, code, distance, opening year, railway line, serving suburbs, and interchange information
- `station_count`: Total number of stations found

### List Train Lines
List all train line pages in the wiki:
```python
execute({
    "function": "list_lines",
    "prefix": "T",
    "limit": 50
})
```
Returns all pages starting with the specified prefix (default: "T" for train lines like T1, T2, etc.)

## Available Train Lines

The wiki contains pages for Sydney Trains lines including:
- **T1** North Shore and Western line
- **T2** Leppington and Inner West line
- **T3** Liverpool and Inner West line / Bankstown line
- **T4** Eastern Suburbs and Illawarra line
- **T5** Cumberland line
- **T6** Lidcombe and Bankstown line
- **T7** Olympic Park line
- **T8** Airport and South line
- **T9** Northern line

Plus various station pages, rolling stock information, and historical data.

## Data Sources

This skill queries the Fandom MediaWiki API directly, which provides:
- Wikitext content with infobox templates
- Parsed HTML for table extraction
- Search and page listing capabilities

The wiki is maintained by the community and includes detailed information about:
- Line routes and stations
- Fleet and rolling stock
- Operating patterns
- Historical changes
- Infrastructure details

## Technical Notes

- Uses Fandom's MediaWiki API at `https://nswtrains.fandom.com/api.php`
- Infobox templates are parsed from wikitext source
- Station tables are parsed from rendered HTML
- All requests include appropriate User-Agent headers
- Timeout handling for reliable operation