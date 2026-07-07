"""
Browser state management - maintains page stack and navigation history.
Adapted from GPT-OSS SimpleBrowserState.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field

from .models import Extract, PageContents


@dataclass
class BrowserState:
    """Manages the browser's page stack and provides page viewing with scrolling."""

    pages: dict[str, PageContents] = field(default_factory=dict)
    page_stack: list[str] = field(default_factory=list)

    @property
    def current_cursor(self) -> int:
        return len(self.page_stack) - 1

    @property
    def has_pages(self) -> bool:
        return len(self.page_stack) > 0

    def add_page(self, page: PageContents) -> None:
        """Add a page to the stack."""
        self.pages[page.url] = page
        self.page_stack.append(page.url)

    def get_page(self, cursor: int = -1) -> PageContents:
        """Get a page by cursor position. -1 = current page."""
        if not self.has_pages:
            raise ValueError("No pages in browser state.")
        if cursor == -1 or cursor == self.current_cursor:
            return self.pages[self.page_stack[-1]]
        if cursor < 0 or cursor > self.current_cursor:
            raise ValueError(
                f"Cursor {cursor} out of range [0, {self.current_cursor}]."
            )
        return self.pages[self.page_stack[cursor]]

    def get_page_by_url(self, url: str) -> PageContents | None:
        """Get a cached page by URL."""
        return self.pages.get(url)

    def show_page(
        self,
        loc: int = 0,
        max_lines: int = -1,
        view_tokens: int = 2048,
        wrap_width: int = 80,
    ) -> str:
        """Show a portion of the current page with line numbers.

        Returns formatted text ready for the LLM, including header and scrollbar info.
        """
        page = self.get_page()
        lines = _wrap_lines(page.text, width=wrap_width)
        total_lines = len(lines)

        if total_lines == 0:
            return f"{page.title}\n**empty page**"

        loc = max(0, min(loc, total_lines - 1))

        # Calculate end location based on token budget
        if max_lines <= 0:
            # Approximate: ~4 chars per token
            chars_budget = view_tokens * 4
            char_count = 0
            end_loc = loc
            for i in range(loc, total_lines):
                line_len = len(f"L{i}: {lines[i]}") + 1  # +1 for newline
                char_count += line_len
                if char_count > chars_budget:
                    break
                end_loc = i + 1
            end_loc = max(end_loc, loc + 1)  # Show at least 1 line
        else:
            end_loc = min(loc + max_lines, total_lines)

        # Build display text
        display_lines = [f"L{i}: {lines[i]}" for i in range(loc, end_loc)]
        body = "\n".join(display_lines)

        scrollbar = f"viewing lines [{loc} - {end_loc - 1}] of {total_lines - 1}"
        cursor = self.current_cursor

        # Build header
        header = f"<Page {cursor}> {page.title}"
        if page.url:
            domain = _truncate(page.url, 100)
            header += f" ({domain})"
        header += f"\n**{scrollbar}**\n\n"

        return header + body


def find_in_page(
    pattern: str,
    page: PageContents,
    max_results: int = 50,
    context_lines: int = 4,
    wrap_width: int = 80,
) -> PageContents:
    """Find text pattern in page, return a new PageContents with results.

    Adapted from GPT-OSS run_find_in_page.
    """
    lines = _wrap_lines(page.text, width=wrap_width)
    # Strip link markers for search
    text_no_links = re.sub(r"\u3010\d+\u2020[^\u3011]+\u3011", lambda m: _extract_link_text(m), "\n".join(lines))
    lines = text_no_links.split("\n")

    result_chunks = []
    snippets = {}
    match_idx = 0
    used_lines: set[int] = set()

    for line_idx in range(len(lines)):
        if pattern not in lines[line_idx].lower():
            continue
        if line_idx in used_lines:
            continue

        start = max(0, line_idx - context_lines)
        end = min(len(lines), line_idx + context_lines + 1)
        snippet_lines = [
            f"{'>'  if i == line_idx else ' '} L{i}: {lines[i]}"
            for i in range(start, end)
        ]
        snippet_text = "\n".join(snippet_lines)
        result_chunks.append(f"# Match {match_idx} at L{line_idx}\n{snippet_text}")
        snippets[str(match_idx)] = Extract(
            url=page.url,
            text=snippet_text,
            title=f"#{match_idx}",
            line_idx=line_idx,
        )
        used_lines.update(range(start, end))

        if len(result_chunks) >= max_results:
            break
        match_idx += 1

    if result_chunks:
        display_text = "\n\n".join(result_chunks)
    else:
        display_text = f"No results for pattern: `{pattern}`"

    return PageContents(
        url=f"{page.url}/find?pattern={pattern}",
        title=f"Find: `{pattern}` in `{page.title}`",
        text=display_text,
        urls={str(i): page.url for i in range(len(result_chunks))},
        snippets=snippets,
    )

def _extract_link_text(match: re.Match) -> str:
    """Extract display text from a 【id†text†domain】 link."""
    content = match.group(0)
    # Remove 【 and 】
    inner = content[1:-1]
    parts = inner.split("\u2020")  # split by †
    if len(parts) >= 2:
        return parts[1]
    return inner

def _wrap_lines(text: str, width: int = 80) -> list[str]:
    """Wrap long lines for display."""
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if line:
            wrapped.extend(
                textwrap.wrap(
                    line, width=width, replace_whitespace=False, drop_whitespace=False
                )
            )
        else:
            wrapped.append("")
    return wrapped

def _truncate(text: str, max_len: int = 100, suffix = "...") -> str:

    if len(text) > max_len:
        return text[: max_len - len(suffix)] + suffix
    return text
