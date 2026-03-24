"""Main audit pipeline — orchestrates parsing, extraction, verification, and reporting."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sciaudit.extractor import extract_claims_from_document
from sciaudit.models import AuditReport, Claim, ClaimType, VerificationResult, VerificationStatus, Severity
from sciaudit.parsers.html_parser import ParsedDocument, parse_html
from sciaudit.parsers.markdown_parser import parse_markdown
from sciaudit.report import generate_html_report, generate_json_report
from sciaudit.verifiers.citation import CitationVerifier
from sciaudit.verifiers.data import DataVerifier


def parse_document(path: str | Path) -> ParsedDocument:
    """Parse a document file into structured form.

    Supports .html and .md files.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    if path.suffix.lower() in (".html", ".htm"):
        return parse_html(content)
    elif path.suffix.lower() in (".md", ".markdown"):
        return parse_markdown(content)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}. Supported: .html, .md")


def extract_claims(doc: ParsedDocument) -> list[Claim]:
    """Extract all verifiable claims from a parsed document."""
    sections = [(s.heading, s.text) for s in doc.sections]
    return extract_claims_from_document(sections)


async def verify_claims(
    claims: list[Claim],
    fred_api_key: str = "",
    email: str = "sciaudit@verification.local",
    concurrency: int = 5,
) -> list[VerificationResult]:
    """Verify a list of claims against available data sources.

    Args:
        claims: Claims to verify.
        fred_api_key: FRED API key for data verification.
        email: Email for Crossref polite pool.
        concurrency: Max concurrent API calls.

    Returns:
        List of verification results.
    """
    citation_verifier = CitationVerifier(email=email)
    data_verifier = DataVerifier(fred_api_key=fred_api_key)
    semaphore = asyncio.Semaphore(concurrency)

    async def _verify_one(claim: Claim) -> VerificationResult:
        async with semaphore:
            if claim.claim_type == ClaimType.CITATION and citation_verifier.can_verify(claim):
                return await citation_verifier.verify(claim)
            elif data_verifier.can_verify(claim):
                return await data_verifier.verify(claim)
            else:
                return VerificationResult(
                    claim=claim,
                    status=VerificationStatus.UNVERIFIABLE,
                    severity=Severity.INFO,
                    explanation=f"No verifier available for claim type: {claim.claim_type.value}",
                    verified_by="none",
                )

    results = await asyncio.gather(*[_verify_one(c) for c in claims])
    return list(results)


async def run_audit(
    document_path: str | Path,
    output_dir: str | Path | None = None,
    fred_api_key: str = "",
    email: str = "sciaudit@verification.local",
    concurrency: int = 5,
) -> AuditReport:
    """Run a complete audit on a document.

    Args:
        document_path: Path to the document file (.html or .md).
        output_dir: Directory for output reports. Defaults to same dir as document.
        fred_api_key: FRED API key.
        email: Email for Crossref.
        concurrency: Max concurrent API calls.

    Returns:
        AuditReport with all results.
    """
    document_path = Path(document_path)
    if output_dir is None:
        output_dir = document_path.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse
    doc = parse_document(document_path)

    # 2. Extract claims
    claims = extract_claims(doc)

    # 3. Verify
    results = await verify_claims(
        claims, fred_api_key=fred_api_key, email=email, concurrency=concurrency
    )

    # 4. Build report
    report = AuditReport(
        document_path=str(document_path),
        document_title=doc.title,
        results=results,
    )
    report.compute_summary()

    # 5. Generate outputs
    stem = document_path.stem
    generate_html_report(report, output_dir / f"{stem}_audit.html")
    generate_json_report(report, output_dir / f"{stem}_audit.json")

    return report
