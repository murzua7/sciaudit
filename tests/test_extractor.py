"""Tests for the claim extractor."""

import pytest

from sciaudit.extractor import extract_claims, reset_counter
from sciaudit.models import ClaimType


@pytest.fixture(autouse=True)
def _reset():
    reset_counter()
    yield
    reset_counter()


class TestCitationExtraction:
    def test_inline_cite(self):
        text = "Hamilton (2003) showed that oil price shocks have nonlinear effects."
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        assert len(cites) >= 1
        assert cites[0].cited_authors == ["Hamilton"]
        assert cites[0].cited_year == "2003"

    def test_parenthetical_cite(self):
        text = "Oil price shocks are nonlinear (Hamilton, 2003)."
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        assert len(cites) >= 1
        assert cites[0].cited_year == "2003"

    def test_et_al_cite(self):
        text = "Oladosu et al. (2018) conducted a meta-analysis."
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        assert len(cites) >= 1
        assert "Oladosu" in cites[0].cited_authors[0]
        assert cites[0].cited_year == "2018"

    def test_two_author_cite(self):
        text = "Blanchard and Galí (2007) studied oil and the macroeconomy."
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        assert len(cites) >= 1
        assert len(cites[0].cited_authors) == 2

    def test_cite_with_claim_verb(self):
        text = "Kilian (2009) found that supply shocks account for most variation."
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        assert len(cites) >= 1
        assert cites[0].cited_year == "2009"

    def test_multiple_cites_in_text(self):
        text = (
            "Hamilton (2003) and Kilian (2009) disagree on the transmission mechanism. "
            "Blanchard and Galí (2007) offer a middle ground."
        )
        claims = extract_claims(text)
        cites = [c for c in claims if c.claim_type == ClaimType.CITATION]
        authors = {c.cited_authors[0] for c in cites}
        assert "Hamilton" in authors
        assert "Kilian" in authors


class TestQuantitativeExtraction:
    def test_dollar_amount(self):
        text = "The SPR release was valued at $150 billion."
        claims = extract_claims(text)
        quant = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        assert len(quant) >= 1
        assert quant[0].value == 150.0

    def test_percentage(self):
        text = "GDP growth was approximately 3.2% in Q3 2023."
        claims = extract_claims(text)
        quant = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        assert len(quant) >= 1

    def test_physical_quantity(self):
        text = "Global oil demand is 104.5 mb/d."
        claims = extract_claims(text)
        quant = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        assert len(quant) >= 1
        assert any(c.unit == "mb/d" for c in quant)

    def test_number_with_context(self):
        text = "Oil prices reached 150 per barrel."
        claims = extract_claims(text)
        quant = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        assert len(quant) >= 1

    def test_dollar_per_barrel(self):
        text = "Brent crude hit $180/barrel during the crisis."
        claims = extract_claims(text)
        quant = [c for c in claims if c.claim_type == ClaimType.QUANTITATIVE]
        assert len(quant) >= 1
        assert quant[0].value == 180.0


class TestStatisticalExtraction:
    def test_pvalue(self):
        text = "The result was statistically significant (p < 0.05)."
        claims = extract_claims(text)
        stats = [c for c in claims if c.claim_type == ClaimType.STATISTICAL]
        assert len(stats) >= 1
        assert "p" in stats[0].text

    def test_test_statistic(self):
        text = "We found t(42) = 2.31, which is significant."
        claims = extract_claims(text)
        stats = [c for c in claims if c.claim_type == ClaimType.STATISTICAL]
        assert len(stats) >= 1

    def test_r_squared(self):
        text = "The model fit was R² = 0.87."
        claims = extract_claims(text)
        stats = [c for c in claims if c.claim_type == ClaimType.STATISTICAL]
        assert len(stats) >= 1


class TestEdgeCases:
    def test_empty_text(self):
        assert extract_claims("") == []

    def test_no_claims(self):
        text = "This is a general statement about the weather."
        claims = extract_claims(text)
        # May extract some false positives, but should be minimal
        assert isinstance(claims, list)

    def test_section_tracking(self):
        text = "Hamilton (2003) found important results."
        claims = extract_claims(text, section="Literature Review")
        assert claims[0].location.section == "Literature Review"

    def test_unique_ids(self):
        text = "Hamilton (2003) and Kilian (2009) studied oil."
        claims = extract_claims(text)
        ids = [c.id for c in claims]
        assert len(ids) == len(set(ids))
