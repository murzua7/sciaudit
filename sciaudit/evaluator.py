"""Academic journal quality evaluator — scores documents against venue-specific standards.

Evaluates papers on programmatically checkable dimensions:
1. Structure completeness (required sections present)
2. Citation metrics (count, recency, quality via API)
3. Statistical rigor signals (SE, CI, effect sizes, robustness)
4. Identification/causal methodology signals
5. Reproducibility signals (data, code, compute)
6. Writing quality (abstract, hedging, passive voice)
7. Limitations and broader impact
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from sciaudit.parsers.html_parser import ParsedDocument


class VenueType(str, Enum):
    """Academic venue categories."""

    ECON_TOP5 = "econ_top5"  # AER, QJE, JPE, Econometrica, REStud
    ML_TOP = "ml_top"  # NeurIPS, ICML, ICLR
    FINANCE_TOP3 = "finance_top3"  # JF, JFE, RFS
    GENERAL = "general"  # High general standards


@dataclass
class VenueProfile:
    """Expected standards for a venue category."""

    name: str
    venue_type: VenueType
    # Section requirements (lowercase keywords to match)
    required_sections: list[str]
    optional_sections: list[str]
    # Citation norms
    min_references: int
    typical_references: tuple[int, int]  # (low, high) range
    max_citation_age_years: int  # for "recency" check
    min_recent_fraction: float  # fraction of citations from last N years
    # Statistical rigor
    requires_standard_errors: bool
    requires_confidence_intervals: bool
    requires_effect_sizes: bool
    requires_robustness: bool
    requires_multiple_testing_correction: bool
    # Identification
    requires_identification: bool  # causal identification strategy
    requires_endogeneity_discussion: bool
    # Reproducibility
    requires_data_availability: bool
    requires_code: bool
    requires_compute_budget: bool
    # Structure
    max_abstract_words: int
    min_abstract_words: int
    # Writing
    max_passive_voice_fraction: float  # threshold for flagging
    # Specific checklist items
    requires_limitations: bool
    requires_broader_impact: bool
    requires_ablations: bool
    requires_error_bars: bool


# --- Venue profiles ---

ECON_TOP5 = VenueProfile(
    name="Economics Top-5 (AER/QJE/JPE/Econometrica/REStud)",
    venue_type=VenueType.ECON_TOP5,
    required_sections=[
        "introduction", "data", "method", "empirical", "result", "conclusion",
    ],
    optional_sections=[
        "literature", "background", "institutional", "robustness", "extension",
        "discussion", "welfare", "policy", "model",
    ],
    min_references=30,
    typical_references=(40, 70),
    max_citation_age_years=5,
    min_recent_fraction=0.30,
    requires_standard_errors=True,
    requires_confidence_intervals=False,  # increasingly expected but not universal
    requires_effect_sizes=True,
    requires_robustness=True,
    requires_multiple_testing_correction=False,  # depends on design
    requires_identification=True,
    requires_endogeneity_discussion=True,
    requires_data_availability=True,
    requires_code=True,
    requires_compute_budget=False,
    max_abstract_words=200,
    min_abstract_words=80,
    max_passive_voice_fraction=0.30,
    requires_limitations=True,
    requires_broader_impact=False,
    requires_ablations=False,
    requires_error_bars=False,
)

ML_TOP = VenueProfile(
    name="ML Top Venues (NeurIPS/ICML/ICLR)",
    venue_type=VenueType.ML_TOP,
    required_sections=[
        "introduction", "related work", "method", "experiment", "conclusion",
    ],
    optional_sections=[
        "background", "preliminary", "theoretical", "ablation", "discussion",
        "broader impact", "limitation",
    ],
    min_references=20,
    typical_references=(30, 50),
    max_citation_age_years=3,
    min_recent_fraction=0.40,
    requires_standard_errors=False,
    requires_confidence_intervals=False,
    requires_effect_sizes=False,
    requires_robustness=True,
    requires_multiple_testing_correction=False,
    requires_identification=False,
    requires_endogeneity_discussion=False,
    requires_data_availability=True,
    requires_code=True,
    requires_compute_budget=True,
    max_abstract_words=250,
    min_abstract_words=100,
    max_passive_voice_fraction=0.25,
    requires_limitations=True,
    requires_broader_impact=True,
    requires_ablations=True,
    requires_error_bars=True,
)

FINANCE_TOP3 = VenueProfile(
    name="Finance Top-3 (JF/JFE/RFS)",
    venue_type=VenueType.FINANCE_TOP3,
    required_sections=[
        "introduction", "data", "method", "empirical", "result", "conclusion",
    ],
    optional_sections=[
        "literature", "hypothesis", "robustness", "extension", "internet appendix",
    ],
    min_references=30,
    typical_references=(40, 60),
    max_citation_age_years=5,
    min_recent_fraction=0.25,
    requires_standard_errors=True,
    requires_confidence_intervals=False,
    requires_effect_sizes=True,
    requires_robustness=True,
    requires_multiple_testing_correction=False,
    requires_identification=True,
    requires_endogeneity_discussion=True,
    requires_data_availability=True,
    requires_code=False,  # growing but not yet universal
    requires_compute_budget=False,
    max_abstract_words=200,
    min_abstract_words=80,
    max_passive_voice_fraction=0.30,
    requires_limitations=True,
    requires_broader_impact=False,
    requires_ablations=False,
    requires_error_bars=False,
)

GENERAL = VenueProfile(
    name="High General Standards",
    venue_type=VenueType.GENERAL,
    required_sections=[
        "introduction", "method", "result", "conclusion",
    ],
    optional_sections=[
        "related work", "background", "data", "discussion", "limitation",
    ],
    min_references=15,
    typical_references=(20, 50),
    max_citation_age_years=5,
    min_recent_fraction=0.20,
    requires_standard_errors=False,
    requires_confidence_intervals=False,
    requires_effect_sizes=False,
    requires_robustness=True,
    requires_multiple_testing_correction=False,
    requires_identification=False,
    requires_endogeneity_discussion=False,
    requires_data_availability=True,
    requires_code=False,
    requires_compute_budget=False,
    max_abstract_words=300,
    min_abstract_words=50,
    max_passive_voice_fraction=0.35,
    requires_limitations=True,
    requires_broader_impact=False,
    requires_ablations=False,
    requires_error_bars=False,
)

VENUE_PROFILES: dict[str, VenueProfile] = {
    "econ_top5": ECON_TOP5,
    "ml_top": ML_TOP,
    "finance_top3": FINANCE_TOP3,
    "general": GENERAL,
    # Convenience aliases
    "aer": ECON_TOP5, "qje": ECON_TOP5, "jpe": ECON_TOP5,
    "econometrica": ECON_TOP5, "restud": ECON_TOP5,
    "neurips": ML_TOP, "icml": ML_TOP, "iclr": ML_TOP,
    "jf": FINANCE_TOP3, "jfe": FINANCE_TOP3, "rfs": FINANCE_TOP3,
}


# --- Evaluation dimension scores ---

@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""

    name: str
    score: int  # 1-5 (5=excellent, 1=poor)
    max_score: int = 5
    findings: list[str] = field(default_factory=list)  # specific issues
    recommendations: list[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    """Complete evaluation report."""

    venue: str
    venue_profile: str
    dimensions: list[DimensionScore]
    overall_score: float = 0.0  # weighted average
    overall_grade: str = ""  # A/B/C/D/F
    ready_for_submission: bool = False
    blockers: list[str] = field(default_factory=list)  # must-fix before submission
    suggestions: list[str] = field(default_factory=list)  # nice-to-have

    def compute_overall(self) -> None:
        if not self.dimensions:
            return
        self.overall_score = sum(d.score for d in self.dimensions) / sum(
            d.max_score for d in self.dimensions
        )
        # Grade
        if self.overall_score >= 0.90:
            self.overall_grade = "A"
        elif self.overall_score >= 0.80:
            self.overall_grade = "B"
        elif self.overall_score >= 0.65:
            self.overall_grade = "C"
        elif self.overall_score >= 0.50:
            self.overall_grade = "D"
        else:
            self.overall_grade = "F"
        # Submission readiness: no dimension below 3, overall >= B
        self.ready_for_submission = (
            all(d.score >= 3 for d in self.dimensions)
            and self.overall_score >= 0.75
        )
        # Blockers
        self.blockers = []
        for d in self.dimensions:
            if d.score <= 2:
                self.blockers.append(f"{d.name}: score {d.score}/5 — {'; '.join(d.findings[:2])}")


# --- Keyword patterns for detection ---

# Identification strategies
_IDENTIFICATION_KEYWORDS = [
    r"\b(?:instrumental\s+variable|IV|2SLS|two-stage)\b",
    r"\b(?:difference-in-differences?|DiD|diff-in-diff)\b",
    r"\b(?:regression\s+discontinuity|RDD|RD\s+design)\b",
    r"\b(?:randomized?\s+control(?:led)?\s+trial|RCT)\b",
    r"\b(?:natural\s+experiment|quasi-experiment)\b",
    r"\b(?:propensity\s+score|matching\s+estimator)\b",
    r"\b(?:synthetic\s+control)\b",
    r"\b(?:event\s+study|staggered\s+adoption)\b",
    r"\b(?:Bartik\s+instrument|shift-share)\b",
]

# Robustness check signals
_ROBUSTNESS_KEYWORDS = [
    r"\b(?:robustness|robust\s+(?:check|test|to))\b",
    r"\b(?:sensitivity\s+analysis|sensitivity\s+to)\b",
    r"\b(?:placebo\s+(?:test|check|regression))\b",
    r"\b(?:falsification\s+test)\b",
    r"\b(?:alternative\s+specification|alternative\s+measure)\b",
    r"\b(?:subsample\s+analysis)\b",
    r"\b(?:Oster\s+bounds?|selection\s+on\s+observables)\b",
    r"\b(?:leave-one-out|jackknife|bootstrap)\b",
    r"\b(?:permutation\s+test)\b",
]

# Statistical rigor signals
_STAT_RIGOR_KEYWORDS = {
    "standard_errors": [
        r"\b(?:standard\s+error|s\.e\.|SE|robust\s+(?:standard\s+)?error)\b",
        r"\b(?:heteroskedasticity|heteroscedasticity)\b",
        r"\b(?:clustered?\s+(?:standard\s+)?error)\b",
        r"\b(?:Newey-West|HAC)\b",
    ],
    "confidence_intervals": [
        r"\b(?:confidence\s+interval|CI|credible\s+interval)\b",
        r"\b\d+%\s*(?:CI|confidence)\b",
    ],
    "effect_sizes": [
        r"\b(?:effect\s+size|Cohen.s\s+d|standardized?\s+coefficient)\b",
        r"\b(?:standard\s+deviation\s+(?:increase|decrease|change))\b",
        r"\b(?:economic(?:ally)?\s+significant|magnitude)\b",
    ],
    "multiple_testing": [
        r"\b(?:Bonferroni|BH|Benjamini|Holm|FDR|FWER)\b",
        r"\b(?:multiple\s+(?:hypothesis|testing|comparison))\b",
        r"\b(?:family-wise\s+error)\b",
    ],
}

# Reproducibility signals
_REPRO_KEYWORDS = {
    "data_availability": [
        r"\b(?:data\s+(?:available|availability|deposited|repository))\b",
        r"\b(?:replication\s+(?:package|files?|code))\b",
        r"\b(?:supplementary?\s+(?:data|material))\b",
    ],
    "code": [
        r"\b(?:code\s+(?:available|repository|provided))\b",
        r"\b(?:github|gitlab|bitbucket)\b",
        r"\b(?:open[\s-]?source)\b",
        r"\b(?:python|R|Stata|MATLAB|Julia)\b",
    ],
    "compute": [
        r"\b(?:GPU|TPU|CPU|CUDA|A100|V100|T4|RTX)\b",
        r"\b(?:compute\s+(?:budget|resource|time|cost))\b",
        r"\b(?:training\s+(?:time|hours?|wall[\s-]?clock))\b",
        r"\b(?:FLOP|parameter\s+count)\b",
    ],
}

# ML-specific: ablation and error bars
_ML_KEYWORDS = {
    "ablation": [
        r"\b(?:ablation\s+(?:study|experiment|analysis))\b",
        r"\b(?:component\s+analysis)\b",
        r"\b(?:without\s+\w+\s+module|removing\s+\w+\s+component)\b",
    ],
    "error_bars": [
        r"\b(?:error\s+bar|standard\s+deviation|±|mean\s+±)\b",
        r"\b(?:across\s+\d+\s+(?:run|seed|trial))\b",
        r"\b(?:confidence\s+band|shaded\s+(?:region|area))\b",
    ],
    "baselines": [
        r"\b(?:baseline|benchmark|compared?\s+(?:to|with|against))\b",
        r"\b(?:state[\s-]of[\s-]the[\s-]art|SOTA|prior\s+work)\b",
    ],
}

# Endogeneity discussion
_ENDOGENEITY_KEYWORDS = [
    r"\b(?:endogene(?:ity|ous))\b",
    r"\b(?:omitted\s+variable|selection\s+bias)\b",
    r"\b(?:reverse\s+causality|simultaneity)\b",
    r"\b(?:measurement\s+error)\b",
    r"\b(?:exclusion\s+restriction)\b",
    r"\b(?:exogene(?:ity|ous))\b",
]

# Limitations and broader impact
_LIMITATIONS_KEYWORDS = [
    r"\b(?:limitation|caveat|shortcoming)\b",
    r"\b(?:future\s+(?:work|research|direction))\b",
    r"\b(?:beyond\s+the\s+scope)\b",
    r"\b(?:does\s+not\s+(?:account|address|capture))\b",
]

_BROADER_IMPACT_KEYWORDS = [
    r"\b(?:broader\s+impact|societal\s+impact|ethical)\b",
    r"\b(?:negative\s+(?:consequence|impact|effect))\b",
    r"\b(?:fairness|bias|discrimination)\b",
    r"\b(?:dual[\s-]use|misuse)\b",
]

# Passive voice pattern (approximate)
_PASSIVE_VOICE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+"
    r"(?:\w+\s+)*?"
    r"(?:ed|en|ied|ung|orn|own|ade|ilt|ept|old|ound|oken|iven|aten|tten)\b",
    re.IGNORECASE,
)

# Hedging language
_HEDGING_PATTERNS = [
    r"\b(?:might|could|may|possibly|perhaps|somewhat|arguably)\b",
    r"\b(?:it\s+(?:seems|appears)\s+that)\b",
    r"\b(?:to\s+some\s+extent|in\s+some\s+cases)\b",
]


def _count_pattern_matches(text: str, patterns: list[str]) -> int:
    """Count total matches across multiple regex patterns."""
    count = 0
    for p in patterns:
        count += len(re.findall(p, text, re.IGNORECASE))
    return count


def _has_pattern(text: str, patterns: list[str]) -> bool:
    """Check if any pattern matches."""
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _section_matches(heading: str, keywords: list[str]) -> bool:
    """Check if a section heading matches any keyword."""
    h = heading.lower()
    return any(kw in h for kw in keywords)


def _extract_abstract(doc: ParsedDocument) -> str:
    """Extract abstract text from document."""
    for s in doc.sections:
        if "abstract" in s.heading.lower():
            return s.text
    # Try first section if no explicit abstract heading
    if doc.sections and doc.sections[0].level <= 2:
        first = doc.sections[0].text
        if len(first.split()) < 300:  # likely an abstract
            return first
    return ""


def _count_references(doc: ParsedDocument) -> int:
    """Count references in document."""
    if doc.references:
        return len(doc.references)
    # Fallback: count items in any reference/bibliography section
    for s in doc.sections:
        if any(kw in s.heading.lower() for kw in ("reference", "bibliography")):
            # Estimate from text
            lines = [l for l in s.text.split("\n") if l.strip() and len(l.strip()) > 20]
            return max(len(lines), 1)
    return 0


def _estimate_passive_fraction(text: str) -> float:
    """Estimate fraction of sentences using passive voice."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 0.0
    passive_count = sum(1 for s in sentences if _PASSIVE_VOICE.search(s))
    return passive_count / len(sentences)


# --- Main evaluation functions ---

def evaluate_structure(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate document structure against venue requirements."""
    findings = []
    recs = []
    score = 5

    headings_lower = [s.heading.lower() for s in doc.sections]

    # Check required sections
    # Group synonymous section names — matching any one satisfies the requirement
    section_synonyms = {
        "method": ["method", "methodology", "approach", "empirical", "estimation", "strategy", "model", "framework"],
        "data": ["data", "dataset", "sample", "corpus"],
        "result": ["result", "finding", "experiment", "evaluation", "analysis"],
        "conclusion": ["conclusion", "summary", "concluding"],
        "introduction": ["introduction", "overview", "motivation"],
    }
    missing = []
    for req in profile.required_sections:
        synonyms = section_synonyms.get(req, [req])
        found = any(syn in h for h in headings_lower for syn in synonyms)
        if not found:
            missing.append(req)

    if missing:
        n_missing = len(missing)
        score -= min(n_missing, 3)
        findings.append(f"Missing required sections: {', '.join(missing)}")
        recs.append(f"Add sections for: {', '.join(missing)}")

    # Check abstract
    abstract = _extract_abstract(doc)
    if not abstract:
        score -= 1
        findings.append("No abstract found")
        recs.append("Add a structured abstract")
    else:
        word_count = len(abstract.split())
        if word_count < profile.min_abstract_words:
            findings.append(f"Abstract too short ({word_count} words, min {profile.min_abstract_words})")
            recs.append(f"Expand abstract to at least {profile.min_abstract_words} words")
            score -= 1
        elif word_count > profile.max_abstract_words:
            findings.append(f"Abstract too long ({word_count} words, max {profile.max_abstract_words})")
            recs.append(f"Trim abstract to {profile.max_abstract_words} words")

    # Check optional but valued sections
    has_limitations = any("limitation" in h or "caveat" in h for h in headings_lower)
    if profile.requires_limitations and not has_limitations:
        # Check if limitations discussed in body text
        if not _has_pattern(doc.full_text, _LIMITATIONS_KEYWORDS):
            findings.append("No limitations discussed")
            recs.append("Add a limitations section or discuss limitations explicitly")
            score -= 1

    return DimensionScore(
        name="Structure & Completeness",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_citations(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate citation metrics."""
    findings = []
    recs = []
    score = 5

    ref_count = _count_references(doc)

    if ref_count == 0:
        findings.append("No references detected")
        recs.append(f"Add at least {profile.min_references} references")
        return DimensionScore(name="Citations & References", score=1, findings=findings, recommendations=recs)

    if ref_count < profile.min_references:
        findings.append(f"Only {ref_count} references (minimum: {profile.min_references})")
        recs.append(f"Add more references to reach at least {profile.min_references}")
        score -= 2
    elif ref_count < profile.typical_references[0]:
        findings.append(
            f"{ref_count} references is below typical range "
            f"({profile.typical_references[0]}-{profile.typical_references[1]})"
        )
        recs.append("Consider citing additional relevant literature")
        score -= 1
    elif ref_count > profile.typical_references[1] * 1.5:
        findings.append(f"{ref_count} references is unusually high — may indicate unfocused literature review")
        score -= 1

    # Check citation year distribution (from inline citations in text)
    years = re.findall(r"\((?:\w+[,\s]+)?(\d{4})\)", doc.full_text)
    years = [int(y) for y in years if 1900 <= int(y) <= 2030]
    if years:
        current_year = 2026
        recent = [y for y in years if current_year - y <= profile.max_citation_age_years]
        recency = len(recent) / len(years) if years else 0
        if recency < profile.min_recent_fraction:
            findings.append(
                f"Only {recency:.0%} of citations are from the last "
                f"{profile.max_citation_age_years} years (expected: ≥{profile.min_recent_fraction:.0%})"
            )
            recs.append("Add more recent references to demonstrate awareness of current literature")
            score -= 1

        median_year = sorted(years)[len(years) // 2]
        if current_year - median_year > 10:
            findings.append(f"Median citation year is {median_year} — literature may be outdated")
            score -= 1
    else:
        findings.append("Could not extract citation years from text")

    return DimensionScore(
        name="Citations & References",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_statistical_rigor(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate statistical reporting rigor."""
    findings = []
    recs = []
    score = 5
    text = doc.full_text

    # Standard errors
    if profile.requires_standard_errors:
        has_se = _has_pattern(text, _STAT_RIGOR_KEYWORDS["standard_errors"])
        if not has_se:
            findings.append("No standard errors reported")
            recs.append("Report standard errors (robust or clustered as appropriate)")
            score -= 2

    # Confidence intervals
    if profile.requires_confidence_intervals:
        has_ci = _has_pattern(text, _STAT_RIGOR_KEYWORDS["confidence_intervals"])
        if not has_ci:
            findings.append("No confidence intervals reported")
            recs.append("Report confidence intervals for key estimates")
            score -= 1

    # Effect sizes
    if profile.requires_effect_sizes:
        has_effects = _has_pattern(text, _STAT_RIGOR_KEYWORDS["effect_sizes"])
        if not has_effects:
            findings.append("No effect size interpretation found")
            recs.append("Interpret coefficient magnitudes (e.g., '1 SD increase in X → Y% change in outcome')")
            score -= 1

    # Multiple testing correction
    if profile.requires_multiple_testing_correction:
        has_mt = _has_pattern(text, _STAT_RIGOR_KEYWORDS["multiple_testing"])
        if not has_mt:
            findings.append("No multiple testing correction mentioned")
            recs.append("Apply Bonferroni/BH correction if testing multiple hypotheses")
            score -= 1

    # ML-specific: error bars
    if profile.requires_error_bars:
        has_bars = _has_pattern(text, _ML_KEYWORDS["error_bars"])
        if not has_bars:
            findings.append("No error bars or variance across runs reported")
            recs.append("Report mean ± std across multiple random seeds (NeurIPS requirement)")
            score -= 2

    # ML-specific: ablations
    if profile.requires_ablations:
        has_ablation = _has_pattern(text, _ML_KEYWORDS["ablation"])
        if not has_ablation:
            findings.append("No ablation study found")
            recs.append("Add ablation study showing each component's contribution")
            score -= 1

    # General: robustness
    if profile.requires_robustness:
        robustness_count = _count_pattern_matches(text, _ROBUSTNESS_KEYWORDS)
        if robustness_count == 0:
            findings.append("No robustness checks mentioned")
            recs.append("Add robustness checks (alternative specifications, subsamples, sensitivity analysis)")
            score -= 2
        elif robustness_count < 3:
            findings.append(f"Limited robustness discussion ({robustness_count} mentions)")
            recs.append("Expand robustness section with additional checks")
            score -= 1

    return DimensionScore(
        name="Statistical & Methodological Rigor",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_identification(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate identification strategy and causal claims."""
    findings = []
    recs = []
    score = 5
    text = doc.full_text

    if not (profile.requires_identification or profile.requires_endogeneity_discussion):
        return DimensionScore(
            name="Identification & Causality",
            score=5,
            findings=["Not applicable for this venue type"],
        )

    # Check for identification strategy
    if profile.requires_identification:
        id_count = _count_pattern_matches(text, _IDENTIFICATION_KEYWORDS)
        if id_count == 0:
            findings.append("No identification strategy detected (IV, DiD, RDD, RCT, etc.)")
            recs.append(
                "Explicitly state your identification strategy. "
                "Pure correlational work is effectively unpublishable in top-5 journals."
            )
            score -= 3
        elif id_count < 3:
            findings.append("Identification strategy mentioned but may lack depth")
            recs.append("Elaborate on identification: state assumptions, discuss validity, provide supporting evidence")
            score -= 1

    # Check for endogeneity discussion
    if profile.requires_endogeneity_discussion:
        endo_count = _count_pattern_matches(text, _ENDOGENEITY_KEYWORDS)
        if endo_count == 0:
            findings.append("No endogeneity discussion found")
            recs.append(
                "Discuss potential endogeneity concerns: omitted variables, reverse causality, "
                "measurement error. Explain how your design addresses them."
            )
            score -= 2
        elif endo_count < 3:
            findings.append("Endogeneity discussed briefly")
            recs.append("Expand endogeneity discussion to address all potential concerns")
            score -= 1

    return DimensionScore(
        name="Identification & Causality",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_reproducibility(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate reproducibility signals."""
    findings = []
    recs = []
    score = 5
    text = doc.full_text

    # Data availability
    if profile.requires_data_availability:
        has_data = _has_pattern(text, _REPRO_KEYWORDS["data_availability"])
        if not has_data:
            findings.append("No data availability statement found")
            recs.append("Add data availability statement specifying where data can be obtained")
            score -= 1

    # Code
    if profile.requires_code:
        has_code = _has_pattern(text, _REPRO_KEYWORDS["code"])
        if not has_code:
            findings.append("No code availability or implementation details")
            recs.append("Provide code repository link or describe implementation details")
            score -= 1

    # Compute budget (ML venues)
    if profile.requires_compute_budget:
        has_compute = _has_pattern(text, _REPRO_KEYWORDS["compute"])
        if not has_compute:
            findings.append("No compute budget or hardware details reported")
            recs.append(
                "Report hardware (GPU type), training time, and compute resources "
                "(NeurIPS 2026 makes this mandatory)"
            )
            score -= 2

    # Baselines (ML venues)
    if profile.venue_type == VenueType.ML_TOP:
        has_baselines = _has_pattern(text, _ML_KEYWORDS["baselines"])
        if not has_baselines:
            findings.append("No baselines or comparisons mentioned")
            recs.append("Compare against relevant baselines and state-of-the-art methods")
            score -= 2

    return DimensionScore(
        name="Reproducibility & Transparency",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_writing_quality(doc: ParsedDocument, profile: VenueProfile) -> DimensionScore:
    """Evaluate writing quality signals."""
    findings = []
    recs = []
    score = 5
    text = doc.full_text

    # Passive voice
    passive_frac = _estimate_passive_fraction(text)
    if passive_frac > profile.max_passive_voice_fraction:
        findings.append(f"High passive voice usage (~{passive_frac:.0%}, threshold: {profile.max_passive_voice_fraction:.0%})")
        recs.append("Reduce passive voice for clearer, more direct prose")
        score -= 1

    # Hedging
    hedge_count = _count_pattern_matches(text, _HEDGING_PATTERNS)
    word_count = len(text.split())
    hedge_density = hedge_count / max(word_count, 1) * 1000  # per 1000 words
    if hedge_density > 5:
        findings.append(f"Excessive hedging language (~{hedge_density:.1f} per 1000 words)")
        recs.append("Reduce hedging (might, could, perhaps) — state findings with confidence")
        score -= 1

    # Broader impact (ML venues)
    if profile.requires_broader_impact:
        has_impact = _has_pattern(text, _BROADER_IMPACT_KEYWORDS)
        if not has_impact:
            findings.append("No broader impact or ethical considerations discussed")
            recs.append("Add broader impact section (NeurIPS requires this)")
            score -= 1

    # Limitations
    if profile.requires_limitations:
        has_limits = _has_pattern(text, _LIMITATIONS_KEYWORDS)
        if not has_limits:
            findings.append("No limitations discussed")
            recs.append("Discuss limitations explicitly — reviewers view omission as a red flag")
            score -= 1

    return DimensionScore(
        name="Writing Quality & Completeness",
        score=max(1, score),
        findings=findings,
        recommendations=recs,
    )


def evaluate_document(
    doc: ParsedDocument,
    venue: str = "general",
) -> EvaluationReport:
    """Run full evaluation of a document against venue standards.

    Args:
        doc: Parsed document.
        venue: Venue name or category (e.g., "neurips", "aer", "econ_top5", "general").

    Returns:
        EvaluationReport with dimension scores and overall assessment.
    """
    profile = VENUE_PROFILES.get(venue.lower(), GENERAL)

    dimensions = [
        evaluate_structure(doc, profile),
        evaluate_citations(doc, profile),
        evaluate_statistical_rigor(doc, profile),
        evaluate_identification(doc, profile),
        evaluate_reproducibility(doc, profile),
        evaluate_writing_quality(doc, profile),
    ]

    report = EvaluationReport(
        venue=venue,
        venue_profile=profile.name,
        dimensions=dimensions,
    )
    report.compute_overall()

    # Aggregate suggestions
    for d in dimensions:
        report.suggestions.extend(d.recommendations)

    return report
