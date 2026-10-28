"""从 LLM 说明文字中提取完整 JSON 对象，保留字符串、嵌套和歧义边界。"""

from __future__ import annotations

import json
import re

_FENCES = re.compile(
    r'^[ \t]*(`{3,}|~{3,})([^\r\n]*)\r?\n', re.MULTILINE,
)
_INLINE_CODE = re.compile(r'(?P<ticks>`+)(?P<body>.*?)(?<!`)(?P=ticks)(?!`)', re.DOTALL)


def _segments(text):
    """分别读取围栏内外文本，避免删除围栏后拼接出原文没有的 JSON。"""
    position = 0
    while match := _FENCES.search(text, position):
        yield text[position:match.start()], False
        marker = match[1]
        closing = re.compile(
            rf'^[ \t]*{re.escape(marker[0])}{{{len(marker)},}}[ \t]*(?:\r?\n|$)',
            re.MULTILINE,
        ).search(text, match.end())
        end = closing.start() if closing else len(text)
        if match[2].strip().lower() in {'', 'json'}:
            yield text[match.end():end], True
        position = closing.end() if closing else len(text)
    yield text[position:], False


def _container_end(text, start):
    """保留坏容器的边界，避免把它的内层对象提升为完整报告。"""
    stack = []
    in_string = escape = False
    for position in range(start, len(text)):
        character = text[position]
        if in_string:
            if escape:
                escape = False
            elif character == '\\':
                escape = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in '{[':
            stack.append('}' if character == '{' else ']')
        elif character in '}]':
            if not stack or stack.pop() != character:
                return None
            if not stack:
                return position + 1
    return None


def extract_json_object(text: str, *, unique: bool = False) -> dict | None:
    """默认返回首个完整对象；unique 模式拒绝多对象及截断的 JSON 容器。

    JSON 围栏整体解码，围栏外的行内代码作为说明；只有行内 JSON 时可直接读取。
    正式围栏存在时，正文中闭合的非法 JSON 示例不阻断报告；完整对象仍构成歧义。
    数组、JSON 字符串和完整对象整体解码，不将其中的子对象当作顶层报告。
    未找到对象时返回 None；不修改 JSON 内容或猜补缺失字段。
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    segments = list(_segments(text))
    framed = {}
    for index, (segment, is_fence) in enumerate(segments):
        if is_fence:
            try:
                framed[index] = json.loads(segment)
            except json.JSONDecodeError as exc:
                framed[index] = exc
    has_framed_object = any(isinstance(value, dict) for value in framed.values())
    found = None
    inline_objects = []
    for index, (segment, is_fence) in enumerate(segments):
        if is_fence:
            value = framed[index]
            if isinstance(value, json.JSONDecodeError):
                if unique:
                    raise ValueError(
                        'LLM response contains an invalid or incomplete JSON payload'
                    ) from value
                return None
            if isinstance(value, dict):
                if not unique:
                    return value
                if found is not None:
                    raise ValueError('LLM response contains multiple JSON objects')
                found = value
            continue
        position = 0
        while position < len(segment):
            character = segment[position]
            if character == '`':
                code = _INLINE_CODE.match(segment, position)
                if code:
                    try:
                        value = json.loads(code['body'])
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(value, dict):
                            inline_objects.append(value)
                    position = code.end()
                    continue
            if character not in '{["':
                position += 1
                continue
            try:
                value, end = decoder.raw_decode(segment, position)
            except json.JSONDecodeError as exc:
                tail = segment[position + 1:].lstrip()
                end = _container_end(segment, position) if character in '{[' else None
                # 行首容器整体读取；说明中的孤立花括号不吞掉下一行报告。
                orphan_brace = re.match(r'[ \t]*(?:\r?\n[ \t]*)+\{', segment[position + 1:])
                line_prefix = segment[segment.rfind('\n', 0, position) + 1:position]
                structured = character == '{' and (
                    re.match(r'"|[^{}\[\]\s:]+\s*:', tail)
                    or (end is None and tail and not orphan_brace and not line_prefix.strip())
                )
                if structured or (character == '[' and end is None):
                    if has_framed_object and end is not None:
                        position = end
                        continue
                    if unique:
                        raise ValueError(
                            'LLM response contains an invalid or incomplete JSON payload'
                        ) from exc
                    return None
                position = end if end is not None else position + 1
                continue
            position = end
            if isinstance(value, dict):
                if not unique:
                    return value
                if found is not None:
                    raise ValueError('LLM response contains multiple JSON objects')
                found = value
    if found is None and inline_objects:
        if unique and len(inline_objects) != 1:
            raise ValueError('LLM response contains multiple JSON objects')
        return inline_objects[0]
    return found
