"""
src/pipeline/worker.py
========================
Subprocess-side worker module for the parallel candidate scoring pipeline.

Design
------
* _worker_init() is called ONCE per worker process by ProcessPoolExecutor's
  initializer mechanism.  It sets module-level globals so that large read-only
  objects (taxonomies, semantic cache) are received a single time via pickle
  at process start — NOT re-pickled on every batch call.

* score_batch() is the actual worker function.  It receives a list of raw
  candidate dicts, runs extract_features() + compute_final_score() for each,
  and returns a list of picklable result tuples.  No taxonomy data travels in
  this direction.

Thread-safety / state
---------------------
Each worker process has its own address space — module-level globals here are
process-local and never shared across workers or with the main process.
This module is intentionally NOT imported in the main process path; it is only
imported by child processes when they are spawned.

Public API (for ranker.py only)
-------------------------------
    _worker_init(...)   — passed as ProcessPoolExecutor initializer
    score_batch(batch)  — the per-batch work function
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-worker globals — set once via _worker_init(), read many times
# ---------------------------------------------------------------------------
_TITLE_TAXONOMY: dict = {}
_INDUSTRY_TAXONOMY: dict = {}
_TIER_A: dict = {}
_TIER_B: dict = {}
_TIER_C: dict = {}
_SEMANTIC_CACHE: Optional[dict[str, Any]] = None
_JD_EMBEDDING: Optional[Any] = None
_TODAY: Optional[date] = None


def _worker_init(
    title_taxonomy: dict,
    industry_taxonomy: dict,
    tier_a: dict,
    tier_b: dict,
    tier_c: dict,
    semantic_cache: Optional[dict[str, Any]],
    jd_embedding: Optional[Any],
    today: Optional[date],
) -> None:
    """
    Initializer called once per worker process by ProcessPoolExecutor.

    Stores all shared read-only resources as module-level globals so that
    score_batch() can access them without any further IPC.

    Parameters
    ----------
    title_taxonomy, industry_taxonomy : dict
        Career-scorer taxonomy dicts.
    tier_a, tier_b, tier_c : dict
        Skill-taxonomy tier dicts.
    semantic_cache : dict or None
        Maps candidate_id -> numpy embedding array.
    jd_embedding : array-like or None
        Precomputed JD embedding for semantic similarity.
    today : date or None
        Reference date for recency calculations (injected for determinism).
    """
    global _TITLE_TAXONOMY, _INDUSTRY_TAXONOMY
    global _TIER_A, _TIER_B, _TIER_C
    global _SEMANTIC_CACHE, _JD_EMBEDDING, _TODAY

    _TITLE_TAXONOMY    = title_taxonomy
    _INDUSTRY_TAXONOMY = industry_taxonomy
    _TIER_A            = tier_a
    _TIER_B            = tier_b
    _TIER_C            = tier_c
    _SEMANTIC_CACHE    = semantic_cache
    _JD_EMBEDDING      = jd_embedding
    _TODAY             = today

    logger.debug("Worker initialised with %d title-taxonomy entries.", len(title_taxonomy))


def score_batch(
    candidate_batch: list[dict],
) -> list[tuple]:
    """
    Score a batch of candidate dicts and return picklable result tuples.

    Called in a worker process.  All taxonomy / embedding state is read from
    module-level globals set by _worker_init().

    Parameters
    ----------
    candidate_batch : list[dict]
        A slice of the full candidates list, as raw dicts from load_candidates().

    Returns
    -------
    list[tuple]
        Each element is a 3-tuple:
            (sort_key: tuple, features: CandidateFeatures, final_score: float)

        sort_key  — same tuple built by ranker._heap_key(); used to drive the
                    main-process Top-K heap without recomputing scores.
        features  — frozen CandidateFeatures dataclass (fully picklable).
        final_score — float, already computed here to avoid recomputation.

    Notes
    -----
    Vetoed candidates are filtered out here — they are never returned to the
    main process, matching the serial pipeline's behavior of skipping them
    before heap insertion.
    """
    # Import here (inside the worker process) to avoid issues on Windows
    # where the spawn context re-imports only what the child needs.
    from src.pipeline.feature_extractor import extract_features
    from src.pipeline.ranker import compute_final_score, _heap_key

    results: list[tuple] = []

    for candidate in candidate_batch:
        try:
            features = extract_features(
                candidate,
                title_taxonomy=_TITLE_TAXONOMY,
                industry_taxonomy=_INDUSTRY_TAXONOMY,
                tier_a=_TIER_A,
                tier_b=_TIER_B,
                tier_c=_TIER_C,
                today=_TODAY,
                semantic_cache=_SEMANTIC_CACHE,
                jd_embedding=_JD_EMBEDDING,
                debug=False,
            )
        except Exception as exc:  # noqa: BLE001
            # Individual candidate failures must not crash the whole batch.
            cid = candidate.get("candidate_id", "UNKNOWN")
            logger.warning("score_batch: error scoring candidate %s: %s", cid, exc)
            continue

        # Mirror the serial ranker: skip vetoed candidates immediately.
        if features.veto_candidate:
            continue

        score = compute_final_score(features)
        key   = _heap_key(score, features)
        results.append((key, features, score))

    return results
