"""Errors raised by the local-document pipeline."""

from pydantic import ValidationError

from searchos.local import messages


class LocalDocumentError(RuntimeError):
    """Base error for local-document processing."""


class UnsupportedDocumentError(LocalDocumentError):
    """The file type is not supported by the selected parser."""


class DocumentAccessError(LocalDocumentError):
    """The source is outside the caller-authorized root."""


class MissingDependencyError(LocalDocumentError):
    """An optional local-document dependency is unavailable."""


class RecapValidationError(LocalDocumentError):
    """Model output does not satisfy the recap data contract."""


def user_message(exc: Exception, fallback: str = messages.PROCESSING_FAILED) -> str:
    """保留已定义的处理错误，其他异常由调用方记录到日志。"""
    if isinstance(exc, ValidationError):
        return fallback
    if isinstance(exc, (LocalDocumentError, ValueError, OverflowError, KeyError)):
        return str(exc).strip("'")
    return fallback
