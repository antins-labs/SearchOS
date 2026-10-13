"""
IBGE Municipality Statistics Access Skill

Fetches official Brazilian municipality statistics from IBGE (Instituto Brasileiro de Geografia e Estatística)
using their public API endpoints. This skill bypasses the Cloudflare-protected website by using the 
servicodados.ibge.gov.br API directly.

Data sources:
- Survey 33 (Sinopse Municipal): Basic municipality info, population, area, etc.
- Survey 37 (IDH): Human Development Index
- Localidades API: Geographic and administrative data
"""

import asyncio
import aiohttp
from typing import Any


# IBGE API base URL
IBGE_API_BASE = "https://servicodados.ibge.gov.br/api/v1"

# Sinopse Municipal (Survey 33) indicator IDs
SINOPSE_INDICATORS = {
    29171: "População estimada",
    29166: "População (Censo)",
    29167: "Área da unidade territorial",
    29168: "Densidade demográfica",
    29169: "Código do Município",
    29170: "Prefeito",
    60409: "Gentílico",
    77861: "Bioma Predominante",
    82270: "Sistema costeiro-marinho",
    91244: "Código da Região Geográfica Intermediária",
    91245: "Nome da Região Geográfica Intermediária",
    91246: "Código da Região Geográfica Imediata",
    91247: "Nome da Região Geográfica Imediata",
    91248: "Código da Mesorregião Geográfica",
    91249: "Nome da Mesorregião Geográfica",
    91250: "Código da Microrregião Geográfica",
    91251: "Nome da Microrregião Geográfica",
}


async def fetch_json(session: aiohttp.ClientSession, url: str, timeout: float = 15.0) -> dict | list | None:
    """Fetch JSON from URL with error handling."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                return await response.json()
            return None
    except asyncio.TimeoutError:
        return None
    except aiohttp.ClientError:
        return None
    except Exception:
        return None


async def search_municipalities(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Search for municipalities by name."""
    url = f"{IBGE_API_BASE}/localidades/municipios"
    data = await fetch_json(session, url, timeout=30.0)
    
    if not data:
        return []
    
    # Filter municipalities by name (case-insensitive)
    query_lower = query.lower()
    matches = [
        {
            "id": m["id"],
            "nome": m["nome"],
            "uf_sigla": m["microrregiao"]["mesorregiao"]["UF"]["sigla"],
            "uf_nome": m["microrregiao"]["mesorregiao"]["UF"]["nome"],
            "regiao": m["microrregiao"]["mesorregiao"]["UF"]["regiao"]["nome"],
        }
        for m in data
        if query_lower in m["nome"].lower()
    ]
    
    return matches


async def get_municipality_by_id(session: aiohttp.ClientSession, municipality_id: int) -> dict | None:
    """Get municipality details by ID."""
    url = f"{IBGE_API_BASE}/localidades/municipios/{municipality_id}"
    data = await fetch_json(session, url)
    
    if not data or (isinstance(data, list) and len(data) == 0):
        return None
    
    # Handle both list and dict responses
    m = data[0] if isinstance(data, list) else data
    
    return {
        "id": m["id"],
        "nome": m["nome"],
        "microrregiao": m.get("microrregiao", {}).get("nome"),
        "mesorregiao": m.get("microrregiao", {}).get("mesorregiao", {}).get("nome"),
        "uf_sigla": m.get("microrregiao", {}).get("mesorregiao", {}).get("UF", {}).get("sigla"),
        "uf_nome": m.get("microrregiao", {}).get("mesorregiao", {}).get("UF", {}).get("nome"),
        "regiao": m.get("microrregiao", {}).get("mesorregiao", {}).get("UF", {}).get("regiao", {}).get("nome"),
        "regiao_imediata": m.get("regiao-imediata", {}).get("nome"),
        "regiao_intermediaria": m.get("regiao-imediata", {}).get("regiao-intermediaria", {}).get("nome"),
    }


async def get_municipalities_by_state(session: aiohttp.ClientSession, state_sigla: str) -> list[dict]:
    """Get all municipalities for a state."""
    url = f"{IBGE_API_BASE}/localidades/estados/{state_sigla.upper()}/municipios"
    data = await fetch_json(session, url, timeout=30.0)
    
    if not data:
        return []
    
    return [
        {
            "id": m["id"],
            "nome": m["nome"],
            "microrregiao": m.get("microrregiao", {}).get("nome"),
        }
        for m in data
    ]


async def get_all_states(session: aiohttp.ClientSession) -> list[dict]:
    """Get all Brazilian states."""
    url = f"{IBGE_API_BASE}/localidades/estados"
    data = await fetch_json(session, url)
    
    if not data:
        return []
    
    return [
        {
            "id": s["id"],
            "sigla": s["sigla"],
            "nome": s["nome"],
            "regiao": s.get("regiao", {}).get("nome"),
        }
        for s in data
    ]


async def get_municipality_statistics(session: aiohttp.ClientSession, municipality_id: int) -> dict:
    """Get statistics for a municipality from Sinopse Municipal survey."""
    statistics = {}
    
    # Fetch all indicators concurrently
    async def fetch_indicator(ind_id: int, ind_name: str) -> tuple[str, dict | None]:
        url = f"{IBGE_API_BASE}/pesquisas/indicadores/{ind_id}/resultados/{municipality_id}"
        data = await fetch_json(session, url)
        
        if data and len(data) > 0 and "res" in data[0]:
            res_data = data[0]["res"][0].get("res", {})
            if res_data:
                latest_year = max(res_data.keys()) if res_data else None
                latest_value = res_data.get(latest_year) if latest_year else None
                return ind_name, {
                    "latest_year": latest_year,
                    "latest_value": latest_value,
                    "all_values": res_data,
                }
        return ind_name, None
    
    # Create tasks for all indicators
    tasks = [
        fetch_indicator(ind_id, ind_name)
        for ind_id, ind_name in SINOPSE_INDICATORS.items()
    ]
    
    # Execute all tasks
    results = await asyncio.gather(*tasks)
    
    # Build statistics dict
    for ind_name, value in results:
        if value:
            statistics[ind_name] = value
    
    return statistics


async def get_municipality_full_data(session: aiohttp.ClientSession, municipality_id: int) -> dict:
    """Get complete municipality data including location info and statistics."""
    # Get location data
    location_data = await get_municipality_by_id(session, municipality_id)
    
    if not location_data:
        return {"error": "Municipality not found", "municipality_id": municipality_id}
    
    # Get statistics
    statistics = await get_municipality_statistics(session, municipality_id)
    
    return {
        "municipality": location_data,
        "statistics": statistics,
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the IBGE skill.
    
    Functions:
    - search_municipalities: Search for municipalities by name
    - get_municipality: Get municipality details by ID
    - get_municipality_statistics: Get statistics for a municipality
    - get_municipality_full: Get complete data (location + statistics) for a municipality
    - get_state_municipalities: Get all municipalities for a state
    - get_states: Get all Brazilian states
    """
    function = params.get("function", "")
    
    connector = aiohttp.TCPConnector(limit=5)
    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        
        if function == "search_municipalities":
            query = params.get("query", "").strip()
            if not query:
                return {"error": "Missing required parameter: query"}
            
            results = await search_municipalities(session, query)
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "municipalities": results,
            }
        
        elif function == "get_municipality":
            municipality_id = params.get("municipality_id")
            if not municipality_id:
                return {"error": "Missing required parameter: municipality_id"}
            
            try:
                municipality_id = int(municipality_id)
            except (ValueError, TypeError):
                return {"error": "Invalid municipality_id: must be an integer"}
            
            result = await get_municipality_by_id(session, municipality_id)
            if not result:
                return {"error": "Municipality not found", "municipality_id": municipality_id}
            
            return {
                "success": True,
                "municipality": result,
            }
        
        elif function == "get_municipality_statistics":
            municipality_id = params.get("municipality_id")
            if not municipality_id:
                return {"error": "Missing required parameter: municipality_id"}
            
            try:
                municipality_id = int(municipality_id)
            except (ValueError, TypeError):
                return {"error": "Invalid municipality_id: must be an integer"}
            
            statistics = await get_municipality_statistics(session, municipality_id)
            return {
                "success": True,
                "municipality_id": municipality_id,
                "statistics": statistics,
            }
        
        elif function == "get_municipality_full":
            municipality_id = params.get("municipality_id")
            if not municipality_id:
                return {"error": "Missing required parameter: municipality_id"}
            
            try:
                municipality_id = int(municipality_id)
            except (ValueError, TypeError):
                return {"error": "Invalid municipality_id: must be an integer"}
            
            result = await get_municipality_full_data(session, municipality_id)
            if "error" in result:
                return result
            
            return {
                "success": True,
                "data": result,
            }
        
        elif function == "get_state_municipalities":
            state = params.get("state", "").strip()
            if not state:
                return {"error": "Missing required parameter: state"}
            
            municipalities = await get_municipalities_by_state(session, state)
            if not municipalities:
                return {"error": "State not found or no municipalities", "state": state}
            
            return {
                "success": True,
                "state": state.upper(),
                "count": len(municipalities),
                "municipalities": municipalities,
            }
        
        elif function == "get_states":
            states = await get_all_states(session)
            return {
                "success": True,
                "count": len(states),
                "states": states,
            }
        
        else:
            return {"error": f"Unknown function: {function}"}