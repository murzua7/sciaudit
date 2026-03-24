"""Tests for document parsers."""

import pytest

from sciaudit.parsers.html_parser import parse_html
from sciaudit.parsers.markdown_parser import parse_markdown


class TestHTMLParser:
    def test_basic_structure(self):
        html = """
        <html>
        <head><title>Test Report</title></head>
        <body>
            <h1>Introduction</h1>
            <p>This is the introduction.</p>
            <h2>Background</h2>
            <p>Some background text.</p>
        </body>
        </html>
        """
        doc = parse_html(html)
        assert doc.title == "Test Report"
        assert len(doc.sections) == 2
        assert doc.sections[0].heading == "Introduction"
        assert doc.sections[1].heading == "Background"

    def test_table_extraction(self):
        html = """
        <html><body>
        <h2>Data</h2>
        <table>
            <tr><th>Year</th><th>GDP</th></tr>
            <tr><td>2020</td><td>21.0T</td></tr>
        </table>
        </body></html>
        """
        doc = parse_html(html)
        assert len(doc.sections) == 1
        assert len(doc.sections[0].tables) == 1
        assert doc.sections[0].tables[0][0] == ["Year", "GDP"]

    def test_script_removal(self):
        html = """
        <html><body>
        <h1>Title</h1>
        <p>Real content.</p>
        <script>var x = 1;</script>
        </body></html>
        """
        doc = parse_html(html)
        assert "var x" not in doc.full_text

    def test_empty_document(self):
        doc = parse_html("<html><body></body></html>")
        assert doc.title == "Untitled"
        assert doc.sections == []


class TestMarkdownParser:
    def test_basic_structure(self):
        md = """# Report Title

Introduction text here.

## Background

Background content.

## Methods

Methods description.
"""
        doc = parse_markdown(md)
        assert doc.title == "Report Title"
        assert len(doc.sections) == 3

    def test_nested_headings(self):
        md = """# Title

## Section 1

### Subsection 1.1

Content here.

## Section 2

More content.
"""
        doc = parse_markdown(md)
        assert len(doc.sections) >= 3

    def test_reference_extraction(self):
        md = """# Paper

## Methods

Some methods.

## References

- Hamilton, J.D. (2003). What is an oil shock? Journal of Econometrics.
- Kilian, L. (2009). Not all oil price shocks are alike. AER.
"""
        doc = parse_markdown(md)
        assert len(doc.references) >= 2
        assert any("Hamilton" in r for r in doc.references)
