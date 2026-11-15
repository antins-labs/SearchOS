"""三个创建角色共享的连接诊断。"""

NETWORK_CHECK_TOOL = {
    'type': 'function',
    'function': {
        'name': 'network_check',
        'description': '诊断目标 URL 的连接，返回线路探测结果。需要试用线路时传入 route，然后用 exec 复验原业务输入。技能创建流程在业务验收通过后保存线路。',
        'parameters': {
            'type': 'object', 'properties': {
                'url': {'type': 'string', 'description': '要诊断的目标 HTTP(S) URL。'},
                'route': {'type': 'string', 'enum': ['direct', 'proxy'],
                          'description': '可选 direct 或 proxy，供本任务后续新连接试用。人工域名规则优先，省略时仅诊断。'},
            },
            'required': ['url'], 'additionalProperties': False,
        },
    },
}


async def check_network(url, route=None):
    from searchos.network import network_check
    return await network_check(url, route=route)
