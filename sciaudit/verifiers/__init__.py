"""Verification modules for different claim types."""

from sciaudit.verifiers.citation import CitationVerifier
from sciaudit.verifiers.data import DataVerifier

__all__ = ["CitationVerifier", "DataVerifier"]
