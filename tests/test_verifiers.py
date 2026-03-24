"""Tests for verifiers (unit tests with mocked API calls)."""

import pytest

from sciaudit.models import Claim, ClaimType, Severity, SourceLocation, VerificationStatus
from sciaudit.verifiers.citation import CitationVerifier, _title_similarity, _author_surname_match
from sciaudit.verifiers.data import DataVerifier, _match_indicator, _match_country, _parse_year_quarter


class TestTitleSimilarity:
    def test_exact_match(self):
        assert _title_similarity("Oil and the Macroeconomy", "Oil and the Macroeconomy") == 1.0

    def test_case_insensitive(self):
        assert _title_similarity("oil and the macroeconomy", "Oil and the Macroeconomy") == 1.0

    def test_no_match(self):
        assert _title_similarity("Oil prices", "Machine learning fundamentals") < 0.5

    def test_partial_match(self):
        score = _title_similarity(
            "What is an oil shock?",
            "What is an oil shock? Some thoughts on identification"
        )
        assert 0.5 < score < 1.0


class TestAuthorMatch:
    def test_single_author(self):
        assert _author_surname_match(["Hamilton"], ["James D. Hamilton"]) == 1.0

    def test_multiple_authors(self):
        score = _author_surname_match(
            ["Blanchard", "Galí"],
            ["Olivier Blanchard", "Jordi Galí"]
        )
        assert score == 1.0

    def test_partial_match(self):
        score = _author_surname_match(
            ["Hamilton", "Kilian"],
            ["James Hamilton"]
        )
        assert score == 0.5

    def test_empty(self):
        assert _author_surname_match([], ["Hamilton"]) == 0.0
        assert _author_surname_match(["Hamilton"], []) == 0.0


class TestIndicatorMatching:
    def test_gdp_growth(self):
        assert _match_indicator("GDP growth", "%") == "gdp_growth"

    def test_unemployment(self):
        assert _match_indicator("unemployment rate", "percent") == "unemployment"

    def test_oil_price(self):
        assert _match_indicator("oil price", "$/barrel") == "oil_price_wti"

    def test_brent(self):
        assert _match_indicator("Brent crude", "usd") == "oil_price_brent"

    def test_fed_funds(self):
        assert _match_indicator("federal funds rate", "%") == "fed_funds"

    def test_unknown(self):
        assert _match_indicator("random metric", "units") is None

    def test_inflation(self):
        assert _match_indicator("inflation rate", "%") == "inflation"

    def test_vix(self):
        assert _match_indicator("VIX index", "points") == "vix"


class TestCountryMatching:
    def test_us(self):
        assert _match_country("US") == "US"
        assert _match_country("usa") == "US"
        assert _match_country("United States") == "US"

    def test_chile(self):
        assert _match_country("Chile") == "CL"

    def test_unknown(self):
        assert _match_country("Atlantis") is None


class TestYearQuarterParsing:
    def test_q3_2023(self):
        assert _parse_year_quarter("Q3 2023") == ("2023", "Q3")

    def test_2023_q1(self):
        assert _parse_year_quarter("2023 Q1") == ("2023", "Q1")

    def test_plain_year(self):
        assert _parse_year_quarter("2023") == ("2023", None)

    def test_no_year(self):
        assert _parse_year_quarter("last quarter") == (None, None)

    def test_year_in_sentence(self):
        assert _parse_year_quarter("in the year 2020") == ("2020", None)


class TestCitationVerifierCanVerify:
    def test_citation_claim(self):
        v = CitationVerifier()
        claim = Claim(
            id="C001", text="Hamilton (2003)", claim_type=ClaimType.CITATION,
            location=SourceLocation(), cited_authors=["Hamilton"], cited_year="2003",
        )
        assert v.can_verify(claim) is True

    def test_quantitative_claim(self):
        v = CitationVerifier()
        claim = Claim(
            id="C002", text="GDP was 3.2%", claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(),
        )
        assert v.can_verify(claim) is False


class TestDataVerifierCanVerify:
    def test_quantitative_with_entity(self):
        v = DataVerifier()
        claim = Claim(
            id="C003", text="GDP growth was 3.2%", claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(), entity="GDP growth", value=3.2, unit="%",
        )
        assert v.can_verify(claim) is True

    def test_quantitative_no_entity(self):
        v = DataVerifier()
        claim = Claim(
            id="C004", text="3.2%", claim_type=ClaimType.QUANTITATIVE,
            location=SourceLocation(), value=3.2,
        )
        assert v.can_verify(claim) is False
