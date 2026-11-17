"""Parser registration and deterministic format routing."""

from __future__ import annotations

from pathlib import Path

from searchos.local import messages
from searchos.local.errors import UnsupportedDocumentError
from searchos.local.parsers.base import DocumentParser, ParserCapability


class ParserRegistry:
    def __init__(self, parsers: list[DocumentParser] | None = None) -> None:
        self._by_extension: dict[str, DocumentParser] = {}
        for parser in parsers or []:
            self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        for extension in parser.capability.extensions:
            normalized = extension.lower()
            if not normalized.startswith("."):
                raise ValueError(messages.EXTENSION_INVALID.format(extension=extension))
            if normalized in self._by_extension:
                raise ValueError(messages.EXTENSION_DUPLICATE.format(extension=normalized))
            self._by_extension[normalized] = parser

    def resolve(self, path: Path) -> DocumentParser:
        suffix = path.suffix.lower()
        parser = self._by_extension.get(suffix)
        if parser is None:
            raise UnsupportedDocumentError(f"UNSUPPORTED_FORMAT：{suffix or messages.NO_EXTENSION}")
        parser.validate(path)
        return parser

    def capabilities(self) -> tuple[ParserCapability, ...]:
        unique = {id(parser): parser.capability for parser in self._by_extension.values()}
        return tuple(sorted(unique.values(), key=lambda value: value.kind.value))


__all__ = ["ParserRegistry"]
