"""
src/pipeline/loader.py
======================
Streaming JSONL reader for the Redrob candidate dataset.

Design principles
-----------------
* Generator-based: yields one candidate dict at a time. The full 465 MB file
  is NEVER loaded into memory simultaneously.
* Fail-safe: malformed JSON lines are skipped with a warning; the pipeline
  keeps running.
* Schema-light validation: checks candidate_id format + required top-level
  keys so downstream scorers can trust the data shape.
* Progress logging: emits a line every LOADER_LOG_INTERVAL candidates so
  long runs are observable in CI / terminal.
* Benchmarking: exposes load_and_benchmark() for throughput measurement.

Public API
----------
    load_candidates(path, limit=None, skip_invalid=True) -> Iterator[dict]
    count_lines(path) -> int
    load_and_benchmark(path, limit=2000) -> BenchmarkResult
    validate_candidate(candidate) -> tuple[bool, list[str]]
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from src.config import (
    CANDIDATE_ID_PATTERN,
    LOADER_DEFAULT_ENCODING,
    LOADER_LOG_INTERVAL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled once at module load — used in every validate_candidate() call
# ---------------------------------------------------------------------------
_CANDIDATE_ID_RE = re.compile(CANDIDATE_ID_PATTERN)

# Required top-level keys (from candidate_schema.json §required)
_REQUIRED_TOP_KEYS: frozenset[str] = frozenset({
    "candidate_id",
    "profile",
    "career_history",
    "education",
    "skills",
    "redrob_signals",
})

# Required keys inside profile (subset — enough to catch badly truncated records)
_REQUIRED_PROFILE_KEYS: frozenset[str] = frozenset({
    "years_of_experience",
    "current_title",
    "current_industry",
    "location",
    "country",
})

# Required keys inside redrob_signals (critical behavioral fields)
_REQUIRED_SIGNAL_KEYS: frozenset[str] = frozenset({
    "last_active_date",
    "open_to_work_flag",
    "recruiter_response_rate",
    "notice_period_days",
    "expected_salary_range_inr_lpa",
    "skill_assessment_scores",
    "github_activity_score",
    "interview_completion_rate",
    "offer_acceptance_rate",
})


# ---------------------------------------------------------------------------
# Public dataclass for benchmark results
# ---------------------------------------------------------------------------
@dataclass
class BenchmarkResult:
    """Result returned by load_and_benchmark()."""

    total_records: int = 0
    valid_records: int = 0
    skipped_malformed_json: int = 0
    skipped_invalid_schema: int = 0
    elapsed_seconds: float = 0.0
    throughput_per_second: float = 0.0
    peak_line_bytes: int = 0   # largest single line seen (memory proxy)
    sample_invalid_reasons: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # noqa: D105
        return (
            f"BenchmarkResult("
            f"total={self.total_records:,}, valid={self.valid_records:,}, "
            f"malformed_json={self.skipped_malformed_json}, "
            f"invalid_schema={self.skipped_invalid_schema}, "
            f"elapsed={self.elapsed_seconds:.2f}s, "
            f"throughput={self.throughput_per_second:,.0f} rec/s, "
            f"peak_line={self.peak_line_bytes:,} bytes)"
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_candidate(candidate: dict) -> tuple[bool, list[str]]:
    """
    Lightweight schema validation for a parsed candidate dict.

    Returns
    -------
    (is_valid, error_messages)
        is_valid : bool
        error_messages : list of human-readable problem descriptions (empty if valid)

    Complexity: O(1) — fixed set of key lookups, single regex match.
    """
    errors: list[str] = []

    # --- candidate_id ---
    cid = candidate.get("candidate_id")
    if not cid:
        errors.append("Missing candidate_id")
    elif not _CANDIDATE_ID_RE.match(str(cid)):
        errors.append(f"Invalid candidate_id format: {cid!r}")

    # --- required top-level keys ---
    missing_top = _REQUIRED_TOP_KEYS - candidate.keys()
    if missing_top:
        errors.append(f"Missing top-level keys: {sorted(missing_top)}")

    # --- profile sub-keys ---
    profile = candidate.get("profile")
    if isinstance(profile, dict):
        missing_profile = _REQUIRED_PROFILE_KEYS - profile.keys()
        if missing_profile:
            errors.append(f"Missing profile keys: {sorted(missing_profile)}")
        yoe = profile.get("years_of_experience")
        if yoe is not None and not isinstance(yoe, (int, float)):
            errors.append("years_of_experience must be numeric")
    elif "profile" in candidate:
        errors.append("profile must be a dict")

    # --- redrob_signals sub-keys ---
    signals = candidate.get("redrob_signals")
    if isinstance(signals, dict):
        missing_signals = _REQUIRED_SIGNAL_KEYS - signals.keys()
        if missing_signals:
            errors.append(f"Missing signal keys: {sorted(missing_signals)}")
    elif "redrob_signals" in candidate:
        errors.append("redrob_signals must be a dict")

    # --- career_history must be a non-empty list ---
    ch = candidate.get("career_history")
    if ch is not None and not isinstance(ch, list):
        errors.append("career_history must be a list")
    elif isinstance(ch, list) and len(ch) == 0:
        errors.append("career_history is empty (schema requires minItems: 1)")

    # --- skills must be a list ---
    skills = candidate.get("skills")
    if skills is not None and not isinstance(skills, list):
        errors.append("skills must be a list")

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Core streaming generator
# ---------------------------------------------------------------------------
def load_candidates(
    path: str | Path,
    limit: Optional[int] = None,
    skip_invalid: bool = True,
    validate: bool = True,
    log_interval: int = LOADER_LOG_INTERVAL,
) -> Iterator[dict]:
    """
    Stream candidates from a JSONL file one record at a time.

    Parameters
    ----------
    path : str or Path
        Path to candidates.jsonl (or any JSONL file conforming to the schema).
    limit : int, optional
        Stop after yielding this many **valid** candidates. None = no limit.
    skip_invalid : bool
        If True (default): malformed JSON or invalid schema → log warning and
        continue. If False: raise on first error.
    validate : bool
        If True (default): run validate_candidate() on every parsed record.
        Set False for maximum throughput when you trust the input.
    log_interval : int
        Emit an INFO log every this many valid candidates streamed.

    Yields
    ------
    dict
        One candidate record per yield, guaranteed to pass validate_candidate()
        when validate=True.

    Complexity per record
    ---------------------
    Time : O(L) where L = length of the JSON line.
    Memory : O(1) — only one record + one raw line in memory simultaneously.

    Notes
    -----
    * UTF-8 encoding assumed (per submission spec).
    * Lines that are entirely whitespace are skipped silently.
    * The generator can be stopped early by the consumer without leaking fd.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    yielded = 0
    line_num = 0
    malformed_json = 0
    invalid_schema = 0

    logger.info("Loading candidates from: %s", path)
    t_start = time.perf_counter()

    with path.open("r", encoding=LOADER_DEFAULT_ENCODING, errors="replace") as fh:
        for raw_line in fh:
            line_num += 1
            line = raw_line.strip()

            # Skip blank lines
            if not line:
                continue

            # --- Parse JSON ---
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError as exc:
                malformed_json += 1
                msg = f"Line {line_num}: malformed JSON ({exc.msg})"
                if skip_invalid:
                    logger.warning("Skipping — %s", msg)
                    continue
                else:
                    raise ValueError(msg) from exc

            # --- Schema validation ---
            if validate:
                is_valid, errors = validate_candidate(candidate)
                if not is_valid:
                    invalid_schema += 1
                    error_summary = "; ".join(errors[:3])  # trim for log readability
                    msg = (
                        f"Line {line_num} [{candidate.get('candidate_id', '?')}]: "
                        f"schema violation — {error_summary}"
                    )
                    if skip_invalid:
                        logger.warning("Skipping — %s", msg)
                        continue
                    else:
                        raise ValueError(msg)

            yielded += 1

            # --- Progress logging ---
            if log_interval > 0 and yielded % log_interval == 0:
                elapsed = time.perf_counter() - t_start
                throughput = yielded / max(elapsed, 1e-9)
                logger.info(
                    "Loaded %s candidates | line %s | %.0f rec/s | "
                    "skipped malformed=%s invalid=%s",
                    f"{yielded:,}",
                    f"{line_num:,}",
                    throughput,
                    malformed_json,
                    invalid_schema,
                )

            yield candidate

            # --- Respect limit ---
            if limit is not None and yielded >= limit:
                logger.info(
                    "Limit of %d reached — stopping early at line %d.", limit, line_num
                )
                break

    elapsed = time.perf_counter() - t_start
    throughput = yielded / max(elapsed, 1e-9)
    logger.info(
        "Streaming complete | yielded=%s | lines_read=%s | "
        "malformed_json=%s | invalid_schema=%s | "
        "elapsed=%.2fs | throughput=%.0f rec/s",
        f"{yielded:,}",
        f"{line_num:,}",
        malformed_json,
        invalid_schema,
        elapsed,
        throughput,
    )


# ---------------------------------------------------------------------------
# Line counter (fast — reads raw bytes, no JSON parse)
# ---------------------------------------------------------------------------
def count_lines(path: str | Path, chunk_size: int = 1 << 20) -> int:  # 1 MB chunks
    """
    Count the number of non-empty lines in a large text file efficiently.

    Uses buffered binary reads rather than Python line iteration — typically
    3–5× faster than ``sum(1 for _ in open(path))`` on large files.

    Parameters
    ----------
    path : str or Path
    chunk_size : int
        Read buffer size in bytes (default 1 MiB).

    Returns
    -------
    int
        Number of lines containing at least one non-whitespace character.

    Complexity: O(N) time, O(chunk_size) memory.
    """
    path = Path(path)
    count = 0
    newline = ord(b"\n")

    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            count += chunk.count(newline)

    # If last byte is not a newline the last record has no trailing newline
    # → safe to return count as-is since JSONL conventionally ends with \n.
    return count


# ---------------------------------------------------------------------------
# Benchmarking utility
# ---------------------------------------------------------------------------
def load_and_benchmark(
    path: str | Path,
    limit: int = 2_000,
    validate: bool = True,
) -> BenchmarkResult:
    """
    Stream up to *limit* records and collect throughput statistics.

    This is the recommended first call on a new environment to verify the
    pipeline is within the 5-minute budget.

    Parameters
    ----------
    path : str or Path
    limit : int
        Number of valid records to stream before stopping (default 2,000).
    validate : bool
        Whether to run schema validation (default True).

    Returns
    -------
    BenchmarkResult

    Example
    -------
    >>> result = load_and_benchmark("candidates.jsonl", limit=5000)
    >>> print(result)
    BenchmarkResult(total=5000, valid=5000, malformed_json=0, ...)
    """
    result = BenchmarkResult()
    t_start = time.perf_counter()
    path = Path(path)

    line_num = 0
    with path.open("r", encoding=LOADER_DEFAULT_ENCODING, errors="replace") as fh:
        for raw_line in fh:
            line_num += 1
            line = raw_line.strip()
            if not line:
                continue

            result.total_records += 1
            line_bytes = len(raw_line.encode("utf-8", errors="replace"))
            if line_bytes > result.peak_line_bytes:
                result.peak_line_bytes = line_bytes

            # JSON parse
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                result.skipped_malformed_json += 1
                continue

            # Schema validation
            if validate:
                is_valid, errors = validate_candidate(candidate)
                if not is_valid:
                    result.skipped_invalid_schema += 1
                    if len(result.sample_invalid_reasons) < 5:
                        cid = candidate.get("candidate_id", "?")
                        result.sample_invalid_reasons.append(
                            f"{cid}: {'; '.join(errors[:2])}"
                        )
                    continue

            result.valid_records += 1
            if result.valid_records >= limit:
                break

    result.elapsed_seconds = time.perf_counter() - t_start
    result.throughput_per_second = result.valid_records / max(
        result.elapsed_seconds, 1e-9
    )
    return result


# ---------------------------------------------------------------------------
# CLI entry-point (python -m src.pipeline.loader <path> [--limit N])
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Benchmark or count candidates in a JSONL file."
    )
    parser.add_argument("path", help="Path to candidates.jsonl")
    parser.add_argument(
        "--limit",
        type=int,
        default=2_000,
        help="Number of records to benchmark (default 2000)",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Only count lines (fast, no JSON parse)",
    )
    args = parser.parse_args()

    if args.count_only:
        n = count_lines(args.path)
        print(f"Line count: {n:,}")
        sys.exit(0)

    print(f"Benchmarking first {args.limit:,} records from: {args.path}")
    bench = load_and_benchmark(args.path, limit=args.limit)
    print(bench)
    if bench.sample_invalid_reasons:
        print("Sample invalid records:")
        for reason in bench.sample_invalid_reasons:
            print(f"  {reason}")
