# NanoReview Access Skill

Extract detailed specifications and benchmarks for chipsets (SoCs), smartphones, and CPUs from [nanoreview.net](https://nanoreview.net).

## Supported Functions

### `get_chipset`

Get specifications and benchmarks for mobile chipsets/SoCs.

**Parameters:**
- `slug` (required): The chipset identifier

**Example slug values:**
- `qualcomm-snapdragon-8-gen-4` - Snapdragon 8 Elite
- `qualcomm-snapdragon-820` - Snapdragon 820
- `apple-a17-pro` - Apple A17 Pro
- `mediatek-dimensity-9300` - Dimensity 9300

**Returns:**
- Specifications: CPU architecture, cores, frequency, cache, process node, GPU details, memory type/frequency, connectivity, and more
- Benchmarks: AnTuTu 11, GeekBench 6, 3DMark, PCMark scores
- User tests: Community-submitted benchmark results
- Smartphones: List of phones using this chipset with their scores

---

### `get_phone`

Get specifications and benchmarks for smartphones.

**Parameters:**
- `slug` (required): The phone identifier

**Example slug values:**
- `oneplus-13`
- `samsung-galaxy-s25-ultra`
- `iphone-15-pro-max`

**Returns:**
- Display specifications
- Design and build materials
- Performance metrics
- Memory configuration
- Benchmarks
- User-submitted test results

---

### `get_cpu`

Get specifications and benchmarks for desktop/laptop processors.

**Parameters:**
- `slug` (required): The CPU identifier

**Example slug values:**
- `intel-core-i9-14900k`
- `amd-ryzen-9-7950x`
- `intel-core-i5-14600k`

**Returns:**
- CPU specifications
- Cinebench, GeekBench, PassMark, Blender benchmarks
- Performance per watt metrics
- User-submitted test results

---

## Data Structure

### Chipset Response Example

```json
{
  "success": true,
  "url": "https://nanoreview.net/en/soc/qualcomm-snapdragon-8-gen-4",
  "title": "Qualcomm Snapdragon 8 Elite (Gen 4)",
  "content_type": "soc",
  "nanodata": {
    "lang": "en",
    "contentType": "soc",
    "id": 3455,
    "slug": "qualcomm-snapdragon-8-gen-4",
    "name": "Qualcomm Snapdragon 8 Elite (Gen 4)"
  },
  "data": {
    "specifications": {
      "CPU": {
        "Architecture": "2x 4.32 GHz – Oryon (Phoenix L) 6x 3.53 GHz – Oryon (Phoenix M)",
        "Cores": "8",
        "Frequency": "4320 MHz",
        "Instruction set": "ARMv9.2-A",
        "L1 cache": "192 KB",
        "L2 cache": "12 MB",
        "L3 cache": "8 MB",
        "Process": "3 nanometers",
        "TDP (Sustained Power Limit)": "8 W",
        "Manufacturing": "TSMC"
      },
      "Graphics": {
        "GPU name": "Adreno 830",
        "Architecture": "Adreno 800",
        "GPU frequency": "1100 MHz",
        "Pipelines": "3",
        "Shading units": "512",
        "Total shaders": "1536",
        "FLOPS": "3379.2 Gigaflops",
        "Vulkan version": "1.3",
        "OpenCL version": "3.0",
        "DirectX version": "12.1"
      },
      "Memory": {
        "Memory type": "LPDDR5X",
        "Memory frequency": "5300 MHz",
        "Bus": "4x 16 Bit",
        "Max bandwidth": "84.8 Gb/s",
        "Max size": "24 GB"
      },
      "Connectivity": {
        "Modem": "Snapdragon X80",
        "4G support": "LTE Cat. 24",
        "5G support": "Yes",
        "Download speed": "Up to 10000 Mbps",
        "Upload speed": "Up to 3500 Mbps",
        "Wi-Fi": "7",
        "Bluetooth": "6.0"
      },
      "Info": {
        "Announced": "October 2024",
        "Class": "Flagship",
        "Model number": "SM8750-AB"
      }
    },
    "benchmarks": {
      "AnTuTu 11": {
        "CPU": "899884",
        "GPU": "1112775",
        "Memory": "451444",
        "UX": "655205",
        "Total score": "3119308"
      },
      "GeekBench 6": {
        "Asset compression": "367.8 MB/sec",
        "HTML 5 Browser": "223.5 pages/sec",
        "HDR": "315.8 Mpixels/sec"
      },
      "3DMark": {
        "Score": "2386",
        "Graphics test": "18 FPS"
      }
    },
    "user_tests": [
      {
        "date": "2026-06-19, Sang",
        "benchmark": "AnTuTu",
        "result": "3007761"
      }
    ],
    "smartphones": [
      {
        "name": "Honor Win RT",
        "score": "3475149"
      }
    ]
  }
}
```

---

## Usage Examples

### Fetch Snapdragon 8 Elite Gen 4 specs

```python
result = await execute({
    "function": "get_chipset",
    "slug": "qualcomm-snapdragon-8-gen-4"
})

# Access CPU specs
cpu_specs = result["data"]["specifications"]["CPU"]
print(f"Cores: {cpu_specs['Cores']}")
print(f"Frequency: {cpu_specs['Frequency']}")

# Get AnTuTu score
antutu = result["data"]["benchmarks"]["AnTuTu 11"]
print(f"AnTuTu Total: {antutu['Total score']}")
```

### Compare two chipsets

```python
# Get both chipsets
sd8 Elite = await execute({"function": "get_chipset", "slug": "qualcomm-snapdragon-8-gen-4"})
sd820 = await execute({"function": "get_chipset", "slug": "qualcomm-snapdragon-820"})

# Compare scores
elite_score = int(sd8Elite["data"]["benchmarks"]["AnTuTu 11"]["Total score"])
sd820_score = int(sd820["data"]["benchmarks"]["AnTuTu 11"]["Total score"])

print(f"Snapdragon 8 Elite: {elite_score}")
print(f"Snapdragon 820: {sd820_score}")
print(f"Performance ratio: {elite_score / sd820_score:.2f}x")
```

### Get phone specifications

```python
phone = await execute({
    "function": "get_phone",
    "slug": "oneplus-13"
})

print(f"Device: {phone['title']}")
print(f"Benchmarks: {phone['data']['benchmarks']}")
```

---

## Notes

1. **Slug Format**: The slug is typically the lowercase name with hyphens instead of spaces (e.g., `qualcomm-snapdragon-8-gen-4`).

2. **Data Availability**: Not all chipsets/phones/CPU have the same benchmark data available. Some may have fewer sections.

3. **User Tests**: Community-submitted benchmarks are included in the `user_tests` array with date, benchmark type, and result.

4. **Real-time Data**: Benchmark scores can be updated as new tests are submitted by users.

5. **No API**: NanoReview doesn't provide a public API. This skill parses the HTML pages directly.

---

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Failed to fetch page",
  "url": "https://nanoreview.net/en/soc/invalid-slug"
}
```

Common errors:
- Missing required `function` parameter
- Unknown function name
- Missing `slug` parameter
- HTTP errors (404 for invalid slug, timeouts, etc.)