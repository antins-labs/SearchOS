"""
SearchOS Access Skill for opendata.mofcom.gov.cn
Ministry of Commerce of China Open Data Portal

This skill provides access to China's Ministry of Commerce open data portal,
which hosts datasets including trade statistics, enterprise rankings, and policy documents.
"""

import asyncio
import re
from typing import Any, Optional
from bs4 import BeautifulSoup

# Use playwright for fetching due to SSL compatibility issues with the site
from playwright.async_api import async_playwright, Browser, Page


async def fetch_page(url: str, timeout: int = 30000) -> str:
    """Fetch a page using Playwright browser"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until='networkidle', timeout=timeout)
            html = await page.content()
            return html
        finally:
            await browser.close()


def parse_detail_page(html: str, dataset_id: str) -> dict:
    """Parse a dataset detail page to extract metadata and download files"""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        'id': dataset_id,
        'title': None,
        'abstract': None,
        'metadata': {},
        'download_files': [],
        'file_ids': [],
        'download_count': None,
        'api_call_count': None,
    }
    
    # Get text content
    text = soup.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # Build a single text block for regex matching
    text_content = ' '.join(lines)
    
    # Extract title - appears after "数据详情"
    for i, line in enumerate(lines):
        if '数据详情' in line and '首页' in line:
            if i + 1 < len(lines):
                result['title'] = lines[i + 1]
                break
    
    # Extract metadata using regex patterns
    # The page has concatenated labels and values
    
    # Data summary (数据摘要)
    match = re.search(r'数据摘要([^主]+?)(?=主题名称|$)', text_content)
    if match:
        val = match.group(1).strip()
        result['abstract'] = val
        result['metadata']['数据摘要'] = val
    
    # Subject name (主题名称) - value can contain Chinese characters and numbers
    match = re.search(r'主题名称([^\s\.]+)', text_content)
    if match:
        val = match.group(1).strip()
        if not result['title']:
            result['title'] = val
        result['metadata']['主题名称'] = val
    
    # Update frequency (更新频率)
    match = re.search(r'更新频率([^\s]+?)(?=数据提供方|$)', text_content)
    if match:
        result['metadata']['更新频率'] = match.group(1).strip()
    
    # Data provider (数据提供方)
    match = re.search(r'数据提供方([^\s]+?)(?=最后更新时间|$)', text_content)
    if match:
        result['metadata']['数据提供方'] = match.group(1).strip()
    
    # Last update time (最后更新时间) - datetime format
    match = re.search(r'最后更新时间\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', text_content)
    if match:
        result['metadata']['最后更新时间'] = match.group(1).strip()
    
    # Open attribute (开放属性)
    match = re.search(r'开放属性([^\s]+?)(?=数据主题|$)', text_content)
    if match:
        result['metadata']['开放属性'] = match.group(1).strip()
    
    # Data theme (数据主题)
    match = re.search(r'数据主题([^\s]+?)(?=数据类型|$)', text_content)
    if match:
        result['metadata']['数据主题'] = match.group(1).strip()
    
    # Data type (数据类型)
    match = re.search(r'数据类型([^\s]+?)(?=数据格式|$)', text_content)
    if match:
        result['metadata']['数据类型'] = match.group(1).strip()
    
    # Data format (数据格式) - can have spaces, ends before 下载量
    match = re.search(r'数据格式\s*(HTML|XLSX|CSV|PDF|WORD|EXCEL|XML|API)(?:\s*(HTML|XLSX|CSV|PDF|WORD|EXCEL|XML|API))*', text_content)
    if match:
        result['metadata']['数据格式'] = match.group(0).replace('数据格式', '').strip()
    
    # Alternative: capture everything between 数据格式 and 下载量
    if '数据格式' not in result['metadata']:
        match = re.search(r'数据格式([^下]+?)(?=下载量|$)', text_content)
        if match:
            result['metadata']['数据格式'] = match.group(1).strip()
    
    # Download count (下载量/调用量)
    match = re.search(r'下载量/调用量\s*(\d+)\s*/\s*(\d+)', text_content)
    if match:
        result['download_count'] = match.group(1).strip()
        result['api_call_count'] = match.group(2).strip()
        result['metadata']['下载量'] = result['download_count']
        result['metadata']['调用量'] = result['api_call_count']
    
    # Extract hidden inputs
    for inp in soup.find_all('input', type='hidden'):
        name = inp.get('name', '') or inp.get('id', '')
        value = inp.get('value', '')
        if name and value:
            result['metadata'][f'hidden_{name}'] = value
    
    # Dataset ID from hidden field
    if 'hidden_cde' in result['metadata']:
        result['id'] = result['metadata']['hidden_cde']
    
    # Extract download files from onclick handlers
    for link in soup.find_all('a', onclick=True):
        onclick = link.get('onclick', '')
        if 'isLogged' in onclick:
            text_content = link.get_text(strip=True)
            match = re.search(r"isLogged\('([^']+)','([^']+)'", onclick)
            if match:
                file_id = match.group(1)
                download_path = match.group(2)
                result['download_files'].append({
                    'name': text_content,
                    'id': file_id,
                    'path': download_path,
                    'url': f"https://opendata.mofcom.gov.cn{download_path}",
                    'requires_login': True
                })
    
    # Extract file IDs from checkboxes
    for cb in soup.find_all('input', type='checkbox'):
        cb_id = cb.get('id', '')
        if cb_id and cb_id not in ['checkAll', 'selectAll']:
            result['file_ids'].append(cb_id)
    
    return result


def parse_list_page(html: str) -> list:
    """Parse a dataset listing page to extract dataset summaries"""
    soup = BeautifulSoup(html, 'html.parser')
    datasets = []
    
    # Get text content
    text = soup.get_text()
    
    # Get total count
    count_match = re.search(r'共\s*(\d+)\s*个数据目录', text)
    total_count = int(count_match.group(1)) if count_match else 0
    
    # Find all dataset links
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if '/front/data/detail?id=' in href:
            title = link.get_text(strip=True)
            dataset_id = href.split('id=')[-1] if 'id=' in href else ''
            
            # Filter out navigation links
            if title and len(title) > 5 and '首页' not in title and '数据详情' not in title:
                datasets.append({
                    'id': dataset_id,
                    'title': title,
                    'url': f"https://opendata.mofcom.gov.cn{href}",
                })
    
    # Remove duplicates based on ID
    seen = set()
    unique_datasets = []
    for ds in datasets:
        if ds['id'] and ds['id'] not in seen:
            seen.add(ds['id'])
            unique_datasets.append(ds)
    
    return unique_datasets


async def get_dataset_detail(dataset_id: str) -> dict:
    """Fetch detailed information for a specific dataset"""
    url = f"https://opendata.mofcom.gov.cn/front/data/detail?id={dataset_id}"
    
    try:
        html = await fetch_page(url)
        result = parse_detail_page(html, dataset_id)
        result['url'] = url
        return result
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to fetch dataset detail: {str(e)}",
            'id': dataset_id,
            'url': url
        }


async def list_datasets() -> dict:
    """List all available datasets from the portal"""
    url = "https://opendata.mofcom.gov.cn/front/data"
    
    try:
        html = await fetch_page(url)
        datasets = parse_list_page(html)
        
        # Also extract pagination info from the page
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
        
        # Find "共 X 个数据目录" pattern
        count_match = re.search(r'共\s*(\d+)\s*个数据目录', text)
        total_count = int(count_match.group(1)) if count_match else len(datasets)
        
        return {
            'success': True,
            'total_datasets': total_count,
            'returned_count': len(datasets),
            'datasets': datasets,
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to list datasets: {str(e)}",
            'url': url
        }


async def get_download_urls(dataset_id: str) -> dict:
    """Get download URLs for a dataset's files"""
    result = await get_dataset_detail(dataset_id)
    
    if result.get('success') == False:
        return result
    
    return {
        'success': True,
        'id': dataset_id,
        'title': result.get('title'),
        'download_files': result.get('download_files', []),
        'note': 'Downloads require login. Visit the URLs with an authenticated session at https://user.mofcom.gov.cn/login'
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill
    
    Available functions:
    - list_datasets: List all datasets from the portal
    - get_dataset: Get detailed info about a specific dataset
    - get_download_urls: Get download URLs for a dataset's files
    """
    function = params.get('function', '')
    
    if function == 'list_datasets':
        return await list_datasets()
    
    elif function == 'get_dataset':
        dataset_id = params.get('dataset_id')
        if not dataset_id:
            return {
                'success': False,
                'error': 'dataset_id parameter is required'
            }
        result = await get_dataset_detail(dataset_id)
        if 'success' not in result:
            result['success'] = 'error' not in result
        return result
    
    elif function == 'get_download_urls':
        dataset_id = params.get('dataset_id')
        if not dataset_id:
            return {
                'success': False,
                'error': 'dataset_id parameter is required'
            }
        return await get_download_urls(dataset_id)
    
    else:
        return {
            'success': False,
            'error': f"Unknown function: {function}. Available functions: list_datasets, get_dataset, get_download_urls"
        }


# For testing
if __name__ == "__main__":
    async def test():
        print("=== Testing list_datasets ===")
        result = await list_datasets()
        print(f"Success: {result.get('success')}")
        print(f"Total datasets: {result.get('total_datasets')}")
        print(f"Returned: {result.get('returned_count')}")
        if result.get('datasets'):
            print("First 3 datasets:")
            for ds in result['datasets'][:3]:
                print(f"  - {ds['title'][:50]} (ID: {ds['id']})")
        
        print("\n=== Testing get_dataset ===")
        result = await get_dataset_detail('WM006')
        print(f"ID: {result.get('id')}")
        print(f"Title: {result.get('title')}")
        print(f"Abstract: {result.get('abstract')}")
        print(f"Metadata: {result.get('metadata')}")
        print(f"Download files: {len(result.get('download_files', []))}")
        for f in result.get('download_files', [])[:3]:
            print(f"  - {f['name']}")
        
        print("\n=== Testing get_download_urls ===")
        result = await get_download_urls('WM006')
        print(f"Success: {result.get('success')}")
        print(f"Download files: {len(result.get('download_files', []))}")
        for f in result.get('download_files', [])[:3]:
            print(f"  - {f['name']}: {f['url']}")
    
    asyncio.run(test())