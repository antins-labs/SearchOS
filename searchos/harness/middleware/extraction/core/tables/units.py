"""Deterministic unit normalization for extracted numeric cells.

The judge is told to convert units in-prompt, but does so unreliably: it
frequently copies the verbatim source number into a column whose name pins a
different unit (e.g. writes "131" from "$131 billion" into a 亿美元 column,
where the correct value is 1310). The source excerpt retains the original
wording, so we re-derive the conversion in code rather than trusting the LLM.

Conservative by design: a value is only rescaled when it still equals the
source number that appears next to a DIFFERENT magnitude word in the excerpt
(i.e. the judge copied verbatim without converting). If the judge already
converted, the stored value no longer matches the raw number and we leave it.
"""

from __future__ import annotations

import re

# Powers-of-ten magnitude vocabulary (mirrors orchestrator_tools).
_CJK = {
    "千": 1e3,
    "万": 1e4,
    "十万": 1e5,
    "百万": 1e6,
    "千万": 1e7,
    "亿": 1e8,
    "十亿": 1e9,
    "百亿": 1e10,
    "千亿": 1e11,
    "万亿": 1e12,
}
_EN = {
    "thousand": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "trillion": 1e12,
}

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?"
# Longer CJK magnitudes first so the alternation is greedy-correct.
_UNIT_ALT = (
    "万亿|千亿|百亿|十亿|千万|百万|十万|亿|万|千"
    "|thousand|millions|million|billions|billion|trillion"
)
_PAIR = re.compile(rf"({_NUM})\s*({_UNIT_ALT})", re.IGNORECASE)


def _parse_num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _fmt(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _target_factor(col_text: str) -> float | None:
    """Magnitude factor pinned by the column name/desc unit, or None."""
    name = col_text or ""
    cjk = [(u, s) for u, s in _CJK.items() if u in name]
    if cjk:
        # longest CJK magnitude wins (亿 over the bare 万 in 财富值（亿美元）)
        return max(cjk, key=lambda x: len(x[0]))[1]
    en = [_EN[w.lower()] for w in re.findall(r"[A-Za-z]+", name) if w.lower() in _EN]
    if en:
        return en[0]
    return None


def normalize_value(value: str, excerpt: str, col_text: str) -> tuple[str, str | None]:
    """Return (possibly-rescaled value, note-or-None).

    Fires only when the column pins a unit and the same numeric value appears
    in the excerpt next to a different magnitude word.
    """
    tgt = _target_factor(col_text)
    if tgt is None:
        return value, None
    v = _parse_num(value)
    if v is None:
        return value, None
    for m in _PAIR.finditer(excerpt or ""):
        num = _parse_num(m.group(1))
        if num is None:
            continue
        unit = m.group(2)
        src = _CJK.get(unit) or _EN.get(unit.lower())
        if src is None or src == tgt:
            continue
        # match the cell's own number (judge copied it verbatim, unconverted)
        if abs(num - v) <= 1e-6 * max(1.0, abs(v)):
            converted = v * src / tgt
            note = f"unit-normalized: {value} ({unit}) -> {_fmt(converted)}"
            return _fmt(converted), note
    return value, None


def validate_projection_calculation(value: str, quote: str, calculation) -> None:
    """核对纯数值投影的算术；单位和条件的含义仍由来源核验器判断。"""
    import ast
    from decimal import Decimal, InvalidOperation
    from fractions import Fraction

    def number(raw):
        if not isinstance(raw, str) or len(raw) > 128:
            raise ValueError("Projection calculation requires bounded decimal numbers")
        parsed = Decimal(raw.replace(",", "").strip())
        if not parsed.is_finite() or abs(parsed.adjusted()) > 100:
            raise ValueError("Projection calculation number is outside supported bounds")
        return Fraction(parsed)

    try:
        Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        if calculation is not None:
            raise ValueError("Use a numeric cell value for a calculated projection")
        return
    target = number(value)
    numbers = {
        number(match.group(0))
        for match in re.finditer(
            r"(?<!\w)[+-]?(?:\d+(?:,\d{3})*(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?!\w)",
            quote,
        )
    }
    if calculation is None:
        if target not in numbers:
            raise ValueError("Numeric projection needs a source-based calculation")
        return
    if not isinstance(calculation, dict) or set(calculation) != {"source_value", "expression"}:
        raise ValueError("Calculation requires source_value and expression")
    source = number(calculation["source_value"])
    if source not in numbers:
        raise ValueError("Calculation source_value is absent from the supporting quote")
    expression = calculation["expression"]
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 128:
        raise ValueError("Calculation expression must contain at most 128 characters")
    tree = ast.parse(expression.strip(), mode="eval")
    if len(list(ast.walk(tree))) > 64 or not any(
        isinstance(node, ast.Name) and node.id == "x" for node in ast.walk(tree)
    ):
        raise ValueError("Calculation must use source variable x within the expression budget")

    def evaluate(node):
        if isinstance(node, ast.Name) and node.id == "x":
            return source
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return number(ast.get_source_segment(expression.strip(), node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = evaluate(node.operand)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            else:
                result = left / right
            if max(result.numerator.bit_length(), result.denominator.bit_length()) > 1024:
                raise ValueError("Calculation exceeds the arithmetic budget")
            return result
        raise ValueError("Calculation supports only x, decimal numbers and + - * /")

    if evaluate(tree.body) != target:
        raise ValueError("Projected value does not match the source-based calculation")
