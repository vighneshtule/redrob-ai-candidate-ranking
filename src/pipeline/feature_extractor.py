"""
src/pipeline/feature_extractor.py
===================================
Orchestrates feature extraction for a single candidate record.

Calls each scorer in dependency order — integrity first (enables early veto),
then career, skills, behavior, and semantic — and assembles the results into
a flat CandidateFeatures record for the ranker.

Public API
----------
    extract_features(candidate, title_taxonomy, industry_taxonomy,
                     tier_a, tier_b, tier_c, ...) -> CandidateFeatures
    CandidateFeatures                              -- frozen dataclass
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from src.features.integrity_scorer import score_integrity
from src.features.career_scorer import score_career
from src.features.skill_scorer import score_skills
from src.features.behavioral_scorer import score_behavior
from src.features.semantic_scorer import score_semantic


@dataclass(frozen=True)
class CandidateFeatures:
    """
    Flat feature record produced by extract_features() and consumed by the ranker.

    Attributes
    ----------
    candidate_id : str
    veto_candidate : bool
        True if integrity scorer determined the profile should be excluded entirely.
    career_score : float [0, 1]
    skill_score : float [0, 1]
    behavior_score : float [0, 1]
    integrity_score : float [0, 1]
    profile_integrity_score : float [0, 1]
    semantic_score : float [0, 1]
    stuffing_score : float [0, 1]
    anomaly_count : int
    anomaly_flags : tuple[str, ...]
    final_feature_vector : dict
        Flat dict of all sub-scores and signals — used by the reasoning generator
        and exported in the debug CSV.
    """

    candidate_id: str
    veto_candidate: bool
    career_score: float
    skill_score: float
    behavior_score: float
    integrity_score: float
    profile_integrity_score: float
    semantic_score: float
    stuffing_score: float
    anomaly_count: int
    anomaly_flags: tuple
    final_feature_vector: dict


def extract_features(
    candidate: dict,
    title_taxonomy: Optional[dict] = None,
    industry_taxonomy: Optional[dict] = None,
    tier_a: Optional[dict] = None,
    tier_b: Optional[dict] = None,
    tier_c: Optional[dict] = None,
    today: Optional[date] = None,
    semantic_cache: Optional[dict] = None,
    jd_embedding: Optional[Any] = None,
    debug: bool = False,
) -> CandidateFeatures:
    """
    Extract all features for a single candidate record.

    Scorers are called in dependency order:
      1. Integrity — may veto; when debug=False, vetoed candidates short-circuit.
      2. Career, Skills, Behavior — independent; all run in parallel conceptually.
      3. Semantic — requires optional precomputed embeddings.

    Parameters
    ----------
    candidate : dict
        Raw candidate record from load_candidates().
    title_taxonomy, industry_taxonomy : dict, optional
        Loaded from career_scorer.load_taxonomies(). Pass None only in tests.
    tier_a, tier_b, tier_c : dict, optional
        Loaded from skill_scorer.load_skill_taxonomy(). Pass None only in tests.
    today : date, optional
        Reference date for recency calculations. Defaults to date.today().
    semantic_cache : dict, optional
        Maps candidate_id -> embedding array. Used by score_semantic().
    jd_embedding : array-like, optional
        Precomputed JD embedding for semantic similarity.
    debug : bool
        When True, all scorers run even on vetoed candidates (full breakdown visible).

    Returns
    -------
    CandidateFeatures
    """
    cid = str(candidate.get("candidate_id", "UNKNOWN"))
    profile = candidate.get("profile", {}) or {}

    # --- 1. Integrity (veto gate) ---
    integrity_result = score_integrity(candidate)
    is_vetoed = integrity_result.is_vetoed

    if is_vetoed and not debug:
        # Short-circuit: build a minimal record for vetoed candidates.
        return CandidateFeatures(
            candidate_id=cid,
            veto_candidate=True,
            career_score=0.0,
            skill_score=0.0,
            behavior_score=0.0,
            integrity_score=integrity_result.integrity_score,
            profile_integrity_score=integrity_result.profile_integrity_score,
            semantic_score=0.0,
            stuffing_score=integrity_result.stuffing_score,
            anomaly_count=integrity_result.anomaly_count,
            anomaly_flags=tuple(integrity_result.flags),
            final_feature_vector={
                "career_score": 0.0,
                "skill_score": 0.0,
                "behavior_score": 0.0,
                "integrity_score": integrity_result.integrity_score,
                "profile_integrity_score": integrity_result.profile_integrity_score,
                "semantic_score": 0.0,
                "stuffing_score": integrity_result.stuffing_score,
                "anomaly_count": integrity_result.anomaly_count,
            },
        )

    # --- 2. Career ---
    career_result = score_career(
        candidate,
        title_taxonomy=title_taxonomy or {},
        industry_taxonomy=industry_taxonomy or {},
        today=today,
    )

    # --- 3. Skills ---
    skill_result = score_skills(
        candidate,
        tier_a=tier_a or {},
        tier_b=tier_b or {},
        tier_c=tier_c or {},
    )

    # --- 4. Behavior ---
    behavior_result = score_behavior(candidate, today=today)

    # --- 5. Semantic ---
    candidate_embedding = None
    if semantic_cache is not None:
        candidate_embedding = semantic_cache.get(cid)
    semantic_result = score_semantic(candidate, candidate_embedding, jd_embedding)

    # --- Assemble flat feature vector ---
    fv: dict = {
        # Top-level scores
        "career_score": career_result.final_career_score,
        "skill_score": skill_result.final_skill_score,
        "behavior_score": behavior_result.final_behavior_score,
        "integrity_score": integrity_result.integrity_score,
        "profile_integrity_score": integrity_result.profile_integrity_score,
        "semantic_score": semantic_result.semantic_score,
        "stuffing_score": integrity_result.stuffing_score,
        "anomaly_count": integrity_result.anomaly_count,
        # Career sub-scores
        "title_relevance_score": career_result.title_relevance_score,
        "career_history_relevance_score": career_result.career_history_relevance_score,
        "product_company_score": career_result.product_company_score,
        "relevant_experience_score": career_result.relevant_experience_score,
        "career_consistency_score": career_result.career_consistency_score,
        # Skill sub-scores
        "tier_a_match_score": skill_result.tier_a_match_score,
        "tier_b_match_score": skill_result.tier_b_match_score,
        "tier_c_match_score": skill_result.tier_c_match_score,
        "duration_score": skill_result.duration_score,
        "proficiency_score": skill_result.proficiency_score,
        "assessment_score": skill_result.assessment_score,
        "coverage_score": skill_result.coverage_score,
        "depth_score": skill_result.depth_score,
        "consistency_score": skill_result.consistency_score,
        # Behavior sub-scores
        "availability_score": behavior_result.availability_score,
        "activity_score": behavior_result.activity_score,
        "recruiter_engagement_score": behavior_result.recruiter_engagement_score,
        "interview_reliability_score": behavior_result.interview_reliability_score,
        "hiring_probability_score": behavior_result.hiring_probability_score,
        "notice_period_score": behavior_result.notice_period_score,
        "behavioral_risk_score": behavior_result.behavioral_risk_score,
        # Profile fields for API response mapping
        "career_years_exp": profile.get("years_of_experience", 0),
        "current_title": profile.get("current_title", ""),
        "location": profile.get("location", ""),
        # Skill lists for API response
        "supported_skills": list(skill_result.supported_skills),
        "unsupported_skills": list(skill_result.unsupported_skills),
        "matched_skills": list(skill_result.matched_skills),
        "missing_skills": list(skill_result.missing_skills),
    }

    return CandidateFeatures(
        candidate_id=cid,
        veto_candidate=is_vetoed,
        career_score=career_result.final_career_score,
        skill_score=skill_result.final_skill_score,
        behavior_score=behavior_result.final_behavior_score,
        integrity_score=integrity_result.integrity_score,
        profile_integrity_score=integrity_result.profile_integrity_score,
        semantic_score=semantic_result.semantic_score,
        stuffing_score=integrity_result.stuffing_score,
        anomaly_count=integrity_result.anomaly_count,
        anomaly_flags=tuple(integrity_result.flags),
        final_feature_vector=fv,
    )
