# Google Pixel Device Specifications Skill

Extracts comprehensive hardware technical specifications for all Google Pixel phones from the official Google Support help article.

## Overview

This skill provides structured access to official Pixel device specifications including:

- **Display**: Size, resolution, technology (OLED/LTPO), refresh rate
- **Processor**: Google Tensor chip version, security coprocessor
- **Memory & Storage**: RAM capacity, storage options
- **Battery & Charging**: Battery life, fast charging specs, wireless charging
- **Camera**: Rear and front camera details, video capabilities
- **Dimensions & Weight**: Physical size and weight measurements
- **Connectivity**: 5G, Wi-Fi, Bluetooth, USB specifications
- **Operating System**: Android version at launch

## Supported Functions

### 1. `get_all_specs`

Get specifications for all devices with optional filtering.

**Parameters:**
- `device_name` (string): Filter by device name (e.g., "Pixel 9")
- `year` (integer): Filter by release year (e.g., 2024)
- `generation` (integer): Filter by Pixel generation (e.g., 9)
- `device_type` (string): Filter by type ("phone", "foldable", "a_series")
- `variant` (string): Filter by variant ("Pro XL", "Pro", "Standard", "a", "Fold")

**Example:**
```python
# Get all devices
execute({"function": "get_all_specs"})

# Get only 2024 devices
execute({"function": "get_all_specs", "year": 2024})

# Get Pixel 9 family
execute({"function": "get_all_specs", "generation": 9})

# Get foldable devices
execute({"function": "get_all_specs", "device_type": "foldable"})
```

### 2. `get_device_details`

Get detailed specifications for a specific device.

**Parameters:**
- `device_query` (required): Search query for device name
- `return_all_matches`: Return all matching devices instead of best match

**Example:**
```python
# Get Pixel 9 Pro specs
execute({"function": "get_device_details", "device_query": "Pixel 9 Pro"})

# Get Pixel Fold details
execute({"function": "get_device_details", "device_query": "Pixel Fold"})

# Get all Pixel 9 variants
execute({"function": "get_device_details", "device_query": "Pixel 9", "return_all_matches": True})
```

### 3. `compare_devices`

Compare specifications between multiple devices.

**Parameters:**
- `devices` (array): List of device names to compare

**Example:**
```python
# Compare Pixel 9 vs Pixel 8
execute({
    "function": "compare_devices",
    "devices": ["Pixel 9 phones", "Pixel 8 phones"]
})

# Compare three devices
execute({
    "function": "compare_devices",
    "devices": ["Pixel 9a", "Pixel 8a", "Pixel 7a"]
})
```

### 4. `get_spec_summary`

Get a summary of all devices with key specifications.

**Example:**
```python
execute({"function": "get_spec_summary"})
```

Returns a lightweight overview with display, processor, memory, and battery highlights.

### 5. `list_available_devices`

List all available Pixel devices in the database.

**Example:**
```python
execute({"function": "list_available_devices"})
```

Returns devices grouped by generation.

## Response Format

All successful responses include:
```json
{
    "success": true,
    // Function-specific data
}
```

Error responses:
```json
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE"
}
```

## Device Coverage

Currently includes specifications for:

- **Pixel 10 Series** (2025-2026): Pixel 10a, Pixel 10 Pro Fold, Pixel 10/Pro/Pro XL
- **Pixel 9 Series** (2024-2025): Pixel 9a, Pixel 9 Pro Fold, Pixel 9/Pro/Pro XL
- **Pixel 8 Series** (2023-2024): Pixel 8a, Pixel 8/Pro
- **Pixel Fold** (2023)
- **Pixel 7 Series** (2022-2023): Pixel 7a, Pixel 7/Pro
- **Pixel 6 Series** (2021-2022): Pixel 6a, Pixel 6/Pro

## Data Source

Data is fetched from Google's official support article:
- URL: `https://support.google.com/pixelphone/answer/7158570?hl=en`
- Cache duration: 1 hour
- Automatic parsing of HTML tables into structured JSON

## Notes

- **Variant detection**: Devices with multiple variants (Pro XL/Pro/Standard) are automatically identified from display specifications
- **Spec categorization**: Specs are organized into logical categories (display, battery, camera, etc.)
- **Fuzzy matching**: Device queries support partial name matching
- **Data freshness**: Results are cached for 1 hour to reduce load on Google's servers