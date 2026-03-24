"""Claim extractor — identifies verifiable claims from document text.

This module provides heuristic extraction (regex-based) for claims that can be
verified programmatically. For higher-quality extraction, use the Claude Code
skill which leverages LLM understanding of context.

The heuristic extractor catches:
- Inline citations: "Author (Year)", "(Author, Year)", "Author et al. (Year)"
- Quantitative claims: numbers with units/context (%, $, mb/d, basis points)
- Statistical claims: p-values, test statistics, confidence intervals
"""

from __future__ import annotations

import re
from typing import Iterator

from sciaudit.models import Claim, ClaimType, SourceLocation

# Counter for claim IDs
_claim_counter = 0


def _next_id() -> str:
    global _claim_counter
    _claim_counter += 1
    return f"C{_claim_counter:04d}"


def reset_counter() -> None:
    global _claim_counter
    _claim_counter = 0


# --- Citation patterns ---

# "Hamilton (2003)", "Kilian and Murphy (2014)", "Blanchard & Galí (2007)", "Oladosu et al. (2018)"
_INLINE_CITE = re.compile(
    r"([A-Z][a-zà-ü]+(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][a-zà-ü]+)?)"
    r"\s*\((\d{4}[a-z]?)\)"
)

# "(Hamilton, 2003)", "(Kilian & Murphy, 2014; Blanchard & Galí, 2007)"
_PAREN_CITE = re.compile(
    r"\(([A-Z][a-zà-ü]+(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][a-zà-ü]+)?)"
    r",?\s*(\d{4}[a-z]?)\)"
)

# "Hamilton (2003) found that X" — captures the claim text after
_CITE_WITH_CLAIM = re.compile(
    r"([A-Z][a-zà-ü]+(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][a-zà-ü]+)?)"
    r"\s*\((\d{4}[a-z]?)\)\s+"
    r"(?:found|showed|demonstrated|estimated|reported|argued|suggested|concluded|observed)"
    r"\s+(?:that\s+)?(.+?)(?:\.|;|$)"
)

# --- Quantitative claim patterns ---

# Numbers with percentage: "3.2%", "increased by 15%", "-0.020 per 10%"
_PERCENT_CLAIM = re.compile(
    r"((?:[-+]?\d+\.?\d*)\s*%)"
    r"|"
    r"([-+]?\d+\.?\d*)\s+(?:percent|percentage\s+points?|basis\s+points?|bps)"
)

# Dollar amounts: "$150 billion", "$3.2 trillion", "$42/barrel"
_DOLLAR_CLAIM = re.compile(
    r"\$\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(?:(billion|trillion|million|thousand|bn|tn|mn|/barrel|/bbl|per\s+barrel))?"
)

# Physical quantities: "20 mb/d", "104.5 million barrels per day"
_QUANTITY_CLAIM = re.compile(
    r"([-+]?\d+(?:\.\d+)?)\s*"
    r"(mb/d|million\s+barrels?\s+per\s+day|mbd|mt|GW|MW|TWh|bcm|"
    r"million\s+tonnes?|billion\s+tonnes?)"
)

# Generic number-in-context: captures number + surrounding words
_NUMBER_CONTEXT = re.compile(
    r"(?:was|is|reached|hit|fell\s+to|rose\s+to|averaged|totaled?|approximately|about|around|estimated\s+at)\s+"
    r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(%|percent|billion|trillion|million|basis\s+points?|bps|mb/d)?"
)

# --- Statistical patterns ---

_STAT_PVALUE = re.compile(r"p\s*[<>=≤≥]\s*0?\.\d+")
_STAT_TEST = re.compile(
    r"(?:t|F|χ²|chi-squared?|z|r|R²)\s*"
    r"(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?\s*=\s*[-+]?\d+\.?\d*"
)
_STAT_CI = re.compile(
    r"(?:\d+%?\s*(?:CI|confidence\s+interval)\s*[=:]?\s*)"
    r"\[?\s*[-+]?\d+\.?\d*\s*[,–-]\s*[-+]?\d+\.?\d*\s*\]?"
)


def _extract_citations(text: str, section: str) -> Iterator[Claim]:
    """Extract citation claims from text."""
    # Citations with associated claims
    for m in _CITE_WITH_CLAIM.finditer(text):
        authors_str, year, claim_text = m.group(1), m.group(2), m.group(3)
        authors = [a.strip() for a in re.split(r"\s+(?:and|&)\s+", authors_str)]
        yield Claim(
            id=_next_id(),
            text=m.group(0).strip(),
            claim_type=ClaimType.CITATION,
            location=SourceLocation(section=section, sentence=m.group(0).strip()),
            cited_authors=authors,
            cited_year=year,
        )

    # Inline citations (without explicit claim verb)
    seen_cites = set()
    for pattern in (_INLINE_CITE, _PAREN_CITE):
        for m in pattern.finditer(text):
            authors_str, year = m.group(1), m.group(2)
            key = (authors_str.lower(), year)
            if key in seen_cites:
                continue
            seen_cites.add(key)
            authors = [a.strip() for a in re.split(r"\s+(?:and|&)\s+", authors_str)]
            # Get surrounding context (±100 chars)
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 100)
            context = text[start:end]
            yield Claim(
                id=_next_id(),
                text=m.group(0).strip(),
                claim_type=ClaimType.CITATION,
                location=SourceLocation(section=section, context=context),
                cited_authors=authors,
                cited_year=year,
            )


def _extract_quantitative(text: str, section: str) -> Iterator[Claim]:
    """Extract quantitative claims from text."""
    for m in _DOLLAR_CLAIM.finditer(text):
        value_str = m.group(1).replace(",", "")
        unit = m.group(2) or "USD"
        # Get context
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 80)
        context = text[start:end]
        yield Claim(
            id=_next_id(),
            text=m.group(0).strip(),
            claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(section=section, context=context),
            value=float(value_str),
            unit=f"${unit}",
        )

    for m in _QUANTITY_CLAIM.finditer(text):
        value_str = m.group(1)
        unit = m.group(2)
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 80)
        context = text[start:end]
        yield Claim(
            id=_next_id(),
            text=m.group(0).strip(),
            claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(section=section, context=context),
            value=float(value_str),
            unit=unit,
        )

    for m in _NUMBER_CONTEXT.finditer(text):
        value_str = m.group(1).replace(",", "")
        unit = m.group(2) or ""
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 80)
        context = text[start:end]
        yield Claim(
            id=_next_id(),
            text=m.group(0).strip(),
            claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(section=section, context=context),
            value=float(value_str),
            unit=unit,
        )


def _extract_statistical(text: str, section: str) -> Iterator[Claim]:
    """Extract statistical claims from text."""
    for pattern in (_STAT_PVALUE, _STAT_TEST, _STAT_CI):
        for m in pattern.finditer(text):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            context = text[start:end]
            yield Claim(
                id=_next_id(),
                text=m.group(0).strip(),
                claim_type=ClaimType.STATISTICAL,
                location=SourceLocation(section=section, context=context),
            )


def extract_claims(text: str, section: str = "") -> list[Claim]:
    """Extract all verifiable claims from a text block.

    Args:
        text: The text to analyze.
        section: The section heading for location tracking.

    Returns:
        List of extracted claims.
    """
    claims = []
    claims.extend(_extract_citations(text, section))
    claims.extend(_extract_quantitative(text, section))
    claims.extend(_extract_statistical(text, section))
    return claims


def extract_claims_from_document(
    sections: list[tuple[str, str]],
) -> list[Claim]:
    """Extract claims from multiple document sections.

    Args:
        sections: List of (heading, text) tuples.

    Returns:
        All claims extracted across sections.
    """
    reset_counter()
    all_claims = []
    for heading, text in sections:
        all_claims.extend(extract_claims(text, section=heading))
    return all_claims
