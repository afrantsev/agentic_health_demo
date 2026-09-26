"""Run the briefing pipeline over fixed test conditions and apply assertion checks.

    python -m eval.run_eval                          # all cases (live LLM + API calls)
    python -m eval.run_eval --case "multiple"        # cases whose condition contains the text
    python -m eval.run_eval --from-dir eval/results/20260926-101500   # re-check saved briefings, no LLM calls
"""

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.schemas import BriefingResponse

from .cases import CASES, EvalCase
from .checks import CheckResult, run_checks

RESULTS_DIR = Path(__file__).parent / "results"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_or_generate(case: EvalCase, from_dir: Path | None, out_dir: Path) -> BriefingResponse:
    if from_dir:
        return BriefingResponse.model_validate_json((from_dir / f"{slug(case.condition)}.json").read_text())
    from app.crew import run_briefing  # imported lazily so --from-dir works without LLM credentials

    briefing = run_briefing(case.condition)
    (out_dir / f"{slug(case.condition)}.json").write_text(briefing.model_dump_json(indent=2))
    return briefing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", help="substring of a case condition (repeatable)")
    parser.add_argument("--from-dir", type=Path, help="re-evaluate briefings saved by a previous run")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.case or any(s.lower() in c.condition.lower() for s in args.case)]
    if not cases:
        print(f"No cases match {args.case}. Available: {[c.condition for c in CASES]}")
        return 2

    out_dir = args.from_dir or RESULTS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {}
    for case in cases:
        print(f"\n=== {case.condition} ===", flush=True)
        try:
            briefing = load_or_generate(case, args.from_dir, out_dir)
            results = run_checks(case, briefing)
        except Exception as exc:
            results = [CheckResult("pipeline_ran", "FAIL", False, f"{type(exc).__name__}: {exc}")]
        for r in results:
            status = "PASS" if r.passed else r.severity
            print(f"  {status:<5} {r.name:<26} {r.detail}")
        report[case.condition] = [asdict(r) for r in results]

    all_results = [r for rs in report.values() for r in rs]
    failures = sum(1 for r in all_results if not r["passed"] and r["severity"] == "FAIL")
    warnings = sum(1 for r in all_results if not r["passed"] and r["severity"] == "WARN")
    passed = sum(1 for r in all_results if r["passed"])

    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\n{passed} passed, {failures} failed, {warnings} warnings across {len(cases)} case(s)")
    print(f"Report and briefings: {out_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
