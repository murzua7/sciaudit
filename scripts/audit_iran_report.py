"""Run sciaudit against the Iran energy crisis report."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sciaudit.pipeline import run_audit


async def main():
    report_path = Path.home() / "Desktop" / "iran-war-scenarios" / "report.html"
    if not report_path.exists():
        print(f"Report not found at {report_path}")
        return

    print(f"Auditing: {report_path}")
    print()

    report = await run_audit(
        document_path=report_path,
        output_dir=Path.home() / "Desktop" / "sciaudit" / "output",
        concurrency=3,  # conservative to avoid rate limits
    )

    print(f"\nTotal claims extracted: {report.total_claims}")
    print(f"Audit score: {report.score:.0%}")
    print(f"Summary: {report.summary}")
    print(f"\nCritical: {report.critical_count}, Major: {report.major_count}")

    # Show critical/major
    for r in report.results:
        if r.severity.value in ("critical", "major"):
            print(f"\n  [{r.severity.value.upper()}] {r.claim.id}: {r.claim.text}")
            print(f"    Status: {r.status.value}")
            print(f"    {r.explanation}")
            if r.suggested_correction:
                print(f"    Suggested: {r.suggested_correction}")


if __name__ == "__main__":
    asyncio.run(main())
