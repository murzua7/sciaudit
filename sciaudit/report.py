"""Audit report generator — produces HTML and JSON reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sciaudit.evaluator import EvaluationReport
from sciaudit.models import AuditReport, Severity, VerificationResult, VerificationStatus

# Status to emoji/icon mapping for HTML
STATUS_ICONS = {
    VerificationStatus.VERIFIED: "&#10004;",  # ✔
    VerificationStatus.INCORRECT: "&#10008;",  # ✘
    VerificationStatus.IMPRECISE: "&#9888;",  # ⚠
    VerificationStatus.UNVERIFIABLE: "&#8263;",  # ⁇
    VerificationStatus.FABRICATED: "&#9760;",  # ☠
    VerificationStatus.UNSUPPORTED: "&#10060;",  # ❌
    VerificationStatus.MISATTRIBUTED: "&#8644;",  # ⇄
    VerificationStatus.PENDING: "&#8987;",  # ⏳
}

STATUS_COLORS = {
    VerificationStatus.VERIFIED: "#22c55e",
    VerificationStatus.INCORRECT: "#ef4444",
    VerificationStatus.IMPRECISE: "#f59e0b",
    VerificationStatus.UNVERIFIABLE: "#6b7280",
    VerificationStatus.FABRICATED: "#dc2626",
    VerificationStatus.UNSUPPORTED: "#f97316",
    VerificationStatus.MISATTRIBUTED: "#a855f7",
    VerificationStatus.PENDING: "#94a3b8",
}

SEVERITY_COLORS = {
    Severity.CRITICAL: "#dc2626",
    Severity.MAJOR: "#f59e0b",
    Severity.MINOR: "#3b82f6",
    Severity.INFO: "#6b7280",
}


def _result_to_dict(r: VerificationResult) -> dict:
    """Convert a VerificationResult to a serializable dict."""
    return {
        "claim_id": r.claim.id,
        "claim_text": r.claim.text,
        "claim_type": r.claim.claim_type.value,
        "section": r.claim.location.section,
        "status": r.status.value,
        "severity": r.severity.value,
        "explanation": r.explanation,
        "suggested_correction": r.suggested_correction,
        "verified_by": r.verified_by,
        "evidence": [
            {
                "source": e.source_name,
                "url": e.source_url,
                "value": str(e.retrieved_value) if e.retrieved_value else None,
                "match_score": e.match_score,
                "notes": e.notes,
            }
            for e in r.evidence
        ],
    }


def generate_json_report(report: AuditReport, output_path: str | Path) -> None:
    """Generate a JSON audit report."""
    report.compute_summary()
    data = {
        "sciaudit_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document": report.document_path,
        "title": report.document_title,
        "total_claims": report.total_claims,
        "audit_score": round(report.score, 3),
        "summary": report.summary,
        "critical_issues": report.critical_count,
        "major_issues": report.major_count,
        "results": [_result_to_dict(r) for r in report.results],
    }
    Path(output_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_html_report(report: AuditReport, output_path: str | Path) -> None:
    """Generate an HTML audit report with interactive filtering."""
    report.compute_summary()

    # Group results by severity
    critical = [r for r in report.results if r.severity == Severity.CRITICAL]
    major = [r for r in report.results if r.severity == Severity.MAJOR]
    minor = [r for r in report.results if r.severity == Severity.MINOR]
    info = [r for r in report.results if r.severity == Severity.INFO]

    def _render_result_row(r: VerificationResult) -> str:
        icon = STATUS_ICONS.get(r.status, "?")
        color = STATUS_COLORS.get(r.status, "#000")
        sev_color = SEVERITY_COLORS.get(r.severity, "#000")
        correction = ""
        if r.suggested_correction:
            correction = f'<div class="correction">Suggested: <code>{r.suggested_correction}</code></div>'
        evidence_html = ""
        if r.evidence:
            ev_items = []
            for e in r.evidence:
                ev_items.append(
                    f'<li><strong>{e.source_name}</strong> (score: {e.match_score:.2f}): {e.notes}'
                    + (f' — <a href="{e.source_url}" target="_blank">source</a>' if e.source_url else "")
                    + "</li>"
                )
            evidence_html = f'<details><summary>Evidence ({len(r.evidence)} sources)</summary><ul>{"".join(ev_items)}</ul></details>'

        return f"""
        <tr class="result-row severity-{r.severity.value} status-{r.status.value}">
            <td><code>{r.claim.id}</code></td>
            <td style="color:{color}">{icon} {r.status.value}</td>
            <td style="color:{sev_color}">{r.severity.value.upper()}</td>
            <td>{r.claim.claim_type.value}</td>
            <td class="claim-text">{r.claim.text}</td>
            <td>{r.claim.location.section}</td>
            <td>
                <div>{r.explanation}</div>
                {correction}
                {evidence_html}
            </td>
        </tr>"""

    all_rows = "".join(_render_result_row(r) for r in report.results)

    # Score color
    score = report.score
    if score >= 0.9:
        score_color = "#22c55e"
    elif score >= 0.7:
        score_color = "#f59e0b"
    else:
        score_color = "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SciAudit Report — {report.document_title}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; color: #f8fafc; }}
    h2 {{ font-size: 1.2rem; margin: 1.5rem 0 0.75rem; color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
    .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 1.5rem; }}

    .summary-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 1rem;
        margin-bottom: 2rem;
    }}
    .summary-card {{
        background: #1e293b;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }}
    .summary-card .number {{
        font-size: 2rem;
        font-weight: 700;
    }}
    .summary-card .label {{
        font-size: 0.8rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}

    .score-badge {{
        display: inline-block;
        font-size: 2.5rem;
        font-weight: 800;
        color: {score_color};
    }}

    .filters {{
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1rem;
        flex-wrap: wrap;
    }}
    .filter-btn {{
        padding: 0.4rem 0.8rem;
        border: 1px solid #475569;
        border-radius: 4px;
        background: #1e293b;
        color: #e2e8f0;
        cursor: pointer;
        font-size: 0.85rem;
    }}
    .filter-btn:hover {{ background: #334155; }}
    .filter-btn.active {{ background: #3b82f6; border-color: #3b82f6; }}

    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }}
    th {{
        background: #1e293b;
        padding: 0.6rem;
        text-align: left;
        color: #94a3b8;
        position: sticky;
        top: 0;
    }}
    td {{
        padding: 0.6rem;
        border-bottom: 1px solid #1e293b;
        vertical-align: top;
    }}
    tr:hover {{ background: #1e293b44; }}
    .claim-text {{ max-width: 300px; word-break: break-word; }}
    .correction {{ margin-top: 0.3rem; color: #22c55e; font-size: 0.8rem; }}
    details {{ margin-top: 0.3rem; font-size: 0.8rem; color: #94a3b8; }}
    summary {{ cursor: pointer; }}
    a {{ color: #60a5fa; }}
    code {{ background: #334155; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }}

    .hidden {{ display: none !important; }}

    @media print {{
        body {{ background: white; color: black; }}
        .filters {{ display: none; }}
        th {{ background: #f1f5f9; color: black; }}
        td {{ border-color: #e2e8f0; }}
    }}
</style>
</head>
<body>
<div class="container">
    <h1>SciAudit Report</h1>
    <div class="subtitle">
        Document: <strong>{report.document_title}</strong> |
        Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |
        sciaudit v0.1.0
    </div>

    <div class="summary-grid">
        <div class="summary-card">
            <div class="score-badge">{score:.0%}</div>
            <div class="label">Audit Score</div>
        </div>
        <div class="summary-card">
            <div class="number">{report.total_claims}</div>
            <div class="label">Total Claims</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color:#22c55e">{report.summary.get('verified', 0)}</div>
            <div class="label">Verified</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color:#dc2626">{report.critical_count}</div>
            <div class="label">Critical</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color:#f59e0b">{report.major_count}</div>
            <div class="label">Major</div>
        </div>
        <div class="summary-card">
            <div class="number" style="color:#6b7280">{report.summary.get('unverifiable', 0)}</div>
            <div class="label">Unverifiable</div>
        </div>
    </div>

    <h2>Findings</h2>
    <div class="filters">
        <button class="filter-btn active" onclick="filterResults('all')">All</button>
        <button class="filter-btn" onclick="filterResults('critical')">Critical</button>
        <button class="filter-btn" onclick="filterResults('major')">Major</button>
        <button class="filter-btn" onclick="filterResults('minor')">Minor</button>
        <button class="filter-btn" onclick="filterResults('info')">Info</button>
    </div>

    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Severity</th>
                <th>Type</th>
                <th>Claim</th>
                <th>Section</th>
                <th>Details</th>
            </tr>
        </thead>
        <tbody>
            {all_rows}
        </tbody>
    </table>
</div>

<script>
function filterResults(severity) {{
    const rows = document.querySelectorAll('.result-row');
    const buttons = document.querySelectorAll('.filter-btn');
    buttons.forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    rows.forEach(row => {{
        if (severity === 'all') {{
            row.classList.remove('hidden');
        }} else {{
            row.classList.toggle('hidden', !row.classList.contains('severity-' + severity));
        }}
    }});
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")


def generate_evaluation_html(
    report: EvaluationReport, doc_title: str, output_path: str | Path
) -> None:
    """Generate an HTML evaluation report showing venue-standard compliance."""
    report.compute_overall()

    # Grade color
    grade_colors = {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#f97316", "F": "#ef4444"}
    grade_color = grade_colors.get(report.overall_grade, "#6b7280")

    # Build dimension cards
    dim_cards = ""
    for d in report.dimensions:
        bar_width = (d.score / d.max_score) * 100
        if d.score >= 4:
            bar_color = "#22c55e"
        elif d.score >= 3:
            bar_color = "#3b82f6"
        elif d.score >= 2:
            bar_color = "#f59e0b"
        else:
            bar_color = "#ef4444"

        findings_html = ""
        if d.findings:
            items = "".join(f"<li>{f}</li>" for f in d.findings)
            findings_html = f'<div class="findings"><strong>Findings:</strong><ul>{items}</ul></div>'

        recs_html = ""
        if d.recommendations:
            items = "".join(f"<li>{r}</li>" for r in d.recommendations)
            recs_html = f'<div class="recs"><strong>Recommendations:</strong><ul>{items}</ul></div>'

        dim_cards += f"""
        <div class="dim-card">
            <div class="dim-header">
                <span class="dim-name">{d.name}</span>
                <span class="dim-score" style="color:{bar_color}">{d.score}/{d.max_score}</span>
            </div>
            <div class="score-bar-bg">
                <div class="score-bar" style="width:{bar_width}%;background:{bar_color}"></div>
            </div>
            {findings_html}
            {recs_html}
        </div>"""

    # Blockers
    blockers_html = ""
    if report.blockers:
        items = "".join(f"<li>{b}</li>" for b in report.blockers)
        blockers_html = f"""
        <div class="blockers">
            <h2>Submission Blockers</h2>
            <ul>{items}</ul>
        </div>"""

    # Ready badge
    ready_text = "READY" if report.ready_for_submission else "NOT READY"
    ready_color = "#22c55e" if report.ready_for_submission else "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SciAudit Evaluation — {doc_title}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.3rem; color: #f8fafc; }}
    h2 {{ font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: #94a3b8; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
    .subtitle {{ color: #64748b; font-size: 0.85rem; margin-bottom: 1.5rem; }}

    .top-summary {{
        display: flex; gap: 1.5rem; align-items: center; margin-bottom: 2rem;
        background: #1e293b; border-radius: 12px; padding: 1.5rem;
    }}
    .grade-circle {{
        width: 80px; height: 80px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 2.5rem; font-weight: 800; color: {grade_color};
        border: 3px solid {grade_color};
    }}
    .summary-text {{ flex: 1; }}
    .summary-text .venue {{ font-size: 0.85rem; color: #94a3b8; }}
    .summary-text .score-line {{ font-size: 1.1rem; margin: 0.3rem 0; }}
    .ready-badge {{
        display: inline-block; padding: 0.3rem 0.8rem; border-radius: 4px;
        font-size: 0.8rem; font-weight: 700; color: white;
        background: {ready_color};
    }}

    .dim-card {{
        background: #1e293b; border-radius: 8px; padding: 1rem;
        margin-bottom: 1rem;
    }}
    .dim-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
    .dim-name {{ font-weight: 600; }}
    .dim-score {{ font-size: 1.2rem; font-weight: 700; }}
    .score-bar-bg {{
        height: 6px; background: #334155; border-radius: 3px; overflow: hidden;
    }}
    .score-bar {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
    .findings, .recs {{ margin-top: 0.75rem; font-size: 0.85rem; }}
    .findings {{ color: #f59e0b; }}
    .recs {{ color: #60a5fa; }}
    .findings ul, .recs ul {{ margin-left: 1.2rem; margin-top: 0.3rem; }}
    .findings li, .recs li {{ margin-bottom: 0.25rem; }}

    .blockers {{
        background: #451a03; border: 1px solid #92400e; border-radius: 8px;
        padding: 1rem; margin-bottom: 1.5rem;
    }}
    .blockers h2 {{ color: #fbbf24; border: none; margin: 0 0 0.5rem; padding: 0; font-size: 1rem; }}
    .blockers ul {{ margin-left: 1.2rem; color: #fcd34d; font-size: 0.9rem; }}

    @media print {{
        body {{ background: white; color: black; }}
        .dim-card, .top-summary {{ background: #f8fafc; }}
        .score-bar-bg {{ background: #e2e8f0; }}
    }}
</style>
</head>
<body>
<div class="container">
    <h1>Journal Readiness Evaluation</h1>
    <div class="subtitle">
        Document: <strong>{doc_title}</strong> |
        Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |
        sciaudit v0.1.0
    </div>

    <div class="top-summary">
        <div class="grade-circle">{report.overall_grade}</div>
        <div class="summary-text">
            <div class="venue">Target: {report.venue_profile}</div>
            <div class="score-line">Overall Score: <strong>{report.overall_score:.0%}</strong></div>
            <span class="ready-badge">{ready_text} for submission</span>
        </div>
    </div>

    {blockers_html}

    <h2>Dimension Scores</h2>
    {dim_cards}
</div>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
