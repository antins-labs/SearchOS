"""
Sea Level Research Group (University of Colorado) Access Skill

Fetches global mean sea level (GMSL) time-series data from sealevel.colorado.edu.
Provides access to raw tabular data files and data portal information.
"""

import aiohttp
import re
from datetime import datetime
from typing import Any


async def _fetch_url(url: str, timeout: int = 30) -> tuple[int, str]:
    """Fetch URL and return (status, content)."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            content = await resp.text()
            return resp.status, content


def _parse_gmsl_data(text: str) -> list[dict]:
    """
    Parse GMSL text file into structured data.
    
    Format: decimal year and GMSL value in mm, tab/space separated.
    First line is a header comment starting with '#'.
    """
    data_points = []
    lines = text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        parts = line.split()
        if len(parts) >= 2:
            try:
                date_val = float(parts[0])
                gmsl_val = float(parts[1])
                
                # Convert decimal year to approximate date
                year = int(date_val)
                day_of_year = int((date_val - year) * 365.25)
                
                data_points.append({
                    "decimal_year": round(date_val, 6),
                    "year": year,
                    "day_of_year": day_of_year,
                    "gmsl_mm": round(gmsl_val, 3)
                })
            except ValueError:
                continue
    
    return data_points


def _get_release_filename(release: str) -> str:
    """Convert release identifier to filename format."""
    # Normalize: 2026_rel1 -> 2026rel1 for filename
    normalized = release.replace('_', '')
    return normalized


async def fetch_gmsl_timeseries(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch Global Mean Sea Level time-series data.
    
    Parameters:
        release: Release version (e.g., "2026_rel1", "2025_rel2")
        start_year: Optional start year filter
        end_year: Optional end year filter
        limit: Optional limit on number of data points
    """
    release = params.get("release", "2026_rel1")
    start_year = params.get("start_year")
    end_year = params.get("end_year")
    limit = params.get("limit")
    
    # Build URL
    release_filename = _get_release_filename(release)
    url = f"https://sealevel.colorado.edu/files/{release}/gmsl_{release_filename}_seasons_rmvd.txt"
    
    try:
        status, content = await _fetch_url(url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data: HTTP {status}",
                "url": url,
                "release": release
            }
        
        # Parse the data
        data_points = _parse_gmsl_data(content)
        
        if not data_points:
            return {
                "success": False,
                "error": "No data points found in file",
                "url": url,
                "release": release
            }
        
        # Apply filters
        if start_year is not None:
            data_points = [dp for dp in data_points if dp["year"] >= start_year]
        
        if end_year is not None:
            data_points = [dp for dp in data_points if dp["year"] <= end_year]
        
        if limit is not None and limit > 0:
            data_points = data_points[:limit]
        
        # Calculate statistics
        if data_points:
            gmsl_values = [dp["gmsl_mm"] for dp in data_points]
            stats = {
                "count": len(data_points),
                "min_gmsl_mm": round(min(gmsl_values), 3),
                "max_gmsl_mm": round(max(gmsl_values), 3),
                "mean_gmsl_mm": round(sum(gmsl_values) / len(gmsl_values), 3),
                "year_range": [
                    data_points[0]["decimal_year"],
                    data_points[-1]["decimal_year"]
                ]
            }
        else:
            stats = {"count": 0}
        
        return {
            "success": True,
            "release": release,
            "url": url,
            "description": "Global Mean Sea Level with seasonal signals and GIA removed",
            "unit": "mm",
            "statistics": stats,
            "data": data_points
        }
        
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url,
            "release": release
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "url": url,
            "release": release
        }


async def list_releases(params: dict[str, Any]) -> dict[str, Any]:
    """
    List available data release versions from the data portal.
    """
    url = "https://sealevel.colorado.edu/data"
    
    try:
        status, content = await _fetch_url(url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Failed to fetch data page: HTTP {status}",
                "url": url
            }
        
        # Extract all unique release versions
        versions_raw = re.findall(r'(20\d{2}[_]?rel\d+)', content, re.IGNORECASE)
        
        # Normalize and deduplicate
        versions_set = set()
        for v in versions_raw:
            # Normalize to format: YYYY_relN
            v_lower = v.lower()
            if '_' not in v_lower:
                # Convert 2026rel1 -> 2026_rel1
                match = re.match(r'(20\d{2})(rel\d+)', v_lower)
                if match:
                    v_lower = f"{match.group(1)}_{match.group(2)}"
            versions_set.add(v_lower)
        
        # Sort by year and release number (descending)
        versions = sorted(versions_set, key=lambda x: (
            int(x.split('_')[0]),
            int(re.search(r'rel(\d+)', x).group(1)) if re.search(r'rel(\d+)', x) else 0
        ), reverse=True)
        
        # Get latest version
        latest = versions[0] if versions else None
        
        return {
            "success": True,
            "url": url,
            "total_releases": len(versions),
            "latest_release": latest,
            "releases": versions
        }
        
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "url": url
        }


async def get_release_info(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get detailed information about a specific release.
    
    Parameters:
        release: Release version (e.g., "2026_rel1")
    """
    release = params.get("release", "2026_rel1")
    
    # Try to fetch the data file to verify release exists and get info
    release_filename = _get_release_filename(release)
    url = f"https://sealevel.colorado.edu/files/{release}/gmsl_{release_filename}_seasons_rmvd.txt"
    
    try:
        status, content = await _fetch_url(url)
        
        if status != 200:
            return {
                "success": False,
                "error": f"Release '{release}' not found or unavailable: HTTP {status}",
                "release": release
            }
        
        # Parse header and data
        lines = content.strip().split('\n')
        header = lines[0] if lines and lines[0].startswith('#') else None
        
        data_points = _parse_gmsl_data(content)
        
        if not data_points:
            return {
                "success": False,
                "error": "No data points found in release file",
                "release": release
            }
        
        # Calculate comprehensive statistics
        gmsl_values = [dp["gmsl_mm"] for dp in data_points]
        
        # Calculate trend (simple linear regression)
        n = len(data_points)
        x = [dp["decimal_year"] for dp in data_points]
        y = gmsl_values
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean
        
        # Trend in mm/year
        trend_mm_per_year = slope
        
        return {
            "success": True,
            "release": release,
            "url": url,
            "header": header.strip('# ').strip() if header else None,
            "data_availability": {
                "start_date": {
                    "decimal_year": data_points[0]["decimal_year"],
                    "year": data_points[0]["year"],
                    "day_of_year": data_points[0]["day_of_year"]
                },
                "end_date": {
                    "decimal_year": data_points[-1]["decimal_year"],
                    "year": data_points[-1]["year"],
                    "day_of_year": data_points[-1]["day_of_year"]
                },
                "total_observations": n
            },
            "statistics": {
                "min_gmsl_mm": round(min(gmsl_values), 3),
                "max_gmsl_mm": round(max(gmsl_values), 3),
                "mean_gmsl_mm": round(y_mean, 3),
                "range_mm": round(max(gmsl_values) - min(gmsl_values), 3),
                "trend_mm_per_year": round(trend_mm_per_year, 3),
                "total_rise_mm": round(data_points[-1]["gmsl_mm"] - data_points[0]["gmsl_mm"], 3)
            },
            "description": "Global Mean Sea Level with seasonal signals and GIA (Glacial Isostatic Adjustment) removed",
            "unit": "mm"
        }
        
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "release": release
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "release": release
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Sea Level Research Group access skill.
    
    Dispatches based on the 'function' parameter:
        - fetch_gmsl_timeseries: Get GMSL time-series data
        - list_releases: List available data releases
        - get_release_info: Get detailed info about a specific release
    """
    function = params.get("function", "")
    
    if function == "fetch_gmsl_timeseries":
        return await fetch_gmsl_timeseries(params)
    elif function == "list_releases":
        return await list_releases(params)
    elif function == "get_release_info":
        return await get_release_info(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: '{function}'. "
                     f"Available functions: fetch_gmsl_timeseries, list_releases, get_release_info"
        }