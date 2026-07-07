"""Robust JSON extraction from LLM output.

LLM outputs often include JSON wrapped in prose, ```json fences, or with
nested objects/quoted braces. A naive `re.search(r"\\{.*\\}", text)` picks a
span from the first `{` to the last `}` — which breaks when prose contains
`{` or when multiple JSON blobs are mixed with commentary.

`extract_json_object()` scans brace depth while tracking string state and
escapes, returning the first valid top-level JSON object.
"""

from __future__ import annotations

import json


def extract_json_object(text: str) -> dict | None:
    """Return the first top-level JSON object from `text`, or None if not found.

    Handles:
    - ```json / ``` code fences (strips them)
    - Prose before and after the JSON
    - Nested `{}` inside string values or sub-objects
    - Escape sequences inside strings (`\"`, `\\`)

    Returns None if no parseable JSON object is found.
    """
    if not text:
        return None

    stripped = text.strip()

    # Strip a leading fence line like ```json or ```
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]

    start = stripped.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stripped[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
