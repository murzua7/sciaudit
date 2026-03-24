"""Parse HTML reports into structured sections with text content."""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag


@dataclass
class Section:
    """A document section with heading and text content."""

    heading: str
    level: int  # h1=1, h2=2, etc.
    text: str  # all text content in this section
    tables: list[list[list[str]]] = field(default_factory=list)  # rows of cells
    subsections: list[Section] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Structured representation of a parsed document."""

    title: str
    sections: list[Section]
    full_text: str  # all text concatenated
    references: list[str]  # extracted reference list items
    footnotes: list[str]


def _extract_table(table_tag: Tag) -> list[list[str]]:
    """Extract table as list of rows, each row a list of cell strings."""
    rows = []
    for tr in table_tag.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"]):
            cells.append(td.get_text(strip=True))
        if cells:
            rows.append(cells)
    return rows


def _extract_section_text(elements: list) -> tuple[str, list[list[list[str]]]]:
    """Extract text and tables from a list of elements between headings."""
    texts = []
    tables = []
    for el in elements:
        if isinstance(el, Tag):
            if el.name == "table":
                tables.append(_extract_table(el))
            elif el.name in ("script", "style", "canvas"):
                continue
            else:
                t = el.get_text(separator=" ", strip=True)
                if t:
                    texts.append(t)
        elif isinstance(el, NavigableString):
            t = str(el).strip()
            if t:
                texts.append(t)
    return " ".join(texts), tables


def parse_html(html_content: str) -> ParsedDocument:
    """Parse an HTML document into structured sections.

    Args:
        html_content: Raw HTML string.

    Returns:
        ParsedDocument with title, sections, full_text, references, footnotes.
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Remove script and style tags
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "Untitled"

    # Find all heading tags
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    sections = []
    for i, heading in enumerate(heading_tags):
        level = int(heading.name[1])
        heading_text = heading.get_text(strip=True)

        # Collect elements until next heading
        elements = []
        sibling = heading.next_sibling
        next_heading = heading_tags[i + 1] if i + 1 < len(heading_tags) else None
        while sibling and sibling != next_heading:
            if isinstance(sibling, Tag) and sibling.name in (
                "h1", "h2", "h3", "h4", "h5", "h6"
            ):
                break
            elements.append(sibling)
            sibling = sibling.next_sibling

        text, tables = _extract_section_text(elements)
        sections.append(Section(
            heading=heading_text,
            level=level,
            text=text,
            tables=tables,
        ))

    # Full text extraction
    body = soup.find("body") or soup
    full_text = body.get_text(separator="\n", strip=True)

    # Extract references section
    references = []
    for section in sections:
        low = section.heading.lower()
        if any(kw in low for kw in ("reference", "bibliography", "works cited", "appendix")):
            # Try to find list items
            for heading in heading_tags:
                if heading.get_text(strip=True) == section.heading:
                    parent = heading.parent
                    if parent:
                        for li in parent.find_all("li"):
                            ref_text = li.get_text(strip=True)
                            if ref_text:
                                references.append(ref_text)
                    break
            if not references and section.text:
                # Split by newlines or numbered patterns
                for line in section.text.split("\n"):
                    line = line.strip()
                    if line and len(line) > 20:
                        references.append(line)

    # Extract footnotes
    footnotes = []
    for fn in soup.find_all(class_=lambda c: c and "footnote" in str(c).lower()):
        footnotes.append(fn.get_text(strip=True))

    return ParsedDocument(
        title=title,
        sections=sections,
        full_text=full_text,
        references=references,
        footnotes=footnotes,
    )
