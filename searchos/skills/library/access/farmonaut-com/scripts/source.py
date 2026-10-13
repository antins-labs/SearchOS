"""
Farmonaut Mining Data Skill

Extracts mineral reserves tables from farmonaut.com mining pages.
Primary use case: USGS Mineral Commodity Summaries data with country-level reserves.
"""

from __future__ import annotations

import asyncio
import re
from html.parser import HTMLParser
from typing import Any

import aiohttp


class TableParser(HTMLParser):
    """Parse HTML tables into structured data"""
    
    def __init__(self):
        super().__init__()
        self.tables: list[dict] = []
        self.current_table: dict | None = None
        self.current_row: list[dict] | None = None
        self.current_cell: str = ""
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.cell_tag: str | None = None
        
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == "table":
            self.in_table = True
            self.current_table = {"headers": [], "rows": []}
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell_tag = tag
            self.current_cell = ""
            
    def handle_endtag(self, tag: str):
        if tag == "table" and self.in_table:
            if self.current_table:
                self.tables.append(self.current_table)
            self.in_table = False
            self.current_table = None
        elif tag == "tr" and self.in_row:
            if self.current_row and self.current_table is not None:
                has_th = any(cell.get("is_header", False) for cell in self.current_row)
                if has_th and not self.current_table["headers"]:
                    self.current_table["headers"] = [c["text"] for c in self.current_row]
                else:
                    self.current_table["rows"].append([c["text"] for c in self.current_row])
            self.in_row = False
            self.current_row = None
        elif tag in ("td", "th") and self.in_cell:
            if self.current_row is not None:
                self.current_row.append({
                    "text": self.current_cell.strip(),
                    "is_header": self.cell_tag == "th"
                })
            self.in_cell = False
            self.current_cell = ""
            
    def handle_data(self, data: str):
        if self.in_cell:
            self.current_cell += data


async def fetch_page(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch HTML content from URL"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            html = await resp.text()
            return resp.status, html


def extract_tables(html: str) -> list[dict]:
    """Parse all tables from HTML"""
    parser = TableParser()
    parser.feed(html)
    return parser.tables


def find_data_table(tables: list[dict]) -> dict | None:
    """Find the main data table (with reserves/country columns)"""
    for table in tables:
        headers_lower = [h.lower() for h in table.get('headers', [])]
        if any('reserves' in h or 'country' in h for h in headers_lower):
            return table
    
    # Fall back to first substantial table
    for table in tables:
        if len(table.get('rows', [])) >= 3:
            return table
    
    return tables[0] if tables else None


def table_to_records(table: dict) -> list[dict]:
    """Convert table to list of records"""
    headers = table.get('headers', [])
    if not headers and table.get('rows'):
        headers = [f"col_{i}" for i in range(len(table['rows'][0]))]
    
    records = []
    for row in table.get('rows', []):
        if row and any(cell for cell in row):
            record = {}
            for i, cell in enumerate(row):
                key = headers[i] if i < len(headers) else f"col_{i}"
                record[key] = cell
            records.append(record)
    
    return records


async def get_mineral_reserves(url: str) -> dict[str, Any]:
    """
    Extract mineral reserves table from a farmonaut URL.
    
    Args:
        url: Full URL to the farmonaut mining page
        
    Returns:
        Dict with title, headers, row_count, data, or error
    """
    try:
        status, html = await fetch_page(url)
        
        if status != 200:
            return {"error": f"HTTP {status}", "url": url}
        
        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Unknown"
        
        # Parse tables
        tables = extract_tables(html)
        
        if not tables:
            return {"error": "No tables found on page", "url": url, "title": title}
        
        # Find main data table
        data_table = find_data_table(tables)
        
        if not data_table:
            return {"error": "No suitable data table found", "url": url, "title": title}
        
        # Convert to records
        records = table_to_records(data_table)
        
        return {
            "url": url,
            "title": title,
            "headers": data_table.get('headers', []),
            "row_count": len(records),
            "data": records
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def get_all_tables(url: str) -> dict[str, Any]:
    """
    Extract all tables from a farmonaut URL.
    
    Args:
        url: Full URL to the farmonaut page
        
    Returns:
        Dict with title, table_count, tables (list of {headers, rows, row_count})
    """
    try:
        status, html = await fetch_page(url)
        
        if status != 200:
            return {"error": f"HTTP {status}", "url": url}
        
        # Extract title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Unknown"
        
        # Parse tables
        tables = extract_tables(html)
        
        result_tables = []
        for i, table in enumerate(tables):
            records = table_to_records(table)
            result_tables.append({
                "table_index": i,
                "headers": table.get('headers', []),
                "row_count": len(records),
                "data": records
            })
        
        return {
            "url": url,
            "title": title,
            "table_count": len(result_tables),
            "tables": result_tables
        }
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Farmonaut Mining Data skill.
    
    Functions:
        - get_mineral_reserves: Extract mineral reserves table from a URL
        - get_all_tables: Extract all tables from a URL
    
    Parameters:
        function: The function to call (required)
        url: The farmonaut URL to fetch (required)
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    if function == "get_mineral_reserves":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        return await get_mineral_reserves(url)
    
    elif function == "get_all_tables":
        url = params.get("url")
        if not url:
            return {"error": "Missing required parameter: url"}
        return await get_all_tables(url)
    
    else:
        return {"error": f"Unknown function: {function}"}