"""Parser protocol for local documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from searchos.local.models import DocumentKind, ParseResult, PipelineOptions


@dataclass(frozen=True, slots=True)
class ParserCapability:
    kind: DocumentKind
    extensions: tuple[str, ...]
    locator_kinds: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    visual: bool = False


class DocumentParser(Protocol):
    capability: ParserCapability

    def validate(self, path: Path) -> None: ...

    async def parse(self, path: Path, *, options: PipelineOptions) -> ParseResult: ...
