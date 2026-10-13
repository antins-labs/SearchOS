"""
IBGE Municipal Data Access Skill

Fetches structured municipal data from IBGE (Instituto Brasileiro de Geografia e Estatística)
official APIs for Brazilian municipalities.

Data available:
- Municipality identification and geographic hierarchy
- Population data (Censo 2010, 2022)
- GDP and economic indicators
- District information
"""

import aiohttp
from typing import Any


API_BASE = "https://servicodados.ibge.gov.br/api/v1"
API_V3_BASE = "https://servicodados.ibge.gov.br/api/v3"

# Agregado IDs for statistics
AGREGADO_POPULACAO_CENSO_2022 = "4714"  # População residente, área, densidade
AGREGADO_PIB = "5938"  # Produto Interno Bruto


async def _fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> dict | list | None:
    """Fetch JSON from URL with error handling."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.json()
            return None
    except Exception:
        return None


async def _get_municipality_id(session: aiohttp.ClientSession, state: str, name: str) -> dict:
    """Find municipality ID by state abbreviation and name."""
    url = f"{API_BASE}/localidades/estados/{state.upper()}/municipios"
    municipios = await _fetch_json(session, url)
    
    if not municipios:
        return {"error": f"Could not fetch municipalities for state {state}", "success": False}
    
    # Find matching municipality (case-insensitive)
    matches = [m for m in municipios if m['nome'].lower() == name.lower()]
    
    if not matches:
        return {"error": f"Municipality '{name}' not found in state {state}", "success": False}
    
    muni = matches[0]
    return {
        "success": True,
        "id": muni['id'],
        "nome": muni['nome'],
        "microrregiao": muni['microrregiao']['nome'],
        "mesorregiao": muni['microrregiao']['mesorregiao']['nome'],
        "estado": muni['microrregiao']['mesorregiao']['UF']['sigla'],
        "estado_nome": muni['microrregiao']['mesorregiao']['UF']['nome'],
        "regiao": muni['microrregiao']['mesorregiao']['UF']['regiao']['nome'],
    }


async def _get_municipality_by_id(session: aiohttp.ClientSession, muni_id: int) -> dict | None:
    """Get municipality details by ID."""
    url = f"{API_BASE}/localidades/municipios/{muni_id}"
    return await _fetch_json(session, url)


async def _get_districts(session: aiohttp.ClientSession, muni_id: int) -> list:
    """Get districts for a municipality."""
    url = f"{API_BASE}/localidades/municipios/{muni_id}/distritos"
    return await _fetch_json(session, url) or []


async def _get_population_area(session: aiohttp.ClientSession, muni_id: int) -> dict:
    """Get population and area data from Censo 2022."""
    url = f"{API_V3_BASE}/agregados/{AGREGADO_POPULACAO_CENSO_2022}/periodos/all/variaveis?localidades=N6[{muni_id}]"
    data = await _fetch_json(session, url)
    
    result = {}
    if data:
        for item in data:
            var_name = item.get('variavel', '')
            unit = item.get('unidade', '')
            if item.get('resultados'):
                serie = item['resultados'][0]['series'][0]['serie']
                for year, value in serie.items():
                    result[var_name] = {
                        "valor": value,
                        "unidade": unit,
                        "ano": year
                    }
    return result


async def _get_gdp(session: aiohttp.ClientSession, muni_id: int, periods: str = "-1") -> dict:
    """Get GDP data for a municipality.
    
    Args:
        muni_id: Municipality ID
        periods: Period specification (e.g., "-1" for latest, "-5" for last 5 years, "all" for all)
    """
    url = f"{API_V3_BASE}/agregados/{AGREGADO_PIB}/periodos/{periods}/variaveis?localidades=N6[{muni_id}]"
    data = await _fetch_json(session, url, timeout=60)
    
    result = {}
    if data:
        for item in data:
            var_name = item.get('variavel', '')
            unit = item.get('unidade', '')
            if item.get('resultados'):
                serie = item['resultados'][0]['series'][0]['serie']
                result[var_name] = {
                    "unidade": unit,
                    "valores": serie  # Dict of year: value
                }
    return result


async def _list_states(session: aiohttp.ClientSession) -> list:
    """List all Brazilian states."""
    url = f"{API_BASE}/localidades/estados"
    estados = await _fetch_json(session, url)
    
    if not estados:
        return []
    
    return [
        {
            "id": e['id'],
            "sigla": e['sigla'],
            "nome": e['nome'],
            "regiao": e['regiao']['nome']
        }
        for e in sorted(estados, key=lambda x: x['sigla'])
    ]


async def _list_municipalities(session: aiohttp.ClientSession, state: str) -> list:
    """List all municipalities in a state."""
    url = f"{API_BASE}/localidades/estados/{state.upper()}/municipios"
    municipios = await _fetch_json(session, url)
    
    if not municipios:
        return []
    
    return [
        {
            "id": m['id'],
            "nome": m['nome'],
            "microrregiao": m['microrregiao']['nome'],
            "mesorregiao": m['microrregiao']['mesorregiao']['nome']
        }
        for m in sorted(municipios, key=lambda x: x['nome'])
    ]


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute IBGE municipal data queries.
    
    Functions:
        - get_municipality: Get municipality details by state abbreviation and name
        - get_by_id: Get municipality details by IBGE ID
        - get_districts: Get districts within a municipality
        - get_population_area: Get population and area data (Censo 2022)
        - get_gdp: Get GDP/economic data
        - get_stats: Get comprehensive statistics (population, area, GDP)
        - list_states: List all Brazilian states
        - list_municipalities: List municipalities in a state
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession() as session:
        if function == "get_municipality":
            state = params.get("state", "")
            name = params.get("name", "")
            
            if not state or not name:
                return {"error": "Both 'state' (abbreviation) and 'name' parameters required", "success": False}
            
            result = await _get_municipality_id(session, state, name)
            if not result.get("success"):
                return result
            
            muni_id = result["id"]
            
            # Get full details
            details = await _get_municipality_by_id(session, muni_id)
            
            return {
                "success": True,
                "municipio": {
                    "id": muni_id,
                    "nome": result["nome"],
                    "estado": result["estado"],
                    "estado_nome": result["estado_nome"],
                    "regiao": result["regiao"],
                    "microrregiao": result["microrregiao"],
                    "mesorregiao": result["mesorregiao"],
                    "regiao_imediata": details.get('regiao-imediata', {}).get('nome') if details else None,
                    "regiao_intermediaria": details.get('regiao-imediata', {}).get('regiao-intermediaria', {}).get('nome') if details else None,
                }
            }
        
        elif function == "get_by_id":
            muni_id = params.get("municipality_id")
            
            if not muni_id:
                return {"error": "'municipality_id' parameter required", "success": False}
            
            details = await _get_municipality_by_id(session, muni_id)
            
            if not details:
                return {"error": f"Municipality with ID {muni_id} not found", "success": False}
            
            return {
                "success": True,
                "municipio": {
                    "id": details['id'],
                    "nome": details['nome'],
                    "estado": details['microrregiao']['mesorregiao']['UF']['sigla'],
                    "estado_nome": details['microrregiao']['mesorregiao']['UF']['nome'],
                    "regiao": details['microrregiao']['mesorregiao']['UF']['regiao']['nome'],
                    "microrregiao": details['microrregiao']['nome'],
                    "mesorregiao": details['microrregiao']['mesorregiao']['nome'],
                    "regiao_imediata": details.get('regiao-imediata', {}).get('nome'),
                    "regiao_intermediaria": details.get('regiao-imediata', {}).get('regiao-intermediaria', {}).get('nome'),
                }
            }
        
        elif function == "get_districts":
            muni_id = params.get("municipality_id")
            
            if not muni_id:
                return {"error": "'municipality_id' parameter required", "success": False}
            
            districts = await _get_districts(session, muni_id)
            
            return {
                "success": True,
                "municipality_id": muni_id,
                "distritos": [
                    {
                        "id": d['id'],
                        "nome": d['nome']
                    }
                    for d in districts
                ]
            }
        
        elif function == "get_population_area":
            muni_id = params.get("municipality_id")
            
            if not muni_id:
                return {"error": "'municipality_id' parameter required", "success": False}
            
            data = await _get_population_area(session, muni_id)
            
            return {
                "success": True,
                "municipality_id": muni_id,
                "dados": data
            }
        
        elif function == "get_gdp":
            muni_id = params.get("municipality_id")
            periods = params.get("periods", "-1")  # Default to latest
            
            if not muni_id:
                return {"error": "'municipality_id' parameter required", "success": False}
            
            data = await _get_gdp(session, muni_id, periods)
            
            return {
                "success": True,
                "municipality_id": muni_id,
                "pib": data
            }
        
        elif function == "get_stats":
            state = params.get("state", "")
            name = params.get("name", "")
            muni_id = params.get("municipality_id")
            
            # Get municipality ID if not provided
            if not muni_id:
                if not state or not name:
                    return {"error": "Either 'municipality_id' or both 'state' and 'name' required", "success": False}
                
                muni_info = await _get_municipality_id(session, state, name)
                if not muni_info.get("success"):
                    return muni_info
                muni_id = muni_info["id"]
            
            # Get all stats
            details = await _get_municipality_by_id(session, muni_id)
            pop_area = await _get_population_area(session, muni_id)
            gdp = await _get_gdp(session, muni_id, "-1")
            districts = await _get_districts(session, muni_id)
            
            municipio_info = {}
            if details:
                municipio_info = {
                    "id": details['id'],
                    "nome": details['nome'],
                    "estado": details['microrregiao']['mesorregiao']['UF']['sigla'],
                    "estado_nome": details['microrregiao']['mesorregiao']['UF']['nome'],
                    "regiao": details['microrregiao']['mesorregiao']['UF']['regiao']['nome'],
                    "microrregiao": details['microrregiao']['nome'],
                    "mesorregiao": details['microrregiao']['mesorregiao']['nome'],
                }
            
            return {
                "success": True,
                "municipio": municipio_info,
                "populacao_area": pop_area,
                "pib": gdp,
                "distritos": [{"id": d['id'], "nome": d['nome']} for d in districts]
            }
        
        elif function == "list_states":
            estados = await _list_states(session)
            
            return {
                "success": True,
                "estados": estados,
                "total": len(estados)
            }
        
        elif function == "list_municipalities":
            state = params.get("state", "")
            
            if not state:
                return {"error": "'state' parameter (abbreviation) required", "success": False}
            
            municipios = await _list_municipalities(session, state)
            
            return {
                "success": True,
                "estado": state.upper(),
                "municipios": municipios,
                "total": len(municipios)
            }
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "success": False,
                "available_functions": [
                    "get_municipality",
                    "get_by_id",
                    "get_districts",
                    "get_population_area",
                    "get_gdp",
                    "get_stats",
                    "list_states",
                    "list_municipalities"
                ]
            }