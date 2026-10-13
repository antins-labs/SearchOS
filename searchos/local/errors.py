"""Errors raised by the local-document pipeline."""


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
