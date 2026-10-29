"""Answers with receipts: turn Claude's citations into numbered markers and a sources list.

Claude returns cited text as separate text blocks, each with `citations` pointing at a page of a
PDF the owner sent, a passage of a text file, or a web search result. Every URL shown here comes
from the API's citation records, never from text the model wrote.
"""

import re

MAX_SOURCES = 8
MAX_QUOTE = 100

_TRAILING_SPACE = re.compile(r"(\s*)$")


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _describe(citation) -> tuple[tuple, str]:
    """(dedup key, display line) for one citation."""
    kind = getattr(citation, "type", "")
    quote = _clip(getattr(citation, "cited_text", ""), MAX_QUOTE)
    if kind == "web_search_result_location":
        title = _clip(citation.title or citation.url, 80)
        return ("web", citation.url), f"{title} - {citation.url}"
    title = _clip(getattr(citation, "document_title", None) or getattr(citation, "title", None)
                  or getattr(citation, "source", None) or "your document", 80)
    if kind == "page_location":
        last = citation.end_page_number - 1  # end is exclusive
        pages = f"p. {citation.start_page_number}" + (f"-{last}" if last > citation.start_page_number else "")
        return ("doc", title, quote), f'{title}, {pages}: "{quote}"'
    return ("doc", title, quote), f'{title}: "{quote}"'


class SourceList:
    """Collects the sources cited across one reply and numbers them in order of first use."""

    def __init__(self):
        self._numbers: dict[tuple, int] = {}
        self._lines: list[str] = []

    def mark(self, block) -> str:
        """The block's text with [n] markers for whatever it cites."""
        numbers = []
        for citation in getattr(block, "citations", None) or []:
            key, line = _describe(citation)
            if key not in self._numbers:
                self._lines.append(line)
                self._numbers[key] = len(self._lines)
            number = self._numbers[key]
            if number <= MAX_SOURCES and number not in numbers:  # only point at listed sources
                numbers.append(number)
        if not numbers:
            return block.text
        markers = "".join(f"[{n}]" for n in numbers)
        space = _TRAILING_SPACE.search(block.text).group(1)
        return f"{block.text[: len(block.text) - len(space)]} {markers}{space}"

    def footer(self) -> str:
        if not self._lines:
            return ""
        shown = [f"[{i}] {line}" for i, line in enumerate(self._lines[:MAX_SOURCES], start=1)]
        extra = len(self._lines) - MAX_SOURCES
        if extra > 0:
            shown.append(f"(+{extra} more source{'s' if extra > 1 else ''})")
        return "Sources:\n" + "\n".join(shown)


def render(responses: list, sources: SourceList | None = None) -> str:
    """Join the text of one or more responses, with citation markers and a sources footer."""
    sources = sources or SourceList()
    parts = []
    for response in responses:
        text = "".join(sources.mark(b) for b in response.content if b.type == "text").strip()
        if text:
            parts.append(text)
    footer = sources.footer()
    return "\n\n".join(parts + ([footer] if footer and parts else []))
