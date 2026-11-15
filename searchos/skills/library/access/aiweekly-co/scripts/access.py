#!/usr/bin/env python3
"""
AI Weekly 新闻访问脚本
支持按日期获取 AI 新闻摘要
"""
import sys as _skill_sys, os as _skill_os
_skill_sys.path.insert(0, _skill_os.path.dirname(_skill_os.path.abspath(__file__)))
import _network as _skill_network

import argparse
import json
import sys
import urllib.request
import urllib.error
import ssl
import re
import html as html_module
import time
from typing import Optional, Dict, List, Any


def create_ssl_context():
    """创建 SSL 上下文"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_url(url: str, retries: int = 3, timeout: int = 30) -> str:
    """获取 URL 内容，支持重试"""
    ctx = create_ssl_context()
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            })
            with _skill_network.urllib_urlopen(req, context=ctx, timeout=timeout) as resp:
                return resp.read().decode('utf-8')
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def clean_text(text: str) -> str:
    """清理 HTML 标签和实体"""
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    return text.strip()


def get_date_to_url_map() -> Dict[str, str]:
    """从 editions 页面获取日期到 URL 的映射"""
    editions_html = fetch_url('https://aiweekly.co/ai-news-today/editions')
    
    # 提取所有日期链接
    # 格式: <a class="dehub__item" href="/ai-news-today/edition/2026-10-19"><span class="dehub__item-date">Monday, October 19</span>
    date_links = re.findall(
        r'<a[^>]*class="dehub__item"[^>]*href="([^"]+)"[^>]*><span class="dehub__item-date">([^<]+)</span>',
        editions_html
    )
    
    date_to_url = {}
    for href, date_text in date_links:
        # date_text 格式: "Monday, October 19"
        # 提取 "October 19"
        match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+',
            date_text
        )
        if match:
            date_key = match.group(0)
            date_to_url[date_key] = 'https://aiweekly.co' + href
    
    return date_to_url


def parse_news_articles(day_html: str, target_date: str) -> List[Dict[str, Any]]:
    """解析新闻条目"""
    articles = re.findall(r'<article[^>]*>(.+?)</article>', day_html, re.DOTALL)
    
    records = []
    for article in articles:
        record = {}
        
        # 提取元信息: "Oct 19 · Wccftech · Chips And Infrastructure"
        meta_match = re.search(
            r'<div[^>]*style="[^"]*font-size:10\.5px[^"]*"[^>]*>([^<]+)</div>',
            article
        )
        if meta_match:
            meta = clean_text(meta_match.group(1))
            parts = meta.split('·')
            if len(parts) >= 3:
                date_part = parts[0].strip()
                source = parts[1].strip()
                category = parts[2].strip()
                
                # 提取 time_ago (如 "Oct 19" 相对当前日期)
                # 简化处理，直接使用元信息中的日期
                time_ago = date_part
                
                record['time_ago'] = time_ago
                record['category'] = category
            elif len(parts) == 2:
                source = parts[1].strip()
        
        # 提取标题和链接
        title_match = re.search(
            r'<a[^>]*href="([^"]+)"[^>]*style="[^"]*font-size:(?:23|16\.5)px[^"]*"[^>]*>([^<]+)</a>',
            article
        )
        if not title_match:
            # 备用模式
            title_match = re.search(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', article)
        
        if title_match:
            alert_url = title_match.group(1)
            title = clean_text(title_match.group(2))
            
            # 移除标题末尾的 "→"
            title = re.sub(r'\s*→\s*$', '', title)
            
            record['title'] = title
            # source_url 直接使用文章链接
            record['source_url'] = alert_url
            # canonical_url 也使用文章链接（不额外请求详情页）
            record['canonical_url'] = alert_url
        
        # 提取摘要
        summary_match = re.search(
            r'<p[^>]*style="[^"]*font-size:13\.5px[^"]*"[^>]*>([^<]+)</p>',
            article
        )
        if not summary_match:
            summary_match = re.search(r'<p[^>]*>([^<]+)</p>', article)
        
        if summary_match:
            record['summary'] = clean_text(summary_match.group(1))
        
        # 添加目标日期
        record['date'] = target_date
        
        # 确保所有必需字段都存在
        required_fields = ['date', 'title', 'summary', 'source_url', 'category', 'time_ago']
        if all(field in record for field in required_fields):
            records.append(record)
    
    return records


def get_news_by_date(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """获取指定日期的新闻"""
    date_str = input_data.get('date', '').strip()
    
    if not date_str:
        return {
            'status': 'invalid_input',
            'records': [],
            'warnings': ['Missing required field: date']
        }
    
    try:
        # 获取日期映射
        date_to_url = get_date_to_url_map()
        
        # 查找匹配的日期
        # 支持格式: "October 19", "September 15"
        if date_str not in date_to_url:
            # 尝试标准化日期格式
            # 可能用户输入 "october 19" (小写)
            date_str_normalized = date_str.title()
            
            # 也尝试匹配月份和日期
            found = False
            for key in date_to_url:
                if key.lower() == date_str.lower():
                    date_str = key
                    found = True
                    break
            
            if not found:
                return {
                    'status': 'ok',
                    'records': [],
                    'warnings': [f'No edition found for date: {date_str}. Available dates: {", ".join(list(date_to_url.keys())[:10])}...']
                }
        
        target_url = date_to_url[date_str]
        
        # 获取新闻页面
        day_html = fetch_url(target_url)
        
        # 解析新闻条目
        records = parse_news_articles(day_html, date_str)
        
        return {
            'status': 'ok',
            'records': records,
            'warnings': []
        }
        
    except urllib.error.HTTPError as e:
        return {
            'status': 'error',
            'records': [],
            'warnings': [f'HTTP error {e.code}: {e.reason}']
        }
    except urllib.error.URLError as e:
        return {
            'status': 'error',
            'records': [],
            'warnings': [f'Network error: {str(e.reason)}']
        }
    except Exception as e:
        return {
            'status': 'error',
            'records': [],
            'warnings': [f'Error: {str(e)}']
        }


@_skill_network.entrypoint(capability_id='access', cli=True)
def main():
    parser = argparse.ArgumentParser(
        description='AI Weekly 新闻访问工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        'capability_id',
        choices=['get_news_by_date'],
        help='能力 ID'
    )
    parser.add_argument(
        '--input',
        required=True,
        help='JSON 格式的输入参数'
    )
    
    args = parser.parse_args()
    
    # 解析输入
    try:
        input_data = json.loads(args.input)
    except json.JSONDecodeError as e:
        result = {
            'status': 'invalid_input',
            'records': [],
            'warnings': [f'Invalid JSON input: {str(e)}']
        }
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)
    
    # 执行能力
    if args.capability_id == 'get_news_by_date':
        result = get_news_by_date(input_data)
    else:
        result = {
            'status': 'invalid_input',
            'records': [],
            'warnings': [f'Unknown capability: {args.capability_id}']
        }
    
    # 输出结果
    print(json.dumps(result, ensure_ascii=False))
    
    # 非成功状态返回非零退出码
    if result['status'] != 'ok':
        sys.exit(1)


if __name__ == '__main__':
    main()