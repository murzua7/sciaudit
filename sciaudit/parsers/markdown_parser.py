"""Parse Markdown documents into structured sections."""

from __future__ import annotations

import re

from sciaudit.parsers.html_parser import ParsedDocument, Section


def parse_markdown(md_content: str) -> ParsedDocument:
    """Parse a Markdown document into structured sections.

    Args:
        md_content: Raw Markdown string.

    Returns:
        ParsedDocument with title, sections, full_text, references.
    """
    lines = md_content.split("\n")
    sections: list[Section] = []
    current_heading = ""
    current_level = 0
    current_lines: list[str] = []
    title = ""

    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            # Save previous section
            if current_heading or current_lines:
                text = "\n".join(current_lines).strip()
                sections.append(Section(
                    heading=current_heading,
                    level=current_level,
                    text=text,
                ))

            current_level = len(m.group(1))
            current_heading = m.group(2).strip()
            current_lines = []

            if not title and current_level == 1:
                title = current_heading
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_heading or current_lines:
        text = "\n".join(current_lines).strip()
        sections.append(Section(
            heading=current_heading,
            level=current_level,
            text=text,
        ))

    if not title:
        title = sections[0].heading if sections else "Untitled"

    # Extract references
    references = []
    for section in sections:
        low = section.heading.lower()
        if any(kw in low for kw in ("reference", "bibliography", "works cited")):
            for line in section.text.split("\n"):
                line = line.strip()
                if line and len(line) > 20:
                    # Strip markdown list markers
                    line = re.sub(r"^[-*+]\s+", "", line)
                    line = re.sub(r"^\d+\.\s+", "", line)
                    references.append(line)

    return ParsedDocument(
        title=title,
        sections=sections,
        full_text=md_content,
        references=references,
        footnotes=[],
    )
