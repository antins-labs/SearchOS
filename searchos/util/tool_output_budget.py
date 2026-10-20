"""Budget tool output conservatively by UTF-8 bytes when the tokenizer is unknown."""

from contextvars import ContextVar

# 与运行时上下文裁剪共用回退值；未知模型不能据名称猜测窗口长度。
DEFAULT_CONTEXT_TOKENS = 100_000
tool_output_budget: ContextVar[int] = ContextVar(
    "tool_output_budget", default=DEFAULT_CONTEXT_TOKENS,
)


def text_token_bound(text: str) -> int:
    """Bound byte-level token counts without underestimating non-English text."""
    return len(text.encode("utf-8"))


def bounded_text(text: str, budget: int) -> str:
    """Preserve complete Unicode characters without adding text beyond the budget."""
    return text.encode("utf-8")[:max(0, budget)].decode("utf-8", errors="ignore")
