"""Tests for the academic journal quality evaluator."""

import pytest

from sciaudit.evaluator import (
    ECON_TOP5,
    FINANCE_TOP3,
    ML_TOP,
    VENUE_PROFILES,
    evaluate_citations,
    evaluate_document,
    evaluate_identification,
    evaluate_reproducibility,
    evaluate_statistical_rigor,
    evaluate_structure,
    evaluate_writing_quality,
)
from sciaudit.parsers.html_parser import ParsedDocument, Section


def _make_doc(
    title: str = "Test Paper",
    sections: list[tuple[str, str]] | None = None,
    full_text: str = "",
    references: list[str] | None = None,
) -> ParsedDocument:
    """Helper to create a ParsedDocument for testing."""
    if sections is None:
        sections = []
    sec_objs = [Section(heading=h, level=2, text=t) for h, t in sections]
    if not full_text:
        full_text = " ".join(t for _, t in sections)
    return ParsedDocument(
        title=title,
        sections=sec_objs,
        full_text=full_text,
        references=references or [],
        footnotes=[],
    )


class TestVenueProfiles:
    def test_all_profiles_exist(self):
        assert "econ_top5" in VENUE_PROFILES
        assert "ml_top" in VENUE_PROFILES
        assert "finance_top3" in VENUE_PROFILES
        assert "general" in VENUE_PROFILES

    def test_journal_aliases(self):
        assert VENUE_PROFILES["aer"] is ECON_TOP5
        assert VENUE_PROFILES["neurips"] is ML_TOP
        assert VENUE_PROFILES["jf"] is FINANCE_TOP3

    def test_econ_requires_identification(self):
        assert ECON_TOP5.requires_identification is True
        assert ECON_TOP5.requires_standard_errors is True

    def test_ml_requires_ablations(self):
        assert ML_TOP.requires_ablations is True
        assert ML_TOP.requires_error_bars is True
        assert ML_TOP.requires_compute_budget is True

    def test_finance_requires_endogeneity(self):
        assert FINANCE_TOP3.requires_endogeneity_discussion is True


class TestStructureEvaluation:
    def test_complete_econ_paper(self):
        doc = _make_doc(sections=[
            ("Abstract", (
                "We study the causal effect of oil supply shocks on GDP growth using a "
                "difference-in-differences design exploiting exogenous variation in OPEC "
                "production quotas. Using quarterly data from 1970 to 2020 for 30 OECD "
                "countries, we find that a 10 percent increase in oil prices reduces GDP "
                "growth by 0.3 percentage points. Our results are robust to alternative "
                "specifications, placebo tests, and instrumental variable estimation. "
                "We contribute to the literature by providing credible causal estimates "
                "of oil-macro transmission that account for endogenous supply responses."
            )),
            ("Introduction", "Oil prices matter for the economy."),
            ("Data", "We use FRED data from 2000-2020."),
            ("Empirical Strategy", "We employ a difference-in-differences design."),
            ("Results", "We find significant effects."),
            ("Conclusion", "Oil shocks matter."),
            ("Limitations", "Our study has several limitations."),
        ])
        score = evaluate_structure(doc, ECON_TOP5)
        assert score.score >= 4

    def test_missing_sections(self):
        doc = _make_doc(sections=[
            ("Introduction", "Some intro."),
        ])
        score = evaluate_structure(doc, ECON_TOP5)
        assert score.score <= 3
        assert any("Missing" in f for f in score.findings)

    def test_short_abstract(self):
        doc = _make_doc(sections=[
            ("Abstract", "Short."),
            ("Introduction", "Intro."),
            ("Method", "Method."),
            ("Results", "Results."),
            ("Conclusion", "Done."),
        ])
        score = evaluate_structure(doc, ML_TOP)
        assert any("Abstract too short" in f for f in score.findings)


class TestCitationEvaluation:
    def test_adequate_citations(self):
        refs = [f"Author{i} ({2020+i%5}). Title. Journal." for i in range(50)]
        doc = _make_doc(
            sections=[("References", "\n".join(refs))],
            references=refs,
            full_text="Hamilton (2023) and Kilian (2024) studied this. " * 20,
        )
        score = evaluate_citations(doc, ECON_TOP5)
        assert score.score >= 4

    def test_too_few_citations(self):
        refs = [f"Author{i} (2020). Title. Journal." for i in range(5)]
        doc = _make_doc(references=refs)
        score = evaluate_citations(doc, ECON_TOP5)
        assert score.score <= 3
        assert any("Only 5 references" in f for f in score.findings)

    def test_no_citations(self):
        doc = _make_doc()
        score = evaluate_citations(doc, ML_TOP)
        assert score.score == 1


class TestStatisticalRigor:
    def test_econ_with_se_and_robustness(self):
        doc = _make_doc(full_text=(
            "We report heteroskedasticity-robust standard errors. "
            "The effect size is 0.3 standard deviations. "
            "We conduct robustness checks using alternative specifications. "
            "Placebo tests confirm our results. "
            "Sensitivity analysis shows stability."
        ))
        score = evaluate_statistical_rigor(doc, ECON_TOP5)
        assert score.score >= 4

    def test_ml_without_ablations(self):
        doc = _make_doc(full_text="We train a model and report results.")
        score = evaluate_statistical_rigor(doc, ML_TOP)
        assert score.score <= 3
        assert any("ablation" in f.lower() for f in score.findings)

    def test_ml_with_everything(self):
        doc = _make_doc(full_text=(
            "We report mean ± standard deviation across 5 random seeds. "
            "Our ablation study removes each component. "
            "Robustness checks show sensitivity to hyperparameters. "
            "Alternative specifications confirm findings."
        ))
        score = evaluate_statistical_rigor(doc, ML_TOP)
        assert score.score >= 4


class TestIdentification:
    def test_strong_identification(self):
        doc = _make_doc(full_text=(
            "We use a difference-in-differences design exploiting the natural experiment. "
            "We address endogeneity concerns from omitted variables and reverse causality. "
            "The exclusion restriction is satisfied because... "
            "Our instrument is exogenous to the outcome."
        ))
        score = evaluate_identification(doc, ECON_TOP5)
        assert score.score >= 4

    def test_no_identification(self):
        doc = _make_doc(full_text="We run OLS regressions of Y on X.")
        score = evaluate_identification(doc, ECON_TOP5)
        assert score.score <= 2
        assert any("No identification strategy" in f for f in score.findings)

    def test_not_applicable_for_ml(self):
        doc = _make_doc(full_text="We train a neural network.")
        score = evaluate_identification(doc, ML_TOP)
        assert score.score == 5  # N/A for ML


class TestReproducibility:
    def test_ml_with_compute(self):
        doc = _make_doc(full_text=(
            "Code is available at github.com/example/repo. "
            "Data is available in the supplementary material. "
            "We used 4 NVIDIA A100 GPUs with training time of 8 hours. "
            "We compare against state-of-the-art baselines."
        ))
        score = evaluate_reproducibility(doc, ML_TOP)
        assert score.score >= 4

    def test_ml_missing_compute(self):
        doc = _make_doc(full_text="We trained a model.")
        score = evaluate_reproducibility(doc, ML_TOP)
        assert score.score <= 3
        assert any("compute" in f.lower() for f in score.findings)

    def test_econ_with_replication(self):
        doc = _make_doc(full_text=(
            "All data and replication code are available at the AEA repository. "
            "We provide Stata do-files for all results."
        ))
        score = evaluate_reproducibility(doc, ECON_TOP5)
        assert score.score >= 4


class TestWritingQuality:
    def test_limitations_present(self):
        doc = _make_doc(full_text=(
            "Our study has several limitations. "
            "Future work should extend the analysis."
        ))
        score = evaluate_writing_quality(doc, ECON_TOP5)
        assert not any("No limitations" in f for f in score.findings)

    def test_missing_broader_impact(self):
        doc = _make_doc(full_text="We train a model that works well.")
        score = evaluate_writing_quality(doc, ML_TOP)
        assert any("broader impact" in f.lower() for f in score.findings)


class TestFullEvaluation:
    def test_end_to_end_general(self):
        doc = _make_doc(
            title="Test Paper",
            sections=[
                ("Abstract", "We study X and find Y using method Z. " * 5),
                ("Introduction", "This paper contributes to the literature. " * 10),
                ("Related Work", "Prior studies include Hamilton (2023) and Kilian (2024)."),
                ("Method", "We propose a novel approach."),
                ("Experiments", "We compare against baselines."),
                ("Conclusion", "Our method works."),
                ("Limitations", "This study has limitations. Future work is needed."),
            ],
            references=[f"Ref{i} (202{i%5}). Title. Venue." for i in range(25)],
            full_text=(
                "We study X. Hamilton (2023) found Y. Kilian (2024) showed Z. "
                "We compare against state-of-the-art baselines. "
                "Code is available on github. "
                "Our study has limitations. Future work should extend. "
            ) * 10,
        )
        report = evaluate_document(doc, venue="general")
        assert report.overall_grade in ("A", "B", "C", "D", "F")
        assert 0 <= report.overall_score <= 1
        assert len(report.dimensions) == 6

    def test_venue_lookup(self):
        doc = _make_doc()
        report = evaluate_document(doc, venue="neurips")
        assert "NeurIPS" in report.venue_profile

    def test_unknown_venue_defaults_to_general(self):
        doc = _make_doc()
        report = evaluate_document(doc, venue="unknown_journal")
        assert "General" in report.venue_profile
