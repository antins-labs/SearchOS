#!/usr/bin/env python3
"""
Yahoo Finance 历史价格查询工具

从 Yahoo Finance V8 Chart API 获取股票历史价格数据。

用法:
    python history.py AAPL --days 30
    python history.py AAPL --start 2026-09-01 --end 2026-10-12
    python history.py MSFT --days 5 --interval 1h --output history.json
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta


VALID_INTERVALS = ['1m', '2m', '5m', '15m', '30m', '60m', '1h', '1d', '5d', '1wk', '1mo', '3mo']


def parse_date(date_str: str) -> int:
    """将日期字符串转换为 Unix 时间戳。"""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return int(dt.timestamp())
    except ValueError:
        raise ValueError(f"日期格式无效: {date_str}，请使用 YYYY-MM-DD 格式")


def fetch_history(symbol: str, period1: int, period2: int, interval: str = '1d') -> dict:
    """
    从 Yahoo Finance 获取历史价格数据。
    
    Args:
        symbol: 股票代码
        period1: 开始时间戳
        period2: 结束时间戳
        interval: 时间间隔（1m, 5m, 1h, 1d, 1wk, 1mo 等）
    
    Returns:
        包含历史数据的字典
    
    Raises:
        ValueError: 无效参数
        RuntimeError: 网络请求失败
    """
    symbol = symbol.upper().strip()
    
    if interval not in VALID_INTERVALS:
        raise ValueError(f"无效的 interval: {interval}，支持的值: {', '.join(VALID_INTERVALS)}")
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval={interval}"
    
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
        with urllib.request.urlopen(request, context=ctx, timeout=30) as response:
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
    
    chart_data = result[0]
    meta = chart_data.get('meta', {})
    timestamps = chart_data.get('timestamp', [])
    indicators = chart_data.get('indicators', {})
    
    # 获取 OHLCV 数据
    quote_data = {}
    if 'quote' in indicators and indicators['quote']:
        quote_data = indicators['quote'][0]
    
    # 构建输出数据
    source_url = f"https://finance.yahoo.com/quote/{symbol}/history"
    history = []
    for i, ts in enumerate(timestamps):
        try:
            # 根据间隔决定日期格式
            dt = datetime.fromtimestamp(ts)
            if interval in ['1m', '2m', '5m', '15m', '30m', '60m', '1h']:
                date_str = dt.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = dt.strftime('%Y-%m-%d')
            
            record = {
                'date': date_str,
                'open': quote_data.get('open', [None])[i] if i < len(quote_data.get('open', [])) else None,
                'high': quote_data.get('high', [None])[i] if i < len(quote_data.get('high', [])) else None,
                'low': quote_data.get('low', [None])[i] if i < len(quote_data.get('low', [])) else None,
                'close': quote_data.get('close', [None])[i] if i < len(quote_data.get('close', [])) else None,
                'volume': quote_data.get('volume', [None])[i] if i < len(quote_data.get('volume', [])) else None,
                'source_url': source_url,
            }
            
            # 跳过无效数据（None 值）
            if record['close'] is not None:
                history.append(record)
                
        except (ValueError, OSError, IndexError):
            continue
    
    return {
        'symbol': meta.get('symbol', symbol),
        'name': meta.get('longName') or meta.get('shortName', ''),
        'interval': interval,
        'currency': meta.get('currency', 'USD'),
        'exchange': meta.get('fullExchangeName', ''),
        'data_count': len(history),
        'data': history,
        'source_url': f"https://finance.yahoo.com/quote/{symbol}/history"
    }


def main():
    parser = argparse.ArgumentParser(
        description='从 Yahoo Finance 获取股票历史价格',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python history.py AAPL --days 30
  python history.py AAPL --start 2026-09-01 --end 2026-10-12
  python history.py MSFT --days 5 --interval 1h -o history.json

支持的 interval:
  分钟: 1m, 2m, 5m, 15m, 30m, 60m, 1h
  日线: 1d, 5d
  周线/月线: 1wk, 1mo, 3mo

注意: 分钟级数据仅提供最近7天
'''
    )
    parser.add_argument('symbol', help='股票代码（如 AAPL, MSFT）')
    
    # 时间范围参数（二选一）
    time_group = parser.add_mutually_exclusive_group(required=True)
    time_group.add_argument('--days', type=int, help='获取最近 N 天数据')
    time_group.add_argument('--start', help='开始日期（YYYY-MM-DD），需配合 --end 使用')
    
    parser.add_argument('--end', help='结束日期（YYYY-MM-DD），需配合 --start 使用')
    parser.add_argument('-i', '--interval', default='1d', 
                        help=f'时间间隔，默认 1d。支持: {", ".join(VALID_INTERVALS)}')
    parser.add_argument('-o', '--output', help='输出 JSON 文件路径（默认打印到 stdout）')
    
    args = parser.parse_args()
    
    # 计算时间范围
    if args.days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
        period1 = int(start_date.timestamp())
        period2 = int(end_date.timestamp())
    else:
        if not args.end:
            parser.error("--start 需要配合 --end 使用")
        period1 = parse_date(args.start)
        period2 = parse_date(args.end)
    
    try:
        result = fetch_history(args.symbol, period1, period2, args.interval)
        
        output_json = json.dumps(result, indent=2, ensure_ascii=False)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
            print(f"历史数据已保存到 {args.output}（{result['data_count']} 条记录）", file=sys.stderr)
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