#!/usr/bin/env python3
"""
Yahoo Finance 股票报价查询工具

从 Yahoo Finance V8 Chart API 获取股票实时报价和基本信息。

用法:
    python quote.py AAPL
    python quote.py MSFT --output quote.json
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import ssl
from datetime import datetime


def fetch_quote(symbol: str) -> dict:
    """
    从 Yahoo Finance 获取股票报价信息。
    
    Args:
        symbol: 股票代码（如 AAPL）
    
    Returns:
        包含报价信息的字典
    
    Raises:
        ValueError: 无效的股票代码
        RuntimeError: 网络请求失败
    """
    symbol = symbol.upper().strip()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    
    # 创建 SSL 上下文
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    )
    
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"股票代码 '{symbol}' 不存在或无效")
        raise RuntimeError(f"HTTP 请求失败: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("响应解析失败")
    
    # 解析响应
    if 'chart' not in data or 'result' not in data['chart']:
        raise ValueError(f"股票代码 '{symbol}' 数据不可用")
    
    result = data['chart']['result']
    if not result:
        error_msg = data['chart'].get('error', {}).get('description', '未知错误')
        raise ValueError(f"获取数据失败: {error_msg}")
    
    meta = result[0].get('meta', {})
    
    # 构建输出
    quote = {
        'symbol': meta.get('symbol', symbol),
        'name': meta.get('longName') or meta.get('shortName', ''),
        'price': meta.get('regularMarketPrice'),
        'change_percent': meta.get('regularMarketChangePercent'),
        'currency': meta.get('currency', 'USD'),
        'exchange': meta.get('fullExchangeName', ''),
        'exchange_timezone': meta.get('exchangeTimezoneName', ''),
        'volume': meta.get('regularMarketVolume'),
        'day_high': meta.get('regularMarketDayHigh'),
        'day_low': meta.get('regularMarketDayLow'),
        'fifty_two_week_high': meta.get('fiftyTwoWeekHigh'),
        'fifty_two_week_low': meta.get('fiftyTwoWeekLow'),
        'market_time': None,
        'source_url': f"https://finance.yahoo.com/quote/{symbol}/"
    }
    
    # 包装为数组以便验证
    quotes = [quote]
    
    # 转换市场时间
    market_time_ts = meta.get('regularMarketTime')
    if market_time_ts:
        try:
            quote['market_time'] = datetime.fromtimestamp(market_time_ts).strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OSError):
            pass
    
    # 包装为数组以便验证
    quotes = [quote]
    
    return quotes


def main():
    parser = argparse.ArgumentParser(
        description='从 Yahoo Finance 获取股票实时报价',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python quote.py AAPL
  python quote.py MSFT -o quote.json
'''
    )
    parser.add_argument('symbol', help='股票代码（如 AAPL, MSFT）')
    parser.add_argument('-o', '--output', help='输出 JSON 文件路径（默认打印到 stdout）')
    
    args = parser.parse_args()
    
    try:
        quotes = fetch_quote(args.symbol)
        
        output_json = json.dumps(quotes, indent=2, ensure_ascii=False)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
            print(f"报价已保存到 {args.output}", file=sys.stderr)
        else:
            print(output_json)
        
        return 0
        
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"未知错误: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())