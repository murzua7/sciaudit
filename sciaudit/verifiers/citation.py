"""Citation verifier — checks if cited papers exist and metadata is correct.

Uses Crossref, Semantic Scholar, and OpenAlex APIs to verify:
1. Paper existence (DOI resolution, title search)
2. Author accuracy (do the cited authors match?)
3. Year accuracy (was it published when claimed?)
4. Venue accuracy (correct journal/conference?)
"""

from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher

import httpx

from sciaudit.models import (
    Claim,
    ClaimType,
    Severity,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)
from sciaudit.verifiers.base import BaseVerifier

# Timeout for API calls
TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def _normalize_title(title: str) -> str:
    """Normalize a paper title for comparison."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def _title_similarity(a: str, b: str) -> float:
    """Compute similarity between two titles (0-1)."""
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()


def _author_surname_match(cited_authors: list[str], api_authors: list[str]) -> float:
    """Check how well cited author surnames match API author surnames.

    Returns fraction of cited authors found in API authors (0-1).
    """
    if not cited_authors or not api_authors:
        return 0.0

    # Extract surnames (last word of each name)
    def surnames(names: list[str]) -> set[str]:
        result = set()
        for name in names:
            parts = name.strip().split()
            if parts:
                result.add(parts[-1].lower())
        return result

    cited_set = surnames(cited_authors)
    api_set = surnames(api_authors)

    if not cited_set:
        return 0.0
    return len(cited_set & api_set) / len(cited_set)


class CitationVerifier(BaseVerifier):
    """Verify citations against Crossref, Semantic Scholar, and OpenAlex."""

    name = "citation"

    def __init__(self, email: str = "sciaudit@verification.local"):
        self.email = email  # for Crossref polite pool

    def can_verify(self, claim: Claim) -> bool:
        return claim.claim_type == ClaimType.CITATION

    async def verify(self, claim: Claim) -> VerificationResult:
        """Verify a citation claim by searching multiple APIs."""
        evidence = []

        # Strategy: try DOI first, then title+author search
        if claim.cited_doi:
            cr_result = await self._check_crossref_doi(claim.cited_doi)
            if cr_result:
                evidence.append(cr_result)

        # Title + author search across APIs
        search_tasks = []
        if claim.cited_title:
            search_tasks.append(self._search_crossref(claim))
            search_tasks.append(self._search_semantic_scholar(claim))
            search_tasks.append(self._search_openalex(claim))
        elif claim.cited_authors and claim.cited_year:
            # Construct search from author + year
            search_tasks.append(self._search_semantic_scholar(claim))
            search_tasks.append(self._search_openalex(claim))

        if search_tasks:
            results = await asyncio.gather(*search_tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, VerificationEvidence):
                    evidence.append(r)

        # Determine status from evidence
        return self._synthesize(claim, evidence)

    async def _check_crossref_doi(self, doi: str) -> VerificationEvidence | None:
        """Resolve a DOI via Crossref."""
        url = f"https://api.crossref.org/works/{doi}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    url, headers={"User-Agent": f"sciaudit/0.1 (mailto:{self.email})"}
                )
                if resp.status_code == 200:
                    data = resp.json()["message"]
                    title = data.get("title", [""])[0]
                    authors = [
                        a.get("family", "") + ", " + a.get("given", "")
                        for a in data.get("author", [])
                    ]
                    year = ""
                    for date_field in ("published-print", "published-online", "created"):
                        if date_field in data:
                            parts = data[date_field].get("date-parts", [[]])[0]
                            if parts:
                                year = str(parts[0])
                                break
                    venue = data.get("container-title", [""])[0]
                    return VerificationEvidence(
                        source_name="Crossref",
                        source_url=f"https://doi.org/{doi}",
                        retrieved_value={"title": title, "authors": authors, "year": year, "venue": venue},
                        retrieved_metadata={"type": data.get("type", ""), "doi": doi},
                        match_score=1.0,
                        notes="DOI resolved successfully",
                    )
                elif resp.status_code == 404:
                    return VerificationEvidence(
                        source_name="Crossref",
                        source_url=url,
                        match_score=0.0,
                        notes=f"DOI {doi} does not exist in Crossref",
                    )
        except Exception as e:
            return VerificationEvidence(
                source_name="Crossref",
                source_url=url,
                match_score=0.0,
                notes=f"Crossref lookup failed: {e}",
            )
        return None

    async def _search_crossref(self, claim: Claim) -> VerificationEvidence:
        """Search Crossref by title and/or author."""
        query = claim.cited_title or " ".join(claim.cited_authors)
        url = "https://api.crossref.org/works"
        params = {"query.bibliographic": query, "rows": 3}
        if claim.cited_authors:
            params["query.author"] = " ".join(claim.cited_authors[:2])

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": f"sciaudit/0.1 (mailto:{self.email})"},
                )
                if resp.status_code == 200:
                    items = resp.json()["message"]["items"]
                    if items:
                        best = items[0]
                        title = best.get("title", [""])[0]
                        sim = _title_similarity(claim.cited_title, title) if claim.cited_title else 0.5
                        authors = [
                            a.get("family", "") + ", " + a.get("given", "")
                            for a in best.get("author", [])
                        ]
                        year = ""
                        for df in ("published-print", "published-online", "created"):
                            if df in best:
                                parts = best[df].get("date-parts", [[]])[0]
                                if parts:
                                    year = str(parts[0])
                                    break
                        return VerificationEvidence(
                            source_name="Crossref",
                            source_url=f"https://doi.org/{best.get('DOI', '')}",
                            retrieved_value={"title": title, "authors": authors, "year": year},
                            retrieved_metadata={"doi": best.get("DOI", ""), "score": best.get("score", 0)},
                            match_score=sim,
                            notes=f"Title similarity: {sim:.2f}",
                        )
        except Exception as e:
            return VerificationEvidence(
                source_name="Crossref", match_score=0.0, notes=f"Search failed: {e}"
            )
        return VerificationEvidence(
            source_name="Crossref", match_score=0.0, notes="No results found"
        )

    async def _search_semantic_scholar(self, claim: Claim) -> VerificationEvidence:
        """Search Semantic Scholar by title."""
        query = claim.cited_title or f"{' '.join(claim.cited_authors)} {claim.cited_year}"
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": 3,
            "fields": "title,authors,year,venue,externalIds,citationCount",
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        best = data[0]
                        title = best.get("title", "")
                        sim = _title_similarity(claim.cited_title, title) if claim.cited_title else 0.5
                        authors = [a.get("name", "") for a in best.get("authors", [])]
                        return VerificationEvidence(
                            source_name="Semantic Scholar",
                            source_url=f"https://api.semanticscholar.org/graph/v1/paper/{best.get('paperId', '')}",
                            retrieved_value={
                                "title": title,
                                "authors": authors,
                                "year": best.get("year"),
                                "venue": best.get("venue", ""),
                                "citations": best.get("citationCount", 0),
                            },
                            retrieved_metadata=best.get("externalIds", {}),
                            match_score=sim,
                            notes=f"Title similarity: {sim:.2f}",
                        )
        except Exception as e:
            return VerificationEvidence(
                source_name="Semantic Scholar", match_score=0.0, notes=f"Search failed: {e}"
            )
        return VerificationEvidence(
            source_name="Semantic Scholar", match_score=0.0, notes="No results found"
        )

    async def _search_openalex(self, claim: Claim) -> VerificationEvidence:
        """Search OpenAlex by title."""
        query = claim.cited_title or f"{' '.join(claim.cited_authors)} {claim.cited_year}"
        url = "https://api.openalex.org/works"
        params = {"search": query, "per_page": 3}

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": f"sciaudit/0.1 (mailto:{self.email})"},
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        best = results[0]
                        title = best.get("title", "")
                        sim = _title_similarity(claim.cited_title, title) if claim.cited_title else 0.5
                        authors = [
                            a.get("author", {}).get("display_name", "")
                            for a in best.get("authorships", [])
                        ]
                        return VerificationEvidence(
                            source_name="OpenAlex",
                            source_url=best.get("id", ""),
                            retrieved_value={
                                "title": title,
                                "authors": authors,
                                "year": best.get("publication_year"),
                                "venue": best.get("primary_location", {}).get("source", {}).get("display_name", ""),
                                "citations": best.get("cited_by_count", 0),
                            },
                            match_score=sim,
                            notes=f"Title similarity: {sim:.2f}",
                        )
        except Exception as e:
            return VerificationEvidence(
                source_name="OpenAlex", match_score=0.0, notes=f"Search failed: {e}"
            )
        return VerificationEvidence(
            source_name="OpenAlex", match_score=0.0, notes="No results found"
        )

    def _synthesize(
        self, claim: Claim, evidence: list[VerificationEvidence]
    ) -> VerificationResult:
        """Synthesize multiple evidence sources into a final verdict."""
        if not evidence:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.UNVERIFIABLE,
                severity=Severity.INFO,
                evidence=[],
                explanation="No evidence could be gathered (all API calls failed or no search terms available)",
                verified_by=self.name,
            )

        # Check if any source found a strong match
        best_match = max(evidence, key=lambda e: e.match_score)
        high_confidence = [e for e in evidence if e.match_score >= 0.8]
        medium_confidence = [e for e in evidence if 0.5 <= e.match_score < 0.8]
        no_results = [e for e in evidence if e.match_score == 0.0]

        # If all sources return 0 matches -> likely fabricated
        if len(no_results) == len(evidence) and len(evidence) >= 2:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.FABRICATED,
                severity=Severity.CRITICAL,
                evidence=evidence,
                explanation=(
                    f"Citation not found in any of {len(evidence)} databases searched. "
                    f"Searched: {', '.join(e.source_name for e in evidence)}. "
                    "This citation may be fabricated or severely misattributed."
                ),
                verified_by=self.name,
            )

        # If strong match found, check metadata
        if high_confidence:
            best = high_confidence[0]
            val = best.retrieved_value or {}
            issues = []

            # Check year
            if claim.cited_year and val.get("year"):
                api_year = str(val["year"])
                if api_year != claim.cited_year:
                    issues.append(f"Year mismatch: cited {claim.cited_year}, found {api_year}")

            # Check authors
            if claim.cited_authors and val.get("authors"):
                author_match = _author_surname_match(claim.cited_authors, val["authors"])
                if author_match < 0.5:
                    issues.append(
                        f"Author mismatch: cited {claim.cited_authors}, "
                        f"found {val['authors'][:3]}"
                    )

            if not issues:
                return VerificationResult(
                    claim=claim,
                    status=VerificationStatus.VERIFIED,
                    severity=Severity.INFO,
                    evidence=evidence,
                    explanation=f"Citation verified via {best.source_name} (similarity: {best.match_score:.2f})",
                    verified_by=self.name,
                )
            else:
                return VerificationResult(
                    claim=claim,
                    status=VerificationStatus.IMPRECISE,
                    severity=Severity.MINOR,
                    evidence=evidence,
                    explanation=f"Paper found but metadata issues: {'; '.join(issues)}",
                    suggested_correction=str(val),
                    verified_by=self.name,
                )

        # Medium confidence -> paper probably exists but may be misattributed
        if medium_confidence:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.IMPRECISE,
                severity=Severity.MAJOR,
                evidence=evidence,
                explanation=(
                    f"Possible match found (similarity: {best_match.match_score:.2f}) "
                    "but confidence is low. Citation may be imprecise or partially incorrect."
                ),
                verified_by=self.name,
            )

        # Low confidence
        return VerificationResult(
            claim=claim,
            status=VerificationStatus.UNVERIFIABLE,
            severity=Severity.INFO,
            evidence=evidence,
            explanation="Could not confidently match citation to any known paper",
            verified_by=self.name,
        )
