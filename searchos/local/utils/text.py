"""Shared text normalization helpers for local indexing and catalogs."""

from __future__ import annotations


def one_line(value: str) -> str:
    return " ".join(value.replace("\x00", "").splitlines()).strip()


__all__ = ["one_line"]
