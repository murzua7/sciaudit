"""CLI entry point for sciaudit."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from sciaudit.models import Severity, VerificationStatus
from sciaudit.pipeline import run_audit

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sciaudit",
        description="Scientific claim auditor — verify quantitative claims and citations",
    )
    parser.add_argument("document", help="Path to document file (.html or .md)")
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory for reports (default: same as document)",
    )
    parser.add_argument(
        "--fred-api-key",
        default=os.environ.get("FRED_API_KEY", ""),
        help="FRED API key (default: $FRED_API_KEY)",
    )
    parser.add_argument(
        "--email",
        default="sciaudit@verification.local",
        help="Email for Crossref polite pool",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent API calls (default: 5)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Only output JSON (no HTML report)",
    )

    args = parser.parse_args()

    doc_path = Path(args.document)
    if not doc_path.exists():
        console.print(f"[red]Error:[/red] File not found: {doc_path}")
        sys.exit(1)

    console.print(f"[bold]sciaudit[/bold] v0.1.0")
    console.print(f"Auditing: [cyan]{doc_path.name}[/cyan]")
    console.print()

    report = asyncio.run(
        run_audit(
            document_path=doc_path,
            output_dir=args.output_dir,
            fred_api_key=args.fred_api_key,
            email=args.email,
            concurrency=args.concurrency,
        )
    )

    # Print summary table
    console.print()
    table = Table(title=f"Audit Results — {report.document_title}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Claims", str(report.total_claims))
    table.add_row(
        "Audit Score",
        f"[{'green' if report.score >= 0.9 else 'yellow' if report.score >= 0.7 else 'red'}]{report.score:.0%}[/]",
    )
    table.add_row("Verified", f"[green]{report.summary.get('verified', 0)}[/green]")
    table.add_row("Incorrect", f"[red]{report.summary.get('incorrect', 0)}[/red]")
    table.add_row("Imprecise", f"[yellow]{report.summary.get('imprecise', 0)}[/yellow]")
    table.add_row("Fabricated", f"[red bold]{report.summary.get('fabricated', 0)}[/red bold]")
    table.add_row("Unverifiable", f"[dim]{report.summary.get('unverifiable', 0)}[/dim]")
    console.print(table)

    # Print critical/major findings
    critical_major = [
        r for r in report.results if r.severity in (Severity.CRITICAL, Severity.MAJOR)
    ]
    if critical_major:
        console.print()
        console.print("[bold red]Critical & Major Findings:[/bold red]")
        for r in critical_major:
            sev_style = "red bold" if r.severity == Severity.CRITICAL else "yellow"
            console.print(
                f"  [{sev_style}]{r.severity.value.upper()}[/] "
                f"[{STATUS_COLORS_RICH.get(r.status, 'white')}]{r.status.value}[/] "
                f"[dim]{r.claim.id}[/dim] {r.claim.text}"
            )
            console.print(f"    → {r.explanation}")
            if r.suggested_correction:
                console.print(f"    [green]Suggested: {r.suggested_correction}[/green]")

    output_dir = Path(args.output_dir) if args.output_dir else doc_path.parent
    console.print()
    console.print(f"Reports saved to: [cyan]{output_dir}[/cyan]")
    console.print(f"  HTML: {doc_path.stem}_audit.html")
    console.print(f"  JSON: {doc_path.stem}_audit.json")

    # Exit with error code if critical issues found
    if report.critical_count > 0:
        sys.exit(1)


STATUS_COLORS_RICH = {
    VerificationStatus.VERIFIED: "green",
    VerificationStatus.INCORRECT: "red",
    VerificationStatus.IMPRECISE: "yellow",
    VerificationStatus.UNVERIFIABLE: "dim",
    VerificationStatus.FABRICATED: "red bold",
    VerificationStatus.UNSUPPORTED: "red",
    VerificationStatus.MISATTRIBUTED: "magenta",
}


if __name__ == "__main__":
    main()
