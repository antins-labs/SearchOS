# TechPowerUp GPU Specs Access Skill

Extract GPU specifications from [TechPowerUp's GPU Database](https://www.techpowerup.com/gpu-specs/), the industry-standard resource for GPU technical specifications.

## Overview

This skill extracts key GPU specifications from TechPowerUp's extensive GPU database. It retrieves data including architecture, clock speeds, core counts (shaders/stream processors, TMUs, ROPs), memory configuration, and product images.

### Important Notes

TechPowerUp employs bot protection (a custom JavaScript-based firewall) that returns a challenge page instead of the full HTML content when automated access is detected. However, the Open Graph metadata containing essential GPU specs remains accessible in the page source, making reliable data extraction possible.

**What's Available:**
- GPU name and architecture
- GPU clock speeds
- Core counts (Shaders/CUDA cores/Stream processors)
- Texture Mapping Units (TMUs)
- Render Output Units (ROPs)
- Memory size, type, and clock speed
- Memory bus width
- Product image URL

**What's Not Available:**
- Detailed power consumption data
- Release date and pricing
- Full benchmark comparisons
- DLSS/FPS performance tables
- Detailed board design specs

## Functions

### fetch_gpu

Fetch specifications for a single GPU by its TechPowerUp URL.

**Parameters:**
- `url` (required): TechPowerUp GPU specs URL

**Example:**
```python
result = await execute({
    'function': 'fetch_gpu',
    'url': 'https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xtx.c3941'
})
```

**Returns:**
```json
{
  "success": true,
  "gpu_name": "AMD Radeon RX 7900 XTX",
  "gpu_id": "3941",
  "architecture": "AMD Navi 31",
  "gpu_clock": "2498 MHz",
  "cores": "6144 Cores",
  "cores_count": 6144,
  "tmus": "384 TMUs",
  "tmus_count": 384,
  "rops": "192 ROPs",
  "rops_count": 192,
  "memory": "24576 MB GDDR6",
  "memory_size_mb": 24576,
  "memory_type": "GDDR6",
  "memory_clock": "2500 MHz",
  "bus_width": "384 bit",
  "bus_width_bits": 384,
  "image_url": "https://www.techpowerup.com/gpu-specs/images-new/c/3941-front-thumb.jpg",
  "canonical_url": "https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xtx.c3941",
  "firewall_note": "Data extracted from metadata; full page behind bot protection"
}
```

### fetch_multiple

Fetch specifications for multiple GPUs concurrently.

**Parameters:**
- `urls` (required): List of TechPowerUp GPU specs URLs

**Example:**
```python
result = await execute({
    'function': 'fetch_multiple',
    'urls': [
        'https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xtx.c3941',
        'https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xt.c3942'
    ]
})
```

**Returns:**
```json
{
  "success": true,
  "total_count": 2,
  "successful_count": 2,
  "failed_count": 0,
  "results": [
    {"success": true, "gpu_name": "AMD Radeon RX 7900 XTX", ...},
    {"success": true, "gpu_name": "AMD Radeon RX 7900 XT", ...}
  ]
}
```

### search_by_id

Fetch GPU specifications by TechPowerUp's internal GPU ID.

**Parameters:**
- `gpu_id` (required): Numeric GPU ID (as string)

**Example:**
```python
result = await execute({
    'function': 'search_by_id',
    'gpu_id': '3941'
})
```

## Data Extraction Details

The skill extracts data from Open Graph meta tags included in the page HTML:

| Meta Tag | Content |
|----------|---------|
| `og:title` | GPU name with " Specs" suffix |
| `og:description` | Comma-separated spec values |
| `og:url` | Canonical GPU specs URL |
| `og:image` | Product thumbnail image |

The `og:description` field follows this format:
```
"Architecture, GPU Clock, Cores, TMUs, ROPs, Memory, Memory Clock, Bus Width"
```

Example:
```
"AMD Navi 31, 2498 MHz, 6144 Cores, 384 TMUs, 192 ROPs, 24576 MB GDDR6, 2500 MHz, 384 bit"
```

## Finding GPU IDs

GPU IDs can be found in the TechPowerUp URL pattern:
- URL format: `https://www.techpowerup.com/gpu-specs/<gpu-name>.c<id>`
- Example: `https://www.techpowerup.com/gpu-specs/radeon-rx-7900-xtx.c3941` → ID is `3941`

Note: The URL slug (gpu name) is not required - the server uses only the numeric ID:
- `https://www.techpowerup.com/gpu-specs/gpu.c3941` works the same
- The canonical URL in the response always uses the correct GPU name

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Description of what went wrong",
  "url": "Original URL (if applicable)"
}
```

Common errors:
- Missing required parameter
- Invalid URL format
- No valid GPU data found (invalid GPU ID)
- HTTP/network errors

## Known Limitations

1. **Bot Protection**: The site blocks automated browser access, but metadata extraction works reliably
2. **Limited Data**: Only data available in Open Graph metadata is extracted
3. **Thumbnails**: Image URLs point to thumbnail-size images
4. **No Search**: Cannot search the database (search endpoint returns 410)

## Dependencies

- `httpx` - HTTP client for requests
- `beautifulsoup4` - HTML parsing for meta tag extraction
- `asyncio` - Async support for concurrent requests