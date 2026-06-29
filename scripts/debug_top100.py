#!/usr/bin/env python
"""
scripts/debug_top100.py
========================
Human-readable ranked candidate table for debugging and inspection.

Usage
-----
    python scripts/debug_top100.py --candidates data/candidates.jsonl
    python scripts/debug_top100.py --candidates data/candidates.jsonl --top-k 10
    python scripts/debug_top100.py --candidates data/candidates.jsonl --top-k 100 --export-csv

Output
------
    Aligned table printed to stdout:
        Rank  Candidate ID    Score   Career  Skill   Behavior  Integrity  Profile  Flags
           1  CAND_0012345   0.8472  0.9210  0.8040   0.7500    1.0000    0.9000   []
           2  ...

    Optionally writes outputs/submission.csv and outputs/debug/debug_ranked.csv.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.pipeline.ranker import rank_candidates
from src.pipeline.exporter import export_submission_csv, export_debug_csv
from src.features.career_scorer import load_taxonomies
from src.features.skill_scorer import load_skill_taxonomy
from src.pipeline.loader import load_candidates
from src.config import CANDIDATES_JSONL


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _fmt(v: float | None) -> str:
    """Format a float to 4 decimal places, or '–' if None."""
    if v is None:
        return "–"
    return f"{v:.4f}"


def print_table(ranked: list) -> None:
    """Print a human-readable aligned table of ranked candidates."""
    header = (
        f"{'Rank':>4}  {'Candidate ID':<14}  {'Score':>7}  "
        f"{'Career':>7}  {'Skill':>7}  {'Behavior':>8}  "
        f"{'Integrity':>9}  {'Profile':>7}  Anomalies"
    )
    sep = "-" * len(header)

    print()
    print(header)
    print(sep)

    for r in ranked:
        fv = r.feature_breakdown
        print(
            f"{r.rank:>4}  {r.candidate_id:<14}  {r.final_score:>7.4f}  "
            f"{_fmt(fv.get('career_score')):>7}  "
            f"{_fmt(fv.get('skill_score')):>7}  "
            f"{_fmt(fv.get('behavior_score')):>8}  "
            f"{_fmt(fv.get('integrity_score')):>9}  "
            f"{_fmt(fv.get('profile_integrity_score')):>7}  "
            f"{fv.get('anomaly_count', 0)}"
        )
    print(sep)
    print(f"  Total: {len(ranked)} candidates")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Debug the top-K ranked candidates from a JSONL file."
    )
    parser.add_argument(
        "--candidates",
        type=str,
        default=str(CANDIDATES_JSONL),
        help="Path to candidates.jsonl (default: challenge data)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=100,
        help="Number of top candidates to rank (default: 100)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after loading N candidates (for fast iteration). Default: no limit.",
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Also write outputs/submission.csv and outputs/debug/debug_ranked.csv",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip JSONL schema validation (faster)",
    )
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    if not candidates_path.exists():
        logger.error("Candidates file not found: %s", candidates_path)
        sys.exit(1)

    # Load taxonomies once
    logger.info("Loading taxonomies...")
    title_taxonomy, industry_taxonomy = load_taxonomies()
    tier_a, tier_b, tier_c, _ = load_skill_taxonomy()

    # Stream and rank
    logger.info("Ranking top-%d candidates from: %s", args.top_k, candidates_path)
    t0 = time.perf_counter()

    candidate_stream = load_candidates(
        candidates_path,
        limit=args.limit,
        validate=not args.no_validate,
    )

    ranked = rank_candidates(
        candidate_stream,
        title_taxonomy=title_taxonomy,
        industry_taxonomy=industry_taxonomy,
        tier_a=tier_a,
        tier_b=tier_b,
        tier_c=tier_c,
        top_k=args.top_k,
    )

    elapsed = time.perf_counter() - t0
    logger.info("Ranking complete in %.2fs — %d candidates ranked", elapsed, len(ranked))

    # Print table
    print_table(ranked)

    # Optionally export
    if args.export_csv:
        if len(ranked) == 100:
            try:
                sub_path = export_submission_csv(ranked, overwrite=True)
                logger.info("Submission CSV written: %s", sub_path)
            except ValueError as e:
                logger.warning("Submission validation failed: %s", e)

        debug_path = export_debug_csv(ranked, overwrite=True)
        logger.info("Debug CSV written: %s", debug_path)


if __name__ == "__main__":
    main()
