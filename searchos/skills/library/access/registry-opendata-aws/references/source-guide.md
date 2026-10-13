# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# AWS Open Data Registry Access Skill

This skill fetches structured dataset metadata from the AWS Open Data Registry 
(registry.opendata.aws), providing easy access to information about publicly 
available datasets hosted on AWS.

## Available Functions

### get_dataset

Fetch detailed metadata for a specific dataset.

**Parameters:**
- `dataset_path` (required): The dataset identifier or path. Accepts multiple formats:
  - Short name: `nasa-nasa-ssh`
  - Path format: `/nasa-nasa-ssh/`
  - Full URL: `https://registry.opendata.aws/nasa-nasa-ssh/`

**Returns:**
- `success`: Boolean indicating successful fetch
- `title`: Dataset title
- `name`: Dataset name from JSON-LD metadata
- `description`: Full dataset description
- `license`: License information
- `source_organization`: Data provider
- `resources`: Array of AWS resources including:
  - `description`: Resource description
  - `type`: Resource type (e.g., "S3 Bucket", "SNS Topic")
  - `arn`: AWS Resource Name
  - `region`: AWS region
- `resource_count`: Number of resources
- `url`: Final URL after following any redirects

**Example:**
```json
{
  "function": "get_dataset",
  "dataset_path": "nasa-nasa-ssh"
}
```

### list_datasets

List available datasets from the registry's RSS feed.

**Parameters:**
- `limit` (optional): Maximum number of datasets to return (default: 50)

**Returns:**
- `success`: Boolean
- `count`: Number of datasets returned
- `datasets`: Array of datasets with:
  - `title`: Dataset title
  - `path`: Dataset path for use with get_dataset
  - `url`: Full URL to dataset page
  - `description`: Brief description

**Example:**
```json
{
  "function": "list_datasets",
  "limit": 20
}
```

## Use Cases

- Discover open datasets available on AWS
- Get S3 bucket ARNs for direct data access
- Find dataset licensing and attribution requirements
- Identify data providers and source organizations
- Browse available datasets by topic

## Data Sources

This skill extracts data from:
1. **JSON-LD structured data** embedded in dataset pages
2. **Resource listings** from the HTML page structure
3. **RSS feed** for dataset discovery

## Notes

- Some datasets may redirect to new URLs (handled automatically)
- Resource types include S3 buckets, SNS topics, and other AWS services
- Controlled access resources are noted in the resource type
- ARNs can be used directly with AWS CLI or SDKs for data access
