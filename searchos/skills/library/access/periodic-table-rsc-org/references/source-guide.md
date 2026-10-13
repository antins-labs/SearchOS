# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# RSC Periodic Table Element Data Access Skill

This skill retrieves comprehensive element data from the Royal Society of Chemistry (RSC) Periodic Table website at `periodic-table.rsc.org`.

## Features

- **Complete Element Data**: Fetches all available data for any element including:
  - Basic properties (Group, Period, Block, Atomic number, Atomic mass, etc.)
  - Physical properties (Melting point, Boiling point, Density, State)
  - Discovery information (Date, Discoverers, Name origin)
  - Uses and applications
  - History
  - Atomic data (Atomic radius, Covalent radius, Electron affinity, Electronegativity, Ionisation energies)
  - Oxidation states
  - Isotopes (with mass, abundance, half-life, decay mode)

- **Flexible Search**: Search by element name, symbol, or atomic number

## Functions

### get_element

Fetch element data by atomic number.

**Parameters:**
- `atomic_number` (required): Integer 1-118
- `element_name` (optional): Element name (will be lowercased automatically)

**Example:**
```python
params = {
    "function": "get_element",
    "atomic_number": 109,
    "element_name": "meitnerium"  # optional
}
```

### search_element

Search for an element by name, symbol, or atomic number.

**Parameters:**
- `query` (required): Element name ("gold"), symbol ("Au"), or atomic number as string ("79")

**Example:**
```python
params = {
    "function": "search_element",
    "query": "Au"  # or "gold" or "79"
}
```

## Return Data Structure

```json
{
  "name": "Meitnerium",
  "symbol": "Mt",
  "url": "https://periodic-table.rsc.org/element/109/meitnerium",
  "atomic_number": 109,
  "properties": {
    "group": "9",
    "period": "7",
    "block": "d",
    "atomic_mass": "[278]",
    "state_at_20c": "Solid",
    "melting_point": "Unknown",
    "boiling_point": "Unknown",
    "density": "Unknown",
    "electron_configuration": "[Rn] 5f146d77s2",
    "cas_number": "54038-01-6",
    "key_isotopes": "276Mt"
  },
  "discovery": {
    "date": "1982",
    "discoverers": "Peter Armbruster, Gottfried Münzenberg and colleagues",
    "name_origin": "Meitnerium is named for the Austrian physicist Lise Meitner."
  },
  "uses": [
    "A highly radioactive metal, of which only a few atoms have ever been made.",
    "At present it is only used in research.",
    "Meitnerium has no known biological role."
  ],
  "history": [
    "There are 7 isotopes of meitnerium with mass numbers in the range 266 to 279..."
  ],
  "atomic_data": {
    "atomic_radius_non_bonded": "Unknown",
    "covalent_radius": "1.29",
    "electron_affinity": "Unknown",
    "electronegativity": "Unknown"
  },
  "oxidation_states": "Unknown",
  "isotopes": [
    {
      "isotope": "276Mt",
      "atomic_mass": "276.152",
      "half_life": "~ 0.7 s",
      "decay_mode": "α"
    }
  ]
}
```

## Supported Elements

All 118 elements from Hydrogen (1) to Oganesson (118) are supported.

## Data Source

Data is fetched from the Royal Society of Chemistry's Periodic Table:
https://periodic-table.rsc.org/

The RSC Periodic Table provides authoritative, peer-reviewed data on all chemical elements, including properties, history, uses, and more.
