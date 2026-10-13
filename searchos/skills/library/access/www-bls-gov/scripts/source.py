"""
BLS Local Area Unemployment Statistics (LAUS) Data Access Skill

Retrieves unemployment statistics from the BLS Public API v2.
Supports state, county, and metropolitan area queries.

Series ID Format: LAU[AreaType][StateFIPS][AreaCode][Measure]
- Area Types: ST=State, CN=County, MT=Metropolitan, MD=Metro Division
- Measures: 03=Unemployment Rate, 04=Unemployed, 05=Employment, 06=Labor Force

API Documentation: https://www.bls.gov/developers/api_signature_v2.htm
"""

import urllib.request
import urllib.error
import json
import asyncio
from typing import Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# BLS API endpoint
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# State FIPS codes
STATE_FIPS = {
    'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06', 'CO': '08',
    'CT': '09', 'DE': '10', 'DC': '11', 'FL': '12', 'GA': '13', 'HI': '15',
    'ID': '16', 'IL': '17', 'IN': '18', 'IA': '19', 'KS': '20', 'KY': '21',
    'LA': '22', 'ME': '23', 'MD': '24', 'MA': '25', 'MI': '26', 'MN': '27',
    'MS': '28', 'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33',
    'NJ': '34', 'NM': '35', 'NY': '36', 'NC': '37', 'ND': '38', 'OH': '39',
    'OK': '40', 'OR': '41', 'PA': '42', 'RI': '44', 'SC': '45', 'SD': '46',
    'TN': '47', 'TX': '48', 'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53',
    'WV': '54', 'WI': '55', 'WY': '56', 'PR': '72', 'VI': '78',
}

STATE_NAMES = {
    '01': 'Alabama', '02': 'Alaska', '04': 'Arizona', '05': 'Arkansas',
    '06': 'California', '08': 'Colorado', '09': 'Connecticut', '10': 'Delaware',
    '11': 'District of Columbia', '12': 'Florida', '13': 'Georgia', '15': 'Hawaii',
    '16': 'Idaho', '17': 'Illinois', '18': 'Indiana', '19': 'Iowa', '20': 'Kansas',
    '21': 'Kentucky', '22': 'Louisiana', '23': 'Maine', '24': 'Maryland',
    '25': 'Massachusetts', '26': 'Michigan', '27': 'Minnesota', '28': 'Mississippi',
    '29': 'Missouri', '30': 'Montana', '31': 'Nebraska', '32': 'Nevada',
    '33': 'New Hampshire', '34': 'New Jersey', '35': 'New Mexico', '36': 'New York',
    '37': 'North Carolina', '38': 'North Dakota', '39': 'Ohio', '40': 'Oklahoma',
    '41': 'Oregon', '42': 'Pennsylvania', '44': 'Rhode Island', '45': 'South Carolina',
    '46': 'South Dakota', '47': 'Tennessee', '48': 'Texas', '49': 'Utah',
    '50': 'Vermont', '51': 'Virginia', '53': 'Washington', '54': 'West Virginia',
    '55': 'Wisconsin', '56': 'Wyoming', '72': 'Puerto Rico', '78': 'Virgin Islands',
}

# Measure codes and descriptions
MEASURES = {
    '03': {'name': 'Unemployment Rate', 'unit': 'percent', 'code': '03'},
    '04': {'name': 'Unemployed', 'unit': 'persons', 'code': '04'},
    '05': {'name': 'Employment', 'unit': 'persons', 'code': '05'},
    '06': {'name': 'Labor Force', 'unit': 'persons', 'code': '06'},
}


def build_series_id(area_type: str, state_fips: str, area_code: str, measure: str) -> str:
    """
    Build a BLS LAUS series ID.
    
    Args:
        area_type: ST (state), CN (county), MT (metro), MD (metro division)
        state_fips: 2-digit state FIPS code
        area_code: Area-specific code (0000000000 for state-level)
        measure: 03=rate, 04=unemployed, 05=employment, 06=labor force
    
    Returns:
        BLS series ID string
    """
    return f"LAU{area_type}{state_fips}{area_code}{measure}"


def _fetch_series_data_sync(
    series_ids: list[str],
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Synchronous fetch for series data using urllib.
    """
    if not series_ids:
        return {"error": "No series IDs provided", "error_type": "validation"}
    
    current_year = datetime.now().year
    
    if start_year is None:
        start_year = current_year - 3
    if end_year is None:
        end_year = current_year
    
    payload = {
        "seriesid": series_ids,
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    
    if registration_key:
        payload["registrationKey"] = registration_key
    
    headers = {
        "User-Agent": "SearchOS-BLS-LAUS-Skill/1.0 (Data Retrieval)",
        "Content-Type": "application/json",
    }
    
    try:
        req = urllib.request.Request(
            BLS_API_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if data.get("status") == "REQUEST_NOT_PROCESSED":
                messages = data.get("message", [])
                return {
                    "error": "Request not processed",
                    "error_type": "rate_limit",
                    "details": "; ".join(messages) if messages else "Daily rate limit exceeded"
                }
            
            if data.get("status") != "REQUEST_SUCCEEDED":
                messages = data.get("message", [])
                return {
                    "error": "API request failed",
                    "error_type": "api_error",
                    "status": data.get("status"),
                    "details": "; ".join(messages) if messages else "Unknown error"
                }
            
            results = {}
            for series in data.get("Results", {}).get("series", []):
                series_id = series.get("seriesID")
                series_data = series.get("data", [])
                
                if not series_data:
                    msg = data.get("message", [])
                    if any(f"Series does not exist for Series {series_id}" in m for m in msg):
                        results[series_id] = {
                            "series_id": series_id,
                            "error": "Series not found",
                            "error_type": "not_found"
                        }
                    else:
                        results[series_id] = {
                            "series_id": series_id,
                            "error": "No data available",
                            "error_type": "no_data"
                        }
                else:
                    results[series_id] = {
                        "series_id": series_id,
                        "data": series_data,
                        "latest": series_data[0] if series_data else None
                    }
            
            return {
                "success": True,
                "response_time_ms": data.get("responseTime"),
                "series_count": len(results),
                "results": results,
                "query": {
                    "start_year": start_year,
                    "end_year": end_year,
                    "series_requested": series_ids
                }
            }
            
    except urllib.error.HTTPError as e:
        return {
            "error": f"HTTP error: {e.code} {e.reason}",
            "error_type": "http_error"
        }
    except urllib.error.URLError as e:
        return {
            "error": f"URL error: {e.reason}",
            "error_type": "network"
        }
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON parse error: {str(e)}",
            "error_type": "parse"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}",
            "error_type": "unknown"
        }


async def fetch_series_data(
    series_ids: list[str],
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Fetch data for multiple LAUS series from BLS API (async wrapper).
    """
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=4) as executor:
        result = await loop.run_in_executor(
            executor,
            lambda: _fetch_series_data_sync(series_ids, start_year, end_year, registration_key)
        )
    return result


async def get_state_unemployment(
    state: str,
    measure: str = "03",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Get unemployment data for a specific state.
    """
    state_upper = state.upper()
    if state_upper in STATE_FIPS:
        state_fips = STATE_FIPS[state_upper]
        state_name = STATE_NAMES.get(state_fips, state)
    elif state in STATE_NAMES:
        state_fips = state
        state_name = STATE_NAMES[state]
    else:
        return {
            "error": f"Invalid state: {state}",
            "error_type": "validation",
            "valid_states": list(STATE_FIPS.keys())
        }
    
    if measure not in MEASURES:
        return {
            "error": f"Invalid measure: {measure}",
            "error_type": "validation",
            "valid_measures": {k: v["name"] for k, v in MEASURES.items()}
        }
    
    series_id = build_series_id("ST", state_fips, "0000000000", measure)
    
    result = await fetch_series_data(
        [series_id],
        start_year=start_year,
        end_year=end_year,
        registration_key=registration_key
    )
    
    if "error" in result:
        return result
    
    series_data = result.get("results", {}).get(series_id, {})
    
    return {
        "success": True,
        "state": state_name,
        "state_fips": state_fips,
        "state_abbr": state_upper if len(state) == 2 else None,
        "measure": MEASURES[measure]["name"],
        "measure_code": measure,
        "unit": MEASURES[measure]["unit"],
        "series_id": series_id,
        "data": series_data.get("data", []),
        "latest": series_data.get("latest"),
        "query": result.get("query")
    }


async def get_all_states_unemployment(
    measure: str = "03",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Get unemployment data for all US states.
    """
    if measure not in MEASURES:
        return {
            "error": f"Invalid measure: {measure}",
            "error_type": "validation",
            "valid_measures": {k: v["name"] for k, v in MEASURES.items()}
        }
    
    series_ids = [
        build_series_id("ST", fips, "0000000000", measure)
        for fips in sorted(STATE_FIPS.values())
    ]
    
    # Split into chunks to respect rate limits
    chunk_size = 50 if registration_key else 25
    all_results = {}
    errors = []
    
    for i in range(0, len(series_ids), chunk_size):
        chunk = series_ids[i:i + chunk_size]
        result = await fetch_series_data(
            chunk,
            start_year=start_year,
            end_year=end_year,
            registration_key=registration_key
        )
        
        if "error" in result:
            errors.append(f"Chunk {i//chunk_size + 1}: {result['error']}")
        else:
            all_results.update(result.get("results", {}))
    
    states_data = {}
    for state_fips, state_name in sorted(STATE_NAMES.items()):
        series_id = build_series_id("ST", state_fips, "0000000000", measure)
        if series_id in all_results:
            series_info = all_results[series_id]
            states_data[state_name] = {
                "state_fips": state_fips,
                "series_id": series_id,
                "data": series_info.get("data", []),
                "latest": series_info.get("latest"),
            }
            if "error" in series_info:
                states_data[state_name]["error"] = series_info["error"]
    
    return {
        "success": len(errors) == 0,
        "measure": MEASURES[measure]["name"],
        "measure_code": measure,
        "unit": MEASURES[measure]["unit"],
        "states": states_data,
        "states_count": len([s for s in states_data.values() if "error" not in s]),
        "errors": errors if errors else None,
        "query": {
            "start_year": start_year,
            "end_year": end_year,
            "measure": measure
        }
    }


async def get_county_unemployment(
    state: str,
    county_fips: str,
    measure: str = "03",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Get unemployment data for a specific county.
    """
    state_upper = state.upper()
    if state_upper in STATE_FIPS:
        state_fips = STATE_FIPS[state_upper]
        state_name = STATE_NAMES.get(state_fips, state)
    elif state in STATE_NAMES:
        state_fips = state
        state_name = STATE_NAMES[state]
    else:
        return {
            "error": f"Invalid state: {state}",
            "error_type": "validation"
        }
    
    if measure not in MEASURES:
        return {
            "error": f"Invalid measure: {measure}",
            "error_type": "validation",
            "valid_measures": {k: v["name"] for k, v in MEASURES.items()}
        }
    
    county_fips = county_fips.zfill(3)
    series_id = f"LAUCN{state_fips}{county_fips}000000{measure}"
    
    result = await fetch_series_data(
        [series_id],
        start_year=start_year,
        end_year=end_year,
        registration_key=registration_key
    )
    
    if "error" in result:
        return result
    
    series_data = result.get("results", {}).get(series_id, {})
    
    return {
        "success": "error" not in series_data,
        "state": state_name,
        "state_fips": state_fips,
        "county_fips": county_fips,
        "fips_code": f"{state_fips}{county_fips}",
        "measure": MEASURES[measure]["name"],
        "measure_code": measure,
        "unit": MEASURES[measure]["unit"],
        "series_id": series_id,
        "data": series_data.get("data", []),
        "latest": series_data.get("latest"),
        "error": series_data.get("error"),
        "query": result.get("query")
    }


async def search_series(
    query: str,
    limit: int = 20
) -> dict[str, Any]:
    """
    Search for LAUS series by name/state/county.
    """
    query_lower = query.lower()
    suggestions = []
    
    for abbr, fips in STATE_FIPS.items():
        state_name = STATE_NAMES.get(fips, "")
        if query_lower in state_name.lower() or query_lower == abbr.lower():
            suggestions.append({
                "type": "state",
                "name": state_name,
                "abbreviation": abbr,
                "fips": fips,
                "series_templates": {
                    measure: build_series_id("ST", fips, "0000000000", measure)
                    for measure in MEASURES
                }
            })
    
    if query.isdigit() and len(query) >= 2:
        state_fips = query[:2]
        if state_fips in STATE_NAMES:
            suggestions.append({
                "type": "state",
                "name": STATE_NAMES[state_fips],
                "fips": state_fips,
                "note": f"Query matched FIPS code {query}"
            })
    
    return {
        "success": True,
        "query": query,
        "suggestions": suggestions[:limit],
        "total": len(suggestions)
    }


async def get_latest_rates(
    registration_key: Optional[str] = None
) -> dict[str, Any]:
    """
    Get latest unemployment rates for all 50 states + DC.
    """
    result = await get_all_states_unemployment(
        measure="03",
        start_year=datetime.now().year - 1,
        end_year=datetime.now().year,
        registration_key=registration_key
    )
    
    if "error" in result:
        return result
    
    latest_rates = {}
    for state_name, data in result.get("states", {}).items():
        latest = data.get("latest")
        if latest and "value" in latest:
            latest_rates[state_name] = {
                "rate": latest.get("value"),
                "period": latest.get("periodName"),
                "year": latest.get("year"),
                "footnotes": latest.get("footnotes", [])
            }
    
    sorted_rates = dict(sorted(
        latest_rates.items(),
        key=lambda x: float(x[1]["rate"]) if x[1]["rate"] else 999
    ))
    
    return {
        "success": True,
        "description": "Latest unemployment rates by state",
        "as_of": f"{list(latest_rates.values())[0]['period'] if latest_rates else 'N/A'} {list(latest_rates.values())[0]['year'] if latest_rates else 'N/A'}",
        "rates": sorted_rates,
        "states_count": len(latest_rates),
        "lowest": list(sorted_rates.keys())[:3] if sorted_rates else [],
        "highest": list(sorted_rates.keys())[-3:] if sorted_rates else []
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for BLS LAUS data access.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "Missing required parameter: function",
            "error_type": "validation",
            "available_functions": [
                "get_state", "get_all_states", "get_county",
                "search", "get_latest_rates", "fetch_series"
            ]
        }
    
    measure = params.get("measure", "03")
    start_year = params.get("start_year")
    end_year = params.get("end_year")
    registration_key = params.get("registration_key")
    
    if start_year is not None:
        start_year = int(start_year)
    if end_year is not None:
        end_year = int(end_year)
    
    if function == "get_state":
        state = params.get("state")
        if not state:
            return {"error": "Missing required parameter: state", "error_type": "validation"}
        
        return await get_state_unemployment(
            state=state,
            measure=measure,
            start_year=start_year,
            end_year=end_year,
            registration_key=registration_key
        )
    
    elif function == "get_all_states":
        return await get_all_states_unemployment(
            measure=measure,
            start_year=start_year,
            end_year=end_year,
            registration_key=registration_key
        )
    
    elif function == "get_county":
        state = params.get("state")
        county_fips = params.get("county_fips")
        
        if not state:
            return {"error": "Missing required parameter: state", "error_type": "validation"}
        if not county_fips:
            return {"error": "Missing required parameter: county_fips", "error_type": "validation"}
        
        return await get_county_unemployment(
            state=state,
            county_fips=county_fips,
            measure=measure,
            start_year=start_year,
            end_year=end_year,
            registration_key=registration_key
        )
    
    elif function == "search":
        query = params.get("query")
        if not query:
            return {"error": "Missing required parameter: query", "error_type": "validation"}
        
        return await search_series(
            query=query,
            limit=params.get("limit", 20)
        )
    
    elif function == "get_latest_rates":
        return await get_latest_rates(registration_key=registration_key)
    
    elif function == "fetch_series":
        series_ids = params.get("series_ids")
        if not series_ids:
            return {"error": "Missing required parameter: series_ids", "error_type": "validation"}
        
        if isinstance(series_ids, str):
            series_ids = [series_ids]
        
        return await fetch_series_data(
            series_ids=series_ids,
            start_year=start_year,
            end_year=end_year,
            registration_key=registration_key
        )
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "error_type": "validation",
            "available_functions": [
                "get_state", "get_all_states", "get_county",
                "search", "get_latest_rates", "fetch_series"
            ]
        }