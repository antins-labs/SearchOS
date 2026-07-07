# NPS IRMA DataStore Access Skill

This skill provides programmatic access to the National Park Service (NPS) Integrated Resource Management Applications (IRMA) DataStore, enabling retrieval of reference profiles, file listings, and tabular CSV data.

## Overview

The IRMA DataStore (https://irma.nps.gov) hosts scientific data, reports, and datasets related to U.S. national parks. This skill allows you to:

- Retrieve metadata for reference profiles (data packages, reports, etc.)
- List all files attached to a reference
- Download files including CSV data tables
- Parse CSV files into structured data with statistics

## Available Functions

### get_reference_profile

Retrieves core metadata for a reference profile.

**Parameters:**
- `reference_id` (required): The numeric reference ID (e.g., "2316680")

**Returns:**
- Title, description, DOI
- Content begin/end dates
- Contacts and authors
- Lifecycle status (Active, Inactive, etc.)
- Type (Data Package, Report, etc.)
- License information

**Example:**
```json
{
  "function": "get_reference_profile",
  "reference_id": "2316680"
}
```

### get_file_holdings

Lists all files attached to a reference profile.

**Parameters:**
- `reference_id` (required): The numeric reference ID

**Returns:**
- List of files with:
  - File ID (for downloading)
  - Filename
  - Description
  - File size
  - MIME type
  - Download URL
  - MD5 hash
  - Can download flag

**Example:**
```json
{
  "function": "get_file_holdings",
  "reference_id": "2316680"
}
```

### download_file

Downloads a specific file by its file ID.

**Parameters:**
- `file_id` (required): The numeric file ID (e.g., "753800")
- `max_size_mb` (optional): Maximum file size to download in MB (default: 50)

**Returns:**
- For text files (CSV, XML):
  - Full text content
  - Line count
- For binary files:
  - Base64-encoded content

**Example:**
```json
{
  "function": "download_file",
  "file_id": "753800"
}
```

### parse_csv_file

Downloads and parses a CSV file into structured data.

**Parameters:**
- `file_id` (required): The numeric file ID
- `max_rows` (optional): Maximum number of rows to return
- `preview_rows` (optional): Number of preview rows (default: 20)

**Returns:**
- Column names and count
- Total row count
- Data rows (as array of objects)
- Preview rows
- Summary statistics for numeric columns (min, max, mean, count)

**Example:**
```json
{
  "function": "parse_csv_file",
  "file_id": "753800",
  "preview_rows": 10
}
```

### get_full_profile

Retrieves complete reference profile with both metadata and file listings.

**Parameters:**
- `reference_id` (required): The numeric reference ID

**Returns:**
- Combined data from `get_reference_profile` and `get_file_holdings`
- Direct URL to the profile page

**Example:**
```json
{
  "function": "get_full_profile",
  "reference_id": "2316680"
}
```

## API Endpoints Used

This skill uses the following IRMA DataStore API endpoints:

- `/DataStore/Reference/GetProfileCoreModel/{referenceId}` - Profile metadata
- `/DataStore/Reference/GetProfilePermissionsModel/{referenceId}` - Access permissions
- `/DataStore/Reference/GetHoldings?referenceId={id}` - File listings
- `/DataStore/DownloadFile/{fileId}` - File downloads

## Use Cases

### Example 1: Discover Available Data

Get a reference profile and list all available files:

```json
// First call
{"function": "get_full_profile", "reference_id": "2316680"}

// Then download specific files of interest
{"function": "parse_csv_file", "file_id": "753800"}
```

### Example 2: Analyze Tabular Data

Parse a CSV file and get summary statistics:

```json
{"function": "parse_csv_file", "file_id": "753801", "preview_rows": 50}
```

The response includes columns, data rows, and statistics for numeric fields.

### Example 3: Large File Handling

For larger files, you can set size limits to avoid downloading excessively large data:

```json
{"function": "download_file", "file_id": "753801", "max_size_mb": 10}
```

## Data Types

The IRMA DataStore contains various types of references:

- **Data Packages**: Collections of related data files (CSV, XML metadata)
- **Reports**: Scientific reports and publications
- **Datasets**: Individual datasets with associated metadata
- **Publications**: Journal articles and other publications

## Error Handling

All functions return a consistent structure:

```json
{
  "success": true,
  "data": { ... }
}
```

On error:

```json
{
  "success": false,
  "error": "Error description"
}
```

Common errors:
- Missing required parameters
- Invalid reference or file ID
- File too large (exceeds max_size_mb)
- Non-CSV file passed to parse_csv_file

## Notes

- Reference IDs are numeric (e.g., 2316680)
- File IDs are also numeric (e.g., 753800)
- Most scientific data files are in CSV format
- Metadata files are often in XML format (EML standard)
- All data is publicly accessible (no authentication required)