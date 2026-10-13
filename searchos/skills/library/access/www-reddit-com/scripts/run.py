#!/usr/bin/env python3
"""兼容旧接口的 RSS 转发入口。仅支持 get_subreddit，拒绝其他功能。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 导入 reddit_rss 的核心函数
sys.path.insert(0, str(Path(__file__).parent))
try:
    from reddit_rss import fetch_subreddit_rss
except ImportError:
    fetch_subreddit_rss = None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Reddit RSS Reader - 兼容旧接口。仅支持 get_subreddit，其他功能不可用。'
    )
    parser.add_argument('--params', help='JSON 参数对象')
    parser.add_argument('--params-file', help='JSON 参数文件')
    parser.add_argument('--result-file', help='输出文件路径')
    parser.add_argument('--function', help='功能名（仅支持 get_subreddit）')
    parser.add_argument('--subreddit', help='板块名称')
    parser.add_argument('--limit', type=int, default=25, help='数量限制')
    
    args = parser.parse_args(argv)
    
    # 解析参数
    params = {}
    if args.params:
        params = json.loads(args.params)
    elif args.params_file:
        params_file = Path(args.params_file)
        if args.params_file == '-':
            params = json.loads(sys.stdin.read())
        else:
            params = json.loads(params_file.read_text(encoding='utf-8'))
    
    # 命令行参数覆盖
    if args.function:
        params['function'] = args.function
    if args.subreddit:
        params['subreddit'] = args.subreddit
    if args.limit:
        params['limit'] = args.limit
    
    function = params.get('function', 'get_subreddit')
    
    # 仅支持 get_subreddit
    if function != 'get_subreddit':
        result = {
            'success': False,
            'error': f'功能 {function} 不可用。PullPush API 不稳定，本技能仅支持 get_subreddit（通过官方 RSS）。',
            'available_functions': ['get_subreddit'],
            'note': '请使用 scripts/reddit_rss.py 直接调用 RSS 阅读功能',
        }
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.result_file:
            Path(args.result_file).write_text(output + '\n', encoding='utf-8')
        else:
            print(output)
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    
    subreddit = params.get('subreddit', '')
    limit = params.get('limit', 25)
    
    if not subreddit:
        result = {'success': False, 'error': 'subreddit 参数必填'}
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.result_file:
            Path(args.result_file).write_text(output + '\n', encoding='utf-8')
        else:
            print(output)
        return 1
    
    if fetch_subreddit_rss is None:
        result = {'success': False, 'error': '无法加载 reddit_rss 模块'}
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.result_file:
            Path(args.result_file).write_text(output + '\n', encoding='utf-8')
        else:
            print(output)
        return 1
    
    try:
        result = fetch_subreddit_rss(subreddit, limit)
    except ValueError as e:
        result = {'success': False, 'error': str(e)}
    
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.result_file:
        Path(args.result_file).write_text(output + '\n', encoding='utf-8')
    else:
        print(output)
    
    if not result.get('success'):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
