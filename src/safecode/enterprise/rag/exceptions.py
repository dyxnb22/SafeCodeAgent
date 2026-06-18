"""Typed exceptions for enterprise RAG source registry and loaders."""


class EnterpriseRagError(Exception):
    """Base error for enterprise RAG operations."""


class DuplicateSourceIdError(EnterpriseRagError):
    """Raised when a manifest declares the same source_id more than once."""


class ManifestValidationError(EnterpriseRagError):
    """Raised when a manifest entry fails structural validation."""


class UnknownSourceTypeError(EnterpriseRagError):
    """Raised when a manifest declares an unsupported source_type."""


class UnknownParserError(EnterpriseRagError):
    """Raised when a manifest declares an unsupported parser."""


class UnsupportedSarifVersionError(EnterpriseRagError):
    """Raised when SARIF input is not version 2.1.0."""


class LoaderTooBigError(EnterpriseRagError):
    """Raised when an individual source file exceeds the loader size cap."""


class LoaderParseError(EnterpriseRagError):
    """Raised when loader input cannot be parsed safely."""
