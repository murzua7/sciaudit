"""Document parsers for extracting text and structure."""

from sciaudit.parsers.html_parser import parse_html
from sciaudit.parsers.markdown_parser import parse_markdown

__all__ = ["parse_html", "parse_markdown"]
