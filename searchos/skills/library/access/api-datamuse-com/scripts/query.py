#!/usr/bin/env python3
"""
Datamuse API 词语检索脚本

通过 Datamuse 公开 API 查询词语关系，支持同义词、相关词、反义词等。
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Dict, Any, Optional


# 关系类型映射
RELATION_MAP = {
    'ml': 'ml',      # means like - 相关词
    'syn': 'rel_syn',  # 同义词
    'ant': 'rel_ant',  # 反义词
    'jja': 'rel_jja',  # 被形容词修饰的名词
    'jjb': 'rel_jjb',  # 修饰名词的形容词
    'sl': 'sl',       # sounds like - 发音相似
    'sp': 'sp',       # spelled like - 拼写相似
    'trg': 'rel_trg', # triggers - 触发相关
}

API_BASE_URL = 'https://api.datamuse.com/words'
DEFAULT_LIMIT = 10
MAX_LIMIT = 100


def build_url(query: str, relation: str, limit: int) -> str:
    """
    构建 Datamuse API 请求 URL。
    
    Args:
        query: 查询词语
        relation: 关系类型（内部参数名）
        limit: 结果数量限制
        
    Returns:
        完整的 API URL
    """
    params = {
        relation: query,
        'max': min(limit, MAX_LIMIT)
    }
    query_string = urllib.parse.urlencode(params)
    return f"{API_BASE_URL}?{query_string}"


def fetch_words(url: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """
    从 Datamuse API 获取词语数据。
    
    Args:
        url: API 请求 URL
        timeout: 请求超时时间（秒）
        
    Returns:
        词语列表
        
    Raises:
        urllib.error.URLError: 网络请求失败
        ValueError: JSON 解析失败或非预期响应
    """
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'SearchOS-Datamuse-Skill/1.0'}
    )
    
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}: {response.reason}")
            
            data = response.read().decode('utf-8')
            result = json.loads(data)
            
            if not isinstance(result, list):
                raise ValueError(f"Unexpected response type: {type(result)}")
            
            return result
            
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise urllib.error.URLError(f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error: {e}")


def format_records(
    words: List[Dict[str, Any]], 
    source_url: str
) -> List[Dict[str, Any]]:
    """
    格式化返回记录，添加来源 URL。
    
    Args:
        words: API 返回的词语列表
        source_url: 原始请求 URL
        
    Returns:
        格式化后的记录列表
    """
    records = []
    for item in words:
        record = {
            'word': item.get('word', ''),
            'score': item.get('score'),
            'source_url': source_url
        }
        # 保留其他字段（如 tags, defs, numSyllables）
        for key in ['tags', 'defs', 'numSyllables']:
            if key in item:
                record[key] = item[key]
        records.append(record)
    return records


def query_words(
    query: str, 
    relation: str = 'ml', 
    limit: int = DEFAULT_LIMIT
) -> Dict[str, Any]:
    """
    查询词语关系。
    
    Args:
        query: 查询词语
        relation: 关系类型代码
        limit: 结果数量限制
        
    Returns:
        包含查询结果和元数据的字典
    """
    # 解析关系类型
    if relation not in RELATION_MAP:
        raise ValueError(
            f"Invalid relation: {relation}. "
            f"Valid options: {', '.join(RELATION_MAP.keys())}"
        )
    
    api_param = RELATION_MAP[relation]
    url = build_url(query, api_param, limit)
    
    # 获取数据
    words = fetch_words(url)
    
    # 格式化记录
    records = format_records(words, url)
    
    return {
        'records': records,
        'query': query,
        'relation': relation,
        'total': len(records)
    }


def main():
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description='通过 Datamuse API 检索词语关系',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
关系类型说明:
  ml   相关词（means like，语义相似）
  syn  同义词
  ant  反义词
  jja  被指定形容词修饰的名词
  jjb  修饰指定名词的形容词
  sl   发音相似词
  sp   拼写相似词（支持通配符 ? 和 *）
  trg  触发相关词（统计共现）

示例:
  %(prog)s --query research --relation ml --limit 5
  %(prog)s -q good -r syn -l 10
  %(prog)s -q ocean -r jjb -o results.json
'''
    )
    
    parser.add_argument(
        '--query', '-q',
        required=True,
        help='查询词语'
    )
    
    parser.add_argument(
        '--relation', '-r',
        default='ml',
        choices=list(RELATION_MAP.keys()),
        help='关系类型，默认为 ml（相关词）'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=DEFAULT_LIMIT,
        help=f'返回结果数量上限，默认 {DEFAULT_LIMIT}，最大 {MAX_LIMIT}'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='输出 JSON 文件路径（默认输出到 stdout）'
    )
    
    args = parser.parse_args()
    
    # 限制最大数量
    limit = min(max(1, args.limit), MAX_LIMIT)
    
    try:
        result = query_words(args.query, args.relation, limit)
        
        output_json = json.dumps(result, indent=2, ensure_ascii=False)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
        else:
            print(output_json)
        
        sys.exit(0)
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
