# SWCAAC Airport Production Statistics System

西南地区机场生产统计系统 (Southwest China Airport Production Statistics System)

## Overview

This skill retrieves airport production statistics from the Civil Aviation Administration of China - Southwest Regional Administration (中国民航局西南地区管理局). The system provides monthly statistical reports on airport operations across Southwest China.

## Data Available

The system provides comprehensive airport statistics including:

- **Passenger Throughput (旅客吞吐量)**: Number of passengers handled
- **Cargo Throughput (货邮吞吐量)**: Cargo volume in kilograms
- **Flight Operations (起降架次)**: Number of takeoffs and landings
- **Year-over-Year Growth Rates**: Comparison with same period in previous year

## Coverage

Statistics are available for airports in:
- **Sichuan Province (四川省)**: Chengdu/Tianfu, Chengdu/Shuangliu, Mianyang, Luzhou, Yibin, etc.
- **Guizhou Province (贵州省)**: Guiyang/Longdongbao, Zunyi, Xingyi, Tongren, etc.
- **Yunnan Province (云南省)**: Kunming/Changshui, Lijiang, Xishuangbanna, Dali, etc.
- **Tibet Autonomous Region (西藏自治区)**: Lhasa/Gonggar, Linzhi, Qamdo, etc.
- **Chongqing Municipality (重庆直辖市)**: Chongqing/Jiangbei, Wanzhou, Qianjiang, etc.

## Functions

### list_reports

List available monthly statistical reports.

```python
result = await execute({
    'function': 'list_reports'
})
```

Returns a list of reports with their IDs and periods (e.g., "1月", "1-3月", "1-6月", etc.).

### get_report_data

Retrieve detailed statistics from a specific report.

```python
result = await execute({
    'function': 'get_report_data',
    'report_id': '55798'  # Report ID from list_reports
})
```

Returns structured data including:
- `report_title`: Report period (e.g., "2024年1月")
- `publish_date`: Publication date
- `statistics`: Array of airport data with passenger, cargo, and flight statistics

### list_options

Get available filter options (years, areas, airports).

```python
result = await execute({
    'function': 'list_options'
})
```

Returns:
- `years`: Available years (1995-2026)
- `areas`: Region/province codes
- `airports`: Airport codes and names

## Example Output

```python
{
    'success': True,
    'report_title': '2024年1月 西南地区机场生产统计简报',
    'publish_date': '2024年02月',
    'statistics': [
        {
            'name': '西南管理局',
            'passengers': {'count': 20161474, 'growth_rate': '26.32'},
            'cargo': {'weight_kg': 169473990, 'growth_rate': '44.20'},
            'flights': {'total': 175790, 'growth_rate': '33.26', ...}
        },
        {
            'name': '成都/天府',
            'passengers': {'count': 4298025, 'growth_rate': '65.19'},
            'cargo': {'weight_kg': 27768533, 'growth_rate': '178.59'},
            ...
        },
        ...
    ]
}
```

## Notes

- Reports are typically published monthly
- Data includes year-over-year comparison percentages
- Regional totals (province-level) are shown along with individual airport data
- Historical data is available from 1995

## Source

- Host: https://info.swcaac.gov.cn/sctj/
- Organization: 中国民航局西南地区管理局 (Civil Aviation Administration of China - Southwest Regional Administration)