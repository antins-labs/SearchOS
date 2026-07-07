# NVIDIA GeForce Graphics Card Specifications Skill

This skill extracts detailed GPU specification data from NVIDIA's official GeForce product
specification pages at www.nvidia.com.

## Overview

NVIDIA maintains comprehensive specification pages for GeForce graphics cards. This skill
scrapes the structured configuration tables embedded in these pages, extracting data such as:

- **GPU Engine Specs**: CUDA cores, base/boost clock speeds
- **Memory Specs**: Memory clock, capacity, interface type, bandwidth
- **Technology Support**: DirectX, OpenGL, VR readiness, etc.
- **Display Support**: Max resolution, connectors, multi-monitor support
- **Dimensions**: Length, height, width
- **Thermal and Power**: Max temperature, power draw, system requirements

## Available Functions

### fetch_specs

Fetches complete specification data for a GPU.

**Parameters:**
- `gpu_slug` (required): GPU identifier from the URL, e.g., `geforce-gtx-750-ti` or `gt-1030`
- `timeout` (optional): Request timeout in seconds (default: 30)

**Returns:**
```json
{
  "status": "success",
  "gpu_name": "GTX 750 Ti",
  "sections": [
    {
      "title": "GTX 750 Ti GPU Engine Specs:",
      "specs": [
        {"label": "CUDA Cores", "value": "640"},
        {"label": "Base Clock (MHz)", "value": "1020"},
        {"label": "Boost Clock (MHz)", "value": "1085"}
      ]
    },
    {
      "title": "GTX 750 Ti Memory Specs:",
      "specs": [
        {"label": "Memory Clock", "value": "5.4 Gbps"},
        {"label": "Standard Memory Config", "value": "2048 MB"},
        {"label": "Memory Interface", "value": "GDDR5"},
        {"label": "Memory Interface Width", "value": "128-bit"},
        {"label": "Memory Bandwidth (GB/sec)", "value": "86.4"}
      ]
    }
  ],
  "raw_specs": {
    "cuda_cores": "640",
    "base_clock_mhz": "1020",
    "boost_clock_mhz": "1085"
  },
  "url": "https://www.nvidia.com/en-us/geforce/graphics-cards/geforce-gtx-750-ti/specifications/"
}
```

### list_key_specs

Extracts the most important GPU specifications in a simplified format.

**Parameters:**
- `gpu_slug` (required): GPU identifier
- `timeout` (optional): Request timeout in seconds (default: 30)

**Returns:**
```json
{
  "status": "success",
  "gpu_name": "GTX 750 Ti",
  "key_specs": {
    "gpu_name": "GTX 750 Ti",
    "cuda_cores": "640",
    "base_clock_mhz": "1020",
    "boost_clock_mhz": "1085",
    "memory_config": "2048 MB",
    "memory_interface": "GDDR5",
    "memory_interface_width": "128-bit",
    "memory_bandwidth_gbps": "86.4",
    "power_w": "60 W",
    "directx": "12 API",
    "opengl": "4.4",
    "bus_support": "PCI Express 3.0",
    "length": "5.7 inches",
    "height": "4.376 inches",
    "min_system_power_w": "300 W"
  },
  "url": "..."
}
```

### search_by_url

Fetches specification data directly from a full NVIDIA specifications page URL.

**Parameters:**
- `url` (required): Complete URL to a NVIDIA GPU specifications page
- `timeout` (optional): Request timeout in seconds (default: 30)

## GPU Slug Examples

The `gpu_slug` parameter should match the URL path segment:

| Full URL Path | gpu_slug |
|--------------|----------|
| `.../geforce-gtx-750-ti/specifications/` | `geforce-gtx-750-ti` |
| `.../gt-1030/specifications/` | `gt-1030` |
| `.../geforce-gtx-1080/specifications/` | `geforce-gtx-1080` |

## Dual-Variant GPUs

Some GPUs (like GT 1030) have multiple variants with different specifications. In these
cases, the skill captures both values:

```json
{
  "label": "Boost Clock (MHz)",
  "value_primary": "1379",
  "value_secondary": "1468",
  "dual_variant": true
}
```

Key specs for dual-variant GPUs show both values:
```json
{
  "boost_clock_mhz": {
    "primary": "1379",
    "secondary": "1468"
  },
  "power_w": {
    "primary": "20 W",
    "secondary": "30 W"
  }
}
```

## Example Usage

```python
# Fetch full specifications
result = await execute({
    'function': 'fetch_specs',
    'gpu_slug': 'geforce-gtx-750-ti'
})

# Get key specs summary
result = await execute({
    'function': 'list_key_specs',
    'gpu_slug': 'gt-1030'
})

# Use direct URL
result = await execute({
    'function': 'search_by_url',
    'url': 'https://www.nvidia.com/en-us/geforce/graphics-cards/gt-1030/specifications/'
})
```

## Notes

- The specification data is embedded directly in the HTML response (no JavaScript rendering required)
- Data is extracted from NVIDIA's proprietary `coloredTable` structure
- All specifications are provided as strings; numeric conversion should be done by the caller
- Some older or very new GPU models may not have specification pages available
- The skill uses aiohttp for efficient async HTTP requests