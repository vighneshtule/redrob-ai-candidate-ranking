"""
backend_api/services/pipeline_service.py
==========================================
Orchestrates the ranking pipeline for the FastAPI backend.

Responsibilities
----------------
* Preloads taxonomies at startup (once, shared across requests).
* Tracks real-time pipeline stage progress for the frontend visualization.
* Measures actual execution time, memory, and per-candidate latency.
* Caches the last ranked result set for the /candidate/{id} route.
"""

from __future__ import annotations

import pickle
import time
import logging
import tracemalloc
from pathlib import Path
from typing import Any, Optional

from src.pipeline.loader import load_candidates
from src.pipeline.ranker import rank_candidates_parallel
from src.features.career_scorer import load_taxonomies
from src.features.skill_scorer import load_skill_taxonomy
from src.config import CANDIDATES_JSONL
from backend_api.schemas.models import (
    CandidateResponse,
    CandidateScores,
    SkillDetails,
    CopilotData,
    JdMatch,
)

logger = logging.getLogger(__name__)


class PipelineStatus:
    """Mutable singleton tracking the state of the currently-running pipeline."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.current_step: int = 0
        self.is_playing: bool = False
        self.metrics: dict = {
            "candidatesProcessed": 0,
            "runtimeSeconds": 0.0,
            "heapSize": 0,
            "cacheHits": 0,
            "memoryMb": 0.0,
            "averageCandidateTimeMs": 0.0,
            "stages": [],
        }


global_status = PipelineStatus()

# Taxonomies are preloaded at import time — loading is slow (~1s) and the data
# is read-only, so sharing a single copy across all requests is safe.
logger.info("Preloading taxonomies...")
title_taxonomy, industry_taxonomy = load_taxonomies()
tier_a, tier_b, tier_c, _ = load_skill_taxonomy()
logger.info("Taxonomies ready.")

# Semantic embedding cache — preloaded once at startup alongside taxonomies.
# Maps candidate_id -> numpy embedding array. None when the pkl is absent.
_EMBEDDINGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "candidate_embeddings.pkl"
_semantic_cache: dict[str, Any] | None = None
_jd_embedding: Any = None
if _EMBEDDINGS_PATH.exists():
    logger.info("Loading semantic embedding cache from %s ...", _EMBEDDINGS_PATH)
    with open(_EMBEDDINGS_PATH, "rb") as _emb_f:
        _emb_data = pickle.load(_emb_f)
    _semantic_cache = _emb_data.get("candidates")
    _jd_embedding = _emb_data.get("jd_embedding")
    logger.info(
        "Semantic cache loaded: %d candidate embeddings, jd_embedding present: %s",
        len(_semantic_cache) if _semantic_cache else 0,
        _jd_embedding is not None,
    )
else:
    logger.warning("Semantic embedding cache not found at %s — semantic_score will be 0.0", _EMBEDDINGS_PATH)

# In-memory store for the most recent ranked result — keyed by candidate_id.
# Cleared and repopulated on each /api/rank call.
_ranked_candidates_cache: dict[str, CandidateResponse] = {}


def get_pipeline_status() -> dict:
    return {
        "currentStep": global_status.current_step,
        "isPlaying": global_status.is_playing,
        "metrics": global_status.metrics,
    }


def run_pipeline(job_description: str, top_k: int = 100) -> list[CandidateResponse]:
    """
    Execute the full ranking pipeline and return the top-K candidates.

    Stages (maps to frontend step numbers)
    ----------------------------------------
    1  — Parsing JD
    2  — Verifying Taxonomies
    3  — Loading Dataset
    4  — Integrity Scoring       (first 20% of candidates)
    5  — Career & Skill Scoring  (next 30%)
    7  — Semantic Scoring        (next 30%)
    8  — Behavioral / Ranking    (final 20%)
    9  — Done

    Parameters
    ----------
    job_description : str
        Raw JD text submitted by the recruiter.
    top_k : int
        Number of top candidates to return (default 100).

    Returns
    -------
    list[CandidateResponse]
        Ranked candidates formatted for the frontend API contract.
    """
    tracemalloc.start()
    global_status.reset()
    global_status.is_playing = True

    stages: list[dict] = []

    def _record_stage(name: str, duration: float) -> None:
        stages.append({
            "name": name,
            "status": "completed",
            "progress": 100,
            "duration": round(duration, 3),
        })
        global_status.metrics["stages"] = stages

    t_total = time.perf_counter()

    # Stage 1: JD ingestion
    global_status.current_step = 1
    t = time.perf_counter()
    # Future: structured JD parsing (NER, skill extraction) goes here.
    _ = job_description
    _record_stage("Parsing JD", time.perf_counter() - t)

    # Stage 2: Taxonomy verification
    global_status.current_step = 2
    t = time.perf_counter()
    _ = len(title_taxonomy), len(tier_a)
    _record_stage("Verifying Taxonomies", time.perf_counter() - t)

    # Stage 3: Dataset loading
    global_status.current_step = 3
    t = time.perf_counter()
    raw_candidates = list(load_candidates(CANDIDATES_JSONL, limit=None, validate=False))
    total_candidates = len(raw_candidates)
    _record_stage("Loading Dataset", time.perf_counter() - t)

    t = time.perf_counter()
    global_status.current_step = 5   # Feature Extraction
    global_status.metrics["candidatesProcessed"] = 0
    ranked = rank_candidates_parallel(
        raw_candidates,
        title_taxonomy=title_taxonomy,
        industry_taxonomy=industry_taxonomy,
        tier_a=tier_a,
        tier_b=tier_b,
        tier_c=tier_c,
        top_k=top_k,
        semantic_cache=_semantic_cache,
        jd_embedding=_jd_embedding,
    )
    global_status.metrics["candidatesProcessed"] = total_candidates
    global_status.current_step = 8   # Behavioral / Ranking
    rank_duration = time.perf_counter() - t
    _record_stage("Feature Extraction & Parallel Hybrid Ranking", rank_duration)

    # Finalise metrics
    global_status.current_step = 9
    total_elapsed = time.perf_counter() - t_total

    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    global_status.metrics.update({
        "runtimeSeconds": round(total_elapsed, 2),
        "heapSize": len(ranked),
        "cacheHits": 0,
        "memoryMb": round(peak_mem / (1024 * 1024), 2),
        "averageCandidateTimeMs": round(
            (rank_duration / (total_candidates or 1)) * 1000, 2
        ),
    })
    global_status.is_playing = False

    # Format results and populate cache
    results: list[CandidateResponse] = []
    _ranked_candidates_cache.clear()

    for r in ranked:
        fv = r.feature_breakdown
        profile = fv  # feature vector includes profile fields

        integrity_flags = (
            ["Anomaly detected"] if fv.get("anomaly_count", 0) > 0 else []
        )
        behavior_signals = (
            ["High recruiter engagement"]
            if fv.get("recruiter_engagement_score", 0) >= 0.7
            else []
        )

        # Determine match tier from final score
        final = r.final_score
        if final >= 0.80:
            match_status = "Strong Match"
            recommendation = "Strong Hire"
        elif final >= 0.60:
            match_status = "Good Match"
            recommendation = "Interview"
        else:
            match_status = "Potential Match"
            recommendation = "Review"

        cand_resp = CandidateResponse(
            id=r.candidate_id,
            name=fv.get("name", f"Candidate {r.candidate_id[-5:]}"),
            avatar_url=None,
            headline=fv.get("current_title", "Experienced Professional"),
            current_title=fv.get("current_title", ""),
            company=fv.get("company", ""),
            location=fv.get("location", ""),
            years_of_experience=int(fv.get("career_years_exp", 0)),
            open_to_work=fv.get("open_to_work", True),
            relocation=fv.get("relocation", False),
            scores=CandidateScores(
                final_score=final,
                career_score=fv.get("career_score", 0.0),
                skill_score=fv.get("skill_score", 0.0),
                behavior_score=fv.get("behavior_score", 0.0),
                integrity_score=fv.get("integrity_score", 0.0),
                semantic_score=fv.get("semantic_score", 0.0),
                consistency_score=fv.get("consistency_score", 0.0),
            ),
            match_status=match_status,
            skills=SkillDetails(
                supported=fv.get("supported_skills", []),
                unsupported=fv.get("unsupported_skills", []),
            ),
            career_summary=r.explanation,
            behavior_signals=behavior_signals,
            integrity_flags=integrity_flags,
            recruiter_explanation=r.explanation,
            copilot=CopilotData(
                why_ranked=_build_why_ranked(fv, final),
                potential_risks=integrity_flags,
                semantic_evidence=[],
                jd_match=JdMatch(
                    required_skills_found=fv.get("matched_skills", []),
                    missing_skills=fv.get("missing_skills", []),
                    preferred_skills_found=[],
                    experience_match=fv.get("career_years_exp", 0) >= 3,
                    location_match=True,
                    overall_match_percentage=int(final * 100),
                ),
                timeline=[],
                recommendation_status=recommendation,
                recommendation_reasoning=r.explanation,
                interview_questions=[],
            ),
        )
        _ranked_candidates_cache[cand_resp.id] = cand_resp
        results.append(cand_resp)

    return results


def _build_why_ranked(fv: dict, final_score: float) -> list[str]:
    """Derive ranked-reason bullets from the feature vector — no hard-coding."""
    reasons: list[str] = []
    if fv.get("career_score", 0) >= 0.70:
        reasons.append(f"Strong career relevance (score: {fv['career_score']:.2f})")
    if fv.get("skill_score", 0) >= 0.60:
        reasons.append(f"Good skill match (score: {fv['skill_score']:.2f})")
    if fv.get("behavior_score", 0) >= 0.65:
        reasons.append(f"High behavioural signals (score: {fv['behavior_score']:.2f})")
    if fv.get("semantic_score", 0) >= 0.50:
        reasons.append(f"Semantic JD alignment (score: {fv['semantic_score']:.2f})")
    if not reasons:
        reasons.append(f"Composite hybrid score: {final_score:.2f}")
    return reasons


def get_candidate(candidate_id: str) -> Optional[CandidateResponse]:
    return _ranked_candidates_cache.get(candidate_id)
