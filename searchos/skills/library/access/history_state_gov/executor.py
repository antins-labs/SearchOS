"""
History.State.Gov Access Skill

Provides access to the U.S. State Department Office of the Historian biographical
database. Supports retrieving person profiles, searching, and listing Secretaries of State.
"""

import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://history.state.gov"

# Default HTTP headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
}


async def _fetch(url: str, client: httpx.AsyncClient | None = None) -> dict:
    """Fetch a URL and return status info with HTML content."""
    should_close = False
    if client is None:
        client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            verify=True,
            timeout=30.0,
            follow_redirects=True,
        )
        should_close = True

    try:
        resp = await client.get(url)
        return {
            "status": resp.status_code,
            "html": resp.text,
            "url": str(resp.url),
        }
    finally:
        if should_close:
            await client.aclose()


def _parse_person_page(html: str, url: str) -> dict:
    """Parse a person biography page and extract structured data."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "slug": url.split("/")[-1],
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Extract title/h1
    h1 = soup.find("h1")
    if h1:
        full_title = h1.get_text(strip=True)
        data["full_title"] = full_title

        # Remove "Biographies of the Secretaries of State:" prefix if present
        name_part = re.sub(
            r"^Biographies of the Secretaries of State:\s*", "", full_title
        )

        # Extract name and years - patterns:
        # "Rex W. Tillerson (1952–)" - living person
        # "Thomas Jefferson (1743–1826)" - deceased person
        years_match = re.match(r"^(.+?)\s*\((\d{4})(?:–|-|—)?\s*(\d{4})?\s*\)?$", name_part)
        if years_match:
            data["name"] = years_match.group(1).strip()
            data["birth_year"] = years_match.group(2)
            if years_match.group(3):
                data["death_year"] = years_match.group(3)
        else:
            data["name"] = name_part.strip()

    # Extract sidebar panel data (contains position info)
    panel = soup.find("div", class_="hsg-panel", id="pocom-data")
    if panel:
        # Extract birth/death info from first paragraph
        born_p = panel.find("p")
        if born_p:
            born_spans = born_p.find_all("span")
            if len(born_spans) >= 1:
                born_text = born_spans[0].get_text(strip=True)
                if born_text:
                    data["birth_year"] = born_text
            if len(born_spans) >= 2:
                died_text = born_spans[1].get_text(strip=True)
                died_match = re.search(r"(\d{4})", died_text)
                if died_match:
                    data["death_year"] = died_match.group(1)

        # Find all position li elements (with IDs like "secr-1789-jeff")
        position_lis = panel.find_all("li", id=True)

        if position_lis:
            positions = []
            for li in position_lis:
                pos_data = {}

                # Get position title
                pos_link = li.find("a")
                if pos_link:
                    pos_data["title"] = pos_link.get_text(strip=True)
                    pos_data["position_href"] = pos_link.get("href", "")

                # Extract date fields from the li text
                li_text = li.get_text("\n", strip=True)

                # Various date field patterns
                date_fields = [
                    ("appointed", r"Appointed:\s*([A-Za-z]+\s+\d+,?\s+\d+)"),
                    ("entry_on_duty", r"Entry on Duty:\s*([A-Za-z]+\s+\d+,?\s+\d+)"),
                    (
                        "presentation_of_credentials",
                        r"Presentation of Credentials:\s*([A-Za-z]+\s+\d+,?\s+\d+)",
                    ),
                    (
                        "termination_of_appointment",
                        r"Termination of Appointment:\s*([A-Za-z]+\s+\d+,?\s+\d+)",
                    ),
                    (
                        "termination_of_mission",
                        r"Termination of Mission:\s*([A-Za-z]+\s+\d+,?\s+\d+|Left post[^.\n]*)",
                    ),
                ]

                for field_name, pattern in date_fields:
                    match = re.search(pattern, li_text)
                    if match:
                        pos_data[field_name] = match.group(1).strip()

                # Get any notes from nested ul/li
                nested_li = li.find("li")
                if nested_li:
                    note_text = nested_li.get_text(strip=True)
                    # Add as notes if not already captured
                    if note_text and "notes" not in pos_data:
                        pos_data["notes"] = note_text

                if pos_data:
                    positions.append(pos_data)

            if positions:
                data["positions"] = positions
                # Set primary position for convenience
                data["position"] = positions[0].get("title")

        # Extract state of residence and appointment type
        panel_body = panel.find("div", class_="hsg-panel-body")
        if panel_body:
            body_text = panel_body.get_text("\n", strip=True)

            # State of residence - extract before the position data
            state_match = re.search(
                r"State of Residence:\s*([A-Za-z\s]+?)(?:\n|Secretary|Minister|Ambassador|Appointed)",
                body_text,
            )
            if state_match:
                data["state_of_residence"] = state_match.group(1).strip()

            # Appointment type
            appt_types = [
                "Non-career appointee",
                "Career appointee",
                "Career Member",
                "Career Minister",
            ]
            for appt_type in appt_types:
                if appt_type in body_text:
                    data["appointment_type"] = appt_type
                    break

    # Extract introduction
    intro_h2 = soup.find("h2", string=re.compile("Introduction", re.I))
    if intro_h2:
        intro_p = intro_h2.find_next("p")
        if intro_p:
            data["introduction"] = intro_p.get_text(strip=True)

    # Extract sources
    sources_h2 = soup.find("h2", string=re.compile("Sources", re.I))
    if sources_h2:
        sources_p = sources_h2.find_next("p")
        if sources_p:
            data["sources"] = sources_p.get_text(strip=True)

    return data


def _parse_list_page(html: str, url: str) -> dict:
    """Parse a list of people page (like secretaries listing)."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Get page title
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Find person links - pattern matches lastname-firstname or similar
    people = []
    links = soup.find_all("a", href=re.compile(r"^/departmenthistory/people/[a-z]+-[a-z]"))

    seen = set()
    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Skip navigation/duplicate links and non-person pages
        if href in seen:
            continue
        if "principalofficers" in href or "chiefsofmission" in href:
            continue
        if "by-name" in href or "by-year" in href:
            continue

        # Skip if text looks like a navigation element
        if any(
            nav in text.lower()
            for nav in ["principal officers", "secretaries of", "listed by"]
        ):
            continue

        seen.add(href)

        people.append(
            {
                "name": text,
                "url": f"{BASE_URL}{href}",
                "slug": href.split("/")[-1],
            }
        )

    data["people"] = people
    data["count"] = len(people)

    return data


def _parse_alpha_page(html: str, url: str, letter: str) -> dict:
    """Parse an alphabetical listing page (e.g., by-name/a)."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "letter": letter,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Get page title
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Find person links - they have years in parentheses like "John Adams (1735–1826)"
    people = []
    links = soup.find_all("a", href=re.compile(r"^/departmenthistory/people/[a-z]+-[a-z]"))

    seen = set()
    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Skip if it's a navigation link
        if href in seen:
            continue
        if "principalofficers" in href or "chiefsofmission" in href:
            continue
        if "by-name" in href or "by-year" in href:
            continue

        # Check if this looks like a person entry (has year in title)
        if re.search(r"\(\d{4}", text) or "–)" in text:
            seen.add(href)
            people.append(
                {
                    "name": text,
                    "url": f"{BASE_URL}{href}",
                    "slug": href.split("/")[-1],
                }
            )

    data["people"] = people
    data["count"] = len(people)

    return data


def _parse_year_page(html: str, url: str, year: str) -> dict:
    """Parse a year listing page (e.g., by-year/2020)."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "year": year,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    # Get page title
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Find person links
    people = []
    links = soup.find_all("a", href=re.compile(r"^/departmenthistory/people/[a-z]+-[a-z]"))

    seen = set()
    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Skip if it's a navigation link
        if href in seen:
            continue
        if "principalofficers" in href or "chiefsofmission" in href:
            continue
        if "by-name" in href or "by-year" in href:
            continue

        # Check if this looks like a person entry
        if re.search(r"\(\d{4}", text) or "–)" in text or "?–)" in text:
            seen.add(href)
            people.append(
                {
                    "name": text,
                    "url": f"{BASE_URL}{href}",
                    "slug": href.split("/")[-1],
                }
            )

    data["people"] = people
    data["count"] = len(people)

    return data


def _parse_alpha_index(html: str, url: str) -> dict:
    """Parse the alphabetical index page and return letter links."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
        "type": "alphabetical_index",
    }

    # Get page title
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Find letter links (by-name/a, by-name/b, etc.)
    letters = []
    links = soup.find_all("a", href=re.compile(r"/departmenthistory/people/by-name/[a-z]$"))

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True).upper()
        if text and len(text) <= 3:  # Just the letter
            letters.append(
                {
                    "letter": text,
                    "url": f"{BASE_URL}{href}",
                }
            )

    data["letters"] = letters
    data["count"] = len(letters)
    data["description"] = "Use get_by_name_letter(letter='a') to get people for a specific letter"

    return data


def _parse_year_index(html: str, url: str) -> dict:
    """Parse the year index page and return year links."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "url": url,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
        "type": "year_index",
    }

    # Get page title
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    # Find year links (by-year/2020, etc.)
    years = []
    links = soup.find_all("a", href=re.compile(r"/departmenthistory/people/by-year/\d{4}$"))

    for link in links:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        if text.isdigit():
            years.append(
                {
                    "year": text,
                    "url": f"{BASE_URL}{href}",
                }
            )

    # Sort years
    years.sort(key=lambda x: int(x["year"]))

    data["years"] = years
    data["count"] = len(years)
    data["year_range"] = f"{years[0]['year']}-{years[-1]['year']}" if years else None
    data["description"] = "Use get_by_year(year=2020) to get people for a specific year"

    return data


def _parse_search_results(html: str, query: str) -> dict:
    """Parse search results page."""
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "query": query,
        "success": True,
        "scraped_at": datetime.utcnow().isoformat(),
    }

    results = []

    # Find main content
    main = soup.find("main") or soup.find("div", class_=re.compile(r"main|content"))
    if main:
        # Look for h3 headings with links - these are search result titles
        headings = main.find_all(["h3", "h4"])
        for heading in headings:
            link = heading.find("a")
            if link:
                href = link.get("href", "")
                title = link.get_text(strip=True)

                # Filter for person-related results
                if "/departmenthistory/people/" in href:
                    results.append(
                        {
                            "title": title,
                            "url": f"{BASE_URL}{href}",
                            "slug": href.split("/")[-1],
                            "type": "person",
                        }
                    )
                elif href and not href.startswith("#"):
                    # Include other results as well
                    results.append(
                        {
                            "title": title,
                            "url": f"{BASE_URL}{href}",
                            "type": "other",
                        }
                    )

    data["results"] = results
    data["count"] = len(results)

    return data


async def get_person(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get biography details for a specific person.

    Parameters:
        slug: The person's URL slug (e.g., 'jefferson-thomas', 'tillerson-rex-w')
        url: Full URL to the person page (alternative to slug)

    Returns:
        Dictionary with person details including name, birth/death years,
        positions held, introduction, and sources.
    """
    slug = params.get("slug")
    url = params.get("url")

    if not slug and not url:
        return {"error": "Either 'slug' or 'url' parameter is required", "success": False}

    if url:
        slug = url.split("/")[-1]
    else:
        url = f"{BASE_URL}/departmenthistory/people/{slug}"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching person page",
            "url": url,
            "success": False,
        }

    data = _parse_person_page(result["html"], url)
    return data


async def search_people(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for people by name.

    Parameters:
        query: Search query (person's name or partial name)

    Returns:
        Dictionary with search results including person names and URLs.
    """
    query = params.get("query", "").strip()

    if not query:
        return {"error": "'query' parameter is required", "success": False}

    # URL encode the query
    encoded_query = quote(query)
    url = f"{BASE_URL}/search?q={encoded_query}"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching search results",
            "url": url,
            "success": False,
        }

    data = _parse_search_results(result["html"], query)
    return data


async def list_secretaries(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all U.S. Secretaries of State.

    Parameters:
        None

    Returns:
        Dictionary with list of all Secretaries of State including names and URLs.
    """
    url = f"{BASE_URL}/departmenthistory/people/secretaries"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching secretaries list",
            "url": url,
            "success": False,
        }

    data = _parse_list_page(result["html"], url)
    data["description"] = "List of all U.S. Secretaries of State"
    return data


async def list_by_name(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List alphabetical index for Principal Officers and Chiefs of Mission.
    Use get_by_name_letter() to get people for a specific letter.

    Parameters:
        None

    Returns:
        Dictionary with available letter indices.
    """
    url = f"{BASE_URL}/departmenthistory/people/by-name"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching alphabetical index",
            "url": url,
            "success": False,
        }

    data = _parse_alpha_index(result["html"], url)
    return data


async def get_by_name_letter(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get people listed under a specific letter of the alphabet.

    Parameters:
        letter: Single letter (a-z) to retrieve people for

    Returns:
        Dictionary with list of people whose names start with the specified letter.
    """
    letter = params.get("letter", "").strip().lower()

    if not letter or len(letter) != 1 or not letter.isalpha():
        return {"error": "'letter' parameter must be a single letter (a-z)", "success": False}

    url = f"{BASE_URL}/departmenthistory/people/by-name/{letter}"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching letter page",
            "url": url,
            "success": False,
        }

    data = _parse_alpha_page(result["html"], url, letter)
    return data


async def list_by_year(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List year index for Principal Officers and Chiefs of Mission.
    Use get_by_year() to get people for a specific year.

    Parameters:
        None

    Returns:
        Dictionary with available year indices.
    """
    url = f"{BASE_URL}/departmenthistory/people/by-year"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching year index",
            "url": url,
            "success": False,
        }

    data = _parse_year_index(result["html"], url)
    return data


async def get_by_year(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get people appointed in a specific year.

    Parameters:
        year: Four-digit year (e.g., 2020, 1789)

    Returns:
        Dictionary with list of people appointed in the specified year.
    """
    year = params.get("year")

    if not year:
        return {"error": "'year' parameter is required", "success": False}

    year_str = str(year)
    if not year_str.isdigit() or len(year_str) != 4:
        return {"error": "'year' parameter must be a four-digit year", "success": False}

    url = f"{BASE_URL}/departmenthistory/people/by-year/{year_str}"

    result = await _fetch(url)

    if result["status"] != 200:
        return {
            "error": f"HTTP {result['status']} error fetching year page",
            "url": url,
            "success": False,
        }

    data = _parse_year_page(result["html"], url, year_str)
    return data


# Function registry
FUNCTIONS = {
    "get_person": {
        "func": get_person,
        "description": "Get biography details for a specific person by slug or URL",
        "params": {
            "slug": "Person's URL slug (e.g., 'jefferson-thomas', 'tillerson-rex-w')",
            "url": "Full URL to person page (alternative to slug)",
        },
    },
    "search_people": {
        "func": search_people,
        "description": "Search for people by name",
        "params": {
            "query": "Search query (person's name or partial name)",
        },
    },
    "list_secretaries": {
        "func": list_secretaries,
        "description": "List all U.S. Secretaries of State",
        "params": {},
    },
    "list_by_name": {
        "func": list_by_name,
        "description": "List alphabetical index (returns available letters)",
        "params": {},
    },
    "get_by_name_letter": {
        "func": get_by_name_letter,
        "description": "Get people by first letter of last name",
        "params": {
            "letter": "Single letter (a-z)",
        },
    },
    "list_by_year": {
        "func": list_by_year,
        "description": "List year index (returns available years)",
        "params": {},
    },
    "get_by_year": {
        "func": get_by_year,
        "description": "Get people by appointment year",
        "params": {
            "year": "Four-digit year (e.g., 2020)",
        },
    },
}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a function from the History.State.Gov skill.

    Parameters:
        function: Name of the function to execute (required when multiple functions available)
        Other parameters depend on the specific function being called.

    Returns:
        Dictionary with results or error information.
    """
    func_name = params.get("function")

    if not func_name:
        return {
            "error": "'function' parameter is required. Available functions: "
            + ", ".join(FUNCTIONS.keys()),
            "success": False,
        }

    if func_name not in FUNCTIONS:
        return {
            "error": f"Unknown function '{func_name}'. Available functions: "
            + ", ".join(FUNCTIONS.keys()),
            "success": False,
        }

    func_info = FUNCTIONS[func_name]
    return await func_info["func"](params, ctx)