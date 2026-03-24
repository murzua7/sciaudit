"""Data models for claims, verification results, and audit reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ClaimType(str, Enum):
    """Classification of extracted claims."""

    QUANTITATIVE = "quantitative"  # "GDP growth was 3.2% in 2023"
    CITATION = "citation"  # "Hamilton (2003) found that..."
    STATISTICAL = "statistical"  # "p < 0.05, t(42) = 2.31"
    COMPARATIVE = "comparative"  # "X is larger than Y"
    CAUSAL = "causal"  # "X causes Y"
    TEMPORAL = "temporal"  # "Since 2008, X has increased"
    DEFINITIONAL = "definitional"  # "The Strait of Hormuz carries 20% of global oil"


class VerificationStatus(str, Enum):
    """Result of verifying a claim."""

    VERIFIED = "verified"  # Confirmed correct against primary source
    INCORRECT = "incorrect"  # Contradicted by primary source
    IMPRECISE = "imprecise"  # Close but not exactly right (e.g., 3.1% vs 3.2%)
    UNVERIFIABLE = "unverifiable"  # Cannot be checked programmatically
    FABRICATED = "fabricated"  # Citation/source does not exist
    UNSUPPORTED = "unsupported"  # Cited source doesn't support the claim
    MISATTRIBUTED = "misattributed"  # Claim attributed to wrong source
    PENDING = "pending"  # Not yet checked


class Severity(str, Enum):
    """Severity of a verification finding."""

    CRITICAL = "critical"  # Fabricated citation, wrong number by >50%
    MAJOR = "major"  # Incorrect data, misattributed claim
    MINOR = "minor"  # Imprecise number, outdated data
    INFO = "info"  # Unverifiable claim (flagged for manual review)


@dataclass
class SourceLocation:
    """Where in the document a claim was found."""

    section: str = ""
    paragraph: int = 0
    sentence: str = ""
    line_number: int | None = None
    context: str = ""  # surrounding text for disambiguation


@dataclass
class Claim:
    """A single verifiable claim extracted from a document."""

    id: str  # unique identifier (e.g., "C001")
    text: str  # the claim as stated in the document
    claim_type: ClaimType
    location: SourceLocation
    # Extracted components for verification
    value: str | float | None = None  # the number/statistic claimed
    unit: str = ""  # %, USD, basis points, etc.
    entity: str = ""  # what the number refers to (GDP, CPI, gold price)
    time_reference: str = ""  # when (Q3 2023, 2008-2019, March 2026)
    geography: str = ""  # where (US, Chile, global)
    cited_source: str = ""  # who said it (Hamilton 2003, FRED, BLS)
    # For citations specifically
    cited_authors: list[str] = field(default_factory=list)
    cited_year: str = ""
    cited_title: str = ""
    cited_doi: str = ""
    cited_venue: str = ""


@dataclass
class VerificationEvidence:
    """Evidence gathered during verification."""

    source_name: str  # "FRED", "Crossref", "Semantic Scholar"
    source_url: str = ""
    retrieved_value: Any = None  # the actual value from the source
    retrieved_metadata: dict[str, Any] = field(default_factory=dict)
    match_score: float = 0.0  # 0.0 to 1.0 confidence in the match
    notes: str = ""


@dataclass
class VerificationResult:
    """Result of verifying a single claim."""

    claim: Claim
    status: VerificationStatus
    severity: Severity
    evidence: list[VerificationEvidence] = field(default_factory=list)
    explanation: str = ""  # human-readable explanation
    suggested_correction: str = ""  # if incorrect, what should it be
    verified_by: str = ""  # which verifier module handled this


@dataclass
class AuditReport:
    """Complete audit report for a document."""

    document_path: str
    document_title: str = ""
    total_claims: int = 0
    results: list[VerificationResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)  # status -> count
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_summary(self) -> None:
        """Compute summary statistics from results."""
        self.total_claims = len(self.results)
        self.summary = {}
        for r in self.results:
            self.summary[r.status.value] = self.summary.get(r.status.value, 0) + 1

    @property
    def critical_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.CRITICAL)

    @property
    def major_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.MAJOR)

    @property
    def score(self) -> float:
        """Audit score: fraction of claims that are verified or info-only."""
        if not self.results:
            return 1.0
        ok = sum(
            1
            for r in self.results
            if r.status in (VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIABLE)
        )
        return ok / len(self.results)
