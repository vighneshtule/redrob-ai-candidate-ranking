"""
src/pipeline/exporter.py
=========================
CSV export for the Redrob submission pipeline.

Writes a submission.csv conforming to the challenge specification:
    Columns : candidate_id, rank, score, reasoning
    Rows    : exactly 100 (top-100 candidates)
    Ranks   : 1-indexed, 1..100, no gaps

Validation
----------
    validate_submission(ranked) -> list[str]  — returns list of violations
    export_submission_csv(ranked, output_path) -> Path  — write & return path

Public API
----------
    export_submission_csv(
        ranked: list[RankedCandidate],
        output_path: Path | str,
        overwrite: bool = False,
    ) -> Path

    validate_submission(ranked: list[RankedCandidate]) -> list[str]
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import (
    SUBMISSION_EXPECTED_ROWS,
    SUBMISSION_MAX_RANK,
    SUBMISSION_MIN_RANK,
    SUBMISSION_REQUIRED_COLUMNS,
    OUTPUTS_DIR,
)

if TYPE_CHECKING:
    from src.pipeline.ranker import RankedCandidate


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_submission(ranked: list) -> list[str]:
    """
    Validate a list of RankedCandidate objects against submission spec.

    Parameters
    ----------
    ranked : list[RankedCandidate]

    Returns
    -------
    list[str]
        Empty list = valid.  Non-empty = list of violation messages.
    """
    violations: list[str] = []

    # Row count
    n = len(ranked)
    if n != SUBMISSION_EXPECTED_ROWS:
        violations.append(
            f"Expected {SUBMISSION_EXPECTED_ROWS} rows, got {n}."
        )

    if not ranked:
        return violations

    # Rank range and uniqueness
    ranks = [r.rank for r in ranked]
    if min(ranks) < SUBMISSION_MIN_RANK:
        violations.append(
            f"Min rank {min(ranks)} < {SUBMISSION_MIN_RANK}."
        )
    if max(ranks) > SUBMISSION_MAX_RANK:
        violations.append(
            f"Max rank {max(ranks)} > {SUBMISSION_MAX_RANK}."
        )
    if len(set(ranks)) != len(ranks):
        violations.append("Duplicate ranks detected.")

    # candidate_id uniqueness
    cids = [r.candidate_id for r in ranked]
    if len(set(cids)) != len(cids):
        violations.append("Duplicate candidate_ids detected.")

    # Score bounds
    for r in ranked:
        if not (0.0 <= r.final_score <= 1.0):
            violations.append(
                f"{r.candidate_id}: score {r.final_score} out of [0, 1]."
            )

    # Explanation non-empty
    for r in ranked:
        if not r.explanation or not r.explanation.strip():
            violations.append(
                f"{r.candidate_id}: explanation is empty."
            )

    return violations


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_submission_csv(
    ranked: list,
    output_path: Path | str | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Write the ranked list to a submission CSV file.

    Parameters
    ----------
    ranked : list[RankedCandidate]
        The top-K ranked candidates (usually top-100).
    output_path : Path or str, optional
        Destination file path.  Defaults to outputs/submission.csv.
    overwrite : bool
        If False (default), raises FileExistsError if output_path exists.

    Returns
    -------
    Path
        Absolute path of the written CSV file.

    Raises
    ------
    FileExistsError
        If output_path already exists and overwrite=False.
    ValueError
        If validation fails (violations found in submission).
    """
    # Resolve output path
    if output_path is None:
        output_path = OUTPUTS_DIR / "submission.csv"
    output_path = Path(output_path).resolve()

    # Create parent dirs if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Guard against accidental overwrite
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. "
            f"Pass overwrite=True to replace it."
        )

    # Validate
    violations = validate_submission(ranked)
    if violations:
        msg = "Submission validation failed:\n" + "\n".join(f"  - {v}" for v in violations)
        raise ValueError(msg)

    # Write CSV
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=SUBMISSION_REQUIRED_COLUMNS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for r in ranked:
            writer.writerow({
                "candidate_id": r.candidate_id,
                "rank": r.rank,
                "score": f"{r.final_score:.6f}",
                "reasoning": r.explanation,
            })

    return output_path


# ---------------------------------------------------------------------------
# Debug export (extended columns — not for submission)
# ---------------------------------------------------------------------------

def export_debug_csv(
    ranked: list,
    output_path: Path | str | None = None,
    overwrite: bool = True,
) -> Path:
    """
    Write an extended debug CSV with all sub-scores visible.

    This is NOT the submission file — it includes extra breakdown columns
    for human inspection.

    Parameters
    ----------
    ranked : list[RankedCandidate]
    output_path : Path or str, optional
        Defaults to outputs/debug/debug_ranked.csv.
    overwrite : bool
        Default True (debug files are ephemeral).

    Returns
    -------
    Path
    """
    if output_path is None:
        from src.config import OUTPUTS_DEBUG_DIR
        output_path = OUTPUTS_DEBUG_DIR / "debug_ranked.csv"
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Debug CSV exists: {output_path}")

    # Build extended fieldnames from first entry's feature_breakdown
    base_fields = SUBMISSION_REQUIRED_COLUMNS[:]
    extra_fields: list[str] = []
    if ranked:
        extra_fields = [
            k for k in ranked[0].feature_breakdown.keys()
            if k not in set(base_fields)
        ]

    all_fields = base_fields + extra_fields

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=all_fields,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for r in ranked:
            row: dict = {
                "candidate_id": r.candidate_id,
                "rank": r.rank,
                "score": f"{r.final_score:.6f}",
                "reasoning": r.explanation,
            }
            for k in extra_fields:
                v = r.feature_breakdown.get(k, "")
                row[k] = f"{v:.4f}" if isinstance(v, float) else str(v)
            writer.writerow(row)

    return output_path
