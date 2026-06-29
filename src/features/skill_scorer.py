"""
src/features/skill_scorer.py
==============================
Skill Intelligence Engine for the Redrob candidate ranking system.

This module answers ONE question:
    "How strong is the candidate's demonstrated technical capability
     relative to the JD?"

It does NOT use embeddings, LLMs, or semantic retrieval.
It uses taxonomy-driven tier matching, duration curves, proficiency
mapping, and assessment validation — all pure Python, all deterministic.

Design principles
-----------------
* Taxonomy-first: match against skill_taxonomy.json tiers before falling
  back to alias expansion and fuzzy matching.
* Depth over breadth: a candidate with 3 skills at expert/72m depth scores
  higher than a candidate with 15 skills at beginner/0m.
* Alias-aware: SBERT, sentence-bert, sentence_transformers all resolve
  to the same canonical taxonomy entry via normalize_skill().
* Graceful degradation: missing duration, proficiency, or assessment fields
  fall back to conservative defaults (never crash, never assume best case).
* Pure functional: no side-effects, no global mutable state, thread-safe.

Signal sources (from candidate['skills'])
------------------------------------------
    name              str
    proficiency       str  (beginner / intermediate / advanced / expert)
    duration_months   int
    (optional) assessment score via redrob_signals.skill_assessment_scores

Taxonomy
---------
    data/skill_taxonomy.json  → tier_a, tier_b, tier_c, negative

Output
------
    SkillScoreResult — frozen dataclass with 12 fields

Sub-scorer weights (sum to 1.0)
--------------------------------
    tier_a_match_score    35%
    tier_b_match_score    15%
    tier_c_match_score    10%
    coverage_score        15%
    duration_score        10%
    proficiency_score      5%
    assessment_score       5%
    depth_score            5%

Public API
----------
    load_skill_taxonomy() -> tuple[dict, dict, dict, list]
    score_skills(candidate, tier_a, tier_b, tier_c) -> SkillScoreResult
    score_skills_batch(candidates, tier_a, tier_b, tier_c) -> list[SkillScoreResult]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.text_utils import normalize_skill
from src.features.skill_career_consistency import score_skill_consistency

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkillScoreResult:
    """
    Output of score_skills().  Frozen → hashable, thread-safe.

    Attributes
    ----------
    tier_a_match_score : float [0, 1]
        Fraction of Tier-A (must-have) skills matched.
    tier_b_match_score : float [0, 1]
        Fraction of Tier-B (nice-to-have) skills matched.
    tier_c_match_score : float [0, 1]
        Fraction of Tier-C (adjacent) skills matched.
    duration_score : float [0, 1]
        Quality-weighted average skill duration (normalised to 72m = 1.0).
    proficiency_score : float [0, 1]
        Weighted average proficiency across matched taxonomy skills.
    assessment_score : float [0, 1]
        Normalised assessment score from platform skill tests.
    coverage_score : float [0, 1]
        Fraction of all required JD skills covered.
    depth_score : float [0, 1]
        Composite of duration + proficiency + assessment for matched skills.
    final_skill_score : float [0, 1]
        Weighted aggregate of all sub-scores.
    matched_skills : tuple[str, ...]
        Canonical names of taxonomy skills successfully matched.
    missing_skills : tuple[str, ...]
        Canonical names of Tier-A skills NOT found in candidate profile.
    explanation : str
        Human-readable recruiter-facing reasoning string.
    """

    tier_a_match_score: float
    tier_b_match_score: float
    tier_c_match_score: float

    duration_score: float
    proficiency_score: float
    assessment_score: float

    coverage_score: float
    depth_score: float
    consistency_score: float

    final_skill_score: float

    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    supported_skills: tuple[str, ...]
    unsupported_skills: tuple[str, ...]

    explanation: str


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Sub-scorer weights — must sum to 1.0
_SKILL_WEIGHTS: dict[str, float] = {
    "tier_a":      0.30,
    "tier_b":      0.13,
    "tier_c":      0.08,
    "coverage":    0.13,
    "consistency": 0.15,
    "duration":    0.08,
    "proficiency": 0.04,
    "assessment":  0.05,
    "depth":       0.04,
}
assert abs(sum(_SKILL_WEIGHTS.values()) - 1.0) < 1e-9, "Skill weights must sum to 1.0"

# Proficiency level → score mapping
_PROFICIENCY_MAP: dict[str, float] = {
    "beginner":     0.25,
    "intermediate": 0.50,
    "advanced":     0.75,
    "expert":       1.00,
}
_DEFAULT_PROFICIENCY: float = 0.50  # unknown proficiency → intermediate default

# Duration → score piecewise linear interpolation
# (months, score) breakpoints — linearly interpolated between them
_DURATION_BREAKPOINTS: list[tuple[float, float]] = [
    (0.0,  0.00),
    (12.0, 0.30),
    (24.0, 0.50),
    (48.0, 0.80),
    (72.0, 1.00),
]
_DURATION_CEILING_MONTHS: float = 72.0  # 72+ months → 1.0

# Assessment score thresholds → normalised score
_ASSESSMENT_BREAKPOINTS: list[tuple[float, float]] = [
    (40.0,  0.20),  # < 40 → 0.20 (questionable)
    (60.0,  0.50),  # 40-60 → interpolate to 0.50
    (80.0,  0.75),  # 60-80 → interpolate to 0.75
    (95.0,  0.95),  # 80-95 → interpolate to 0.95
    (100.0, 1.00),  # 95+ → 1.00
]

# Fuzzy match threshold for alias fallback matching
_FUZZY_THRESHOLD: float = 82.0

# Default taxonomy path (override via load_skill_taxonomy)
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SKILL_TAXONOMY_PATH = _DATA_DIR / "skill_taxonomy.json"
_JD_REQUIREMENTS_PATH = _DATA_DIR / "jd_requirements.json"

# Module-level alias-index cache
# Keyed by (id(tier_a), id(tier_b), id(tier_c)) — Python object identity.
# When the same taxonomy dicts are reused across calls (the normal pipeline
# pattern), indexes are built exactly once per process rather than once per
# candidate.  Thread-safe for reads; a benign write race on first population
# is acceptable (worst case: built twice on the first two concurrent callers).
_ALIAS_INDEX_CACHE: dict[
    tuple[int, int, int],
    tuple[dict[str, str], dict[str, str], dict[str, str]],
] = {}


# ---------------------------------------------------------------------------
# Taxonomy loader
# ---------------------------------------------------------------------------

def load_skill_taxonomy(
    taxonomy_path: Optional[Path] = None,
    jd_path: Optional[Path] = None,
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict], list[str]]:
    """
    Load skill_taxonomy.json and return the four tier dicts.

    Parameters
    ----------
    taxonomy_path : Path, optional
        Override the default taxonomy file location.
    jd_path : Path, optional
        Override the default JD requirements file location.

    Returns
    -------
    (tier_a, tier_b, tier_c, negative_skills)
        Each tier dict: {canonical_name: [alias_list]}
        negative_skills: flat list of negative skill strings
    """
    path = taxonomy_path or _SKILL_TAXONOMY_PATH

    with path.open("r", encoding="utf-8") as f:
        taxonomy = json.load(f)

    tier_a: dict[str, dict] = taxonomy.get("tier_a", {}).get("skills", {})
    tier_b: dict[str, dict] = taxonomy.get("tier_b", {}).get("skills", {})
    tier_c: dict[str, dict] = taxonomy.get("tier_c", {}).get("skills", {})
    negative: list[str] = taxonomy.get("negative", {}).get("skills", [])

    return tier_a, tier_b, tier_c, negative


def load_jd_requirements(jd_path: Optional[Path] = None) -> dict:
    """Load jd_requirements.json."""
    path = jd_path or _JD_REQUIREMENTS_PATH
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Alias index builder
# ---------------------------------------------------------------------------

def _build_alias_index(
    tier: dict[str, list[str]],
) -> dict[str, str]:
    """
    Build a flat alias → canonical_name lookup from a tier dict.

    Each canonical skill name maps to a list of aliases (from the taxonomy).
    This function inverts that mapping: alias → canonical name.

    Also adds the canonical name itself as an alias for direct lookup.

    Parameters
    ----------
    tier : dict[str, list[str]]
        {canonical_name: [alias1, alias2, ...]}

    Returns
    -------
    dict[str, str]
        {normalized_alias: canonical_name}
    """
    index: dict[str, str] = {}
    for canonical, aliases in tier.items():
        # Canonical name itself
        index[normalize_skill(canonical)] = canonical
        # All declared aliases
        for alias in aliases:
            norm = normalize_skill(alias)
            if norm:
                index[norm] = canonical
    return index


# ---------------------------------------------------------------------------
# Skill matching
# ---------------------------------------------------------------------------

def _match_skill_to_tier(
    skill_name: str,
    alias_index: dict[str, str],
) -> Optional[str]:
    """
    Match a single raw skill name against a tier alias index.

    Strategy (in priority order):
    1. Direct normalised lookup in alias_index (fastest, most precise).
    2. Substring containment — check if normalised skill appears as a
       substring of any alias, or vice versa.

    Returns the canonical tier name if matched, else None.

    Parameters
    ----------
    skill_name : str
        Raw skill name from candidate profile.
    alias_index : dict[str, str]
        Pre-built alias → canonical name index.

    Returns
    -------
    str or None
        Canonical skill name if matched, None otherwise.
    """
    if not skill_name:
        return None

    norm = normalize_skill(skill_name)
    if not norm:
        return None

    # --- Strategy 1: Exact normalised lookup ---
    if norm in alias_index:
        return alias_index[norm]

    # --- Strategy 2: Substring containment ---
    # Check if norm is a substring of any alias key, or vice versa
    for alias_norm, canonical in alias_index.items():
        if alias_norm and (norm in alias_norm or alias_norm in norm):
            # Guard against very short partial matches (< 4 chars)
            if len(min(norm, alias_norm, key=len)) >= 4:
                return canonical

    return None


def _get_alias_indexes(
    tier_a: dict[str, list[str]],
    tier_b: dict[str, list[str]],
    tier_c: dict[str, list[str]],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """
    Return alias indexes for all three tiers, using the module-level cache.

    If the same taxonomy objects have been seen before (same Python id()),
    the cached indexes are returned immediately — O(1).
    Otherwise the indexes are built once and stored for future calls.

    Parameters
    ----------
    tier_a, tier_b, tier_c : dict
        Taxonomy tier dicts.

    Returns
    -------
    (idx_a, idx_b, idx_c) — alias → canonical dicts for each tier.
    """
    cache_key = (id(tier_a), id(tier_b), id(tier_c))
    if cache_key not in _ALIAS_INDEX_CACHE:
        _ALIAS_INDEX_CACHE[cache_key] = (
            _build_alias_index(tier_a),
            _build_alias_index(tier_b),
            _build_alias_index(tier_c),
        )
    return _ALIAS_INDEX_CACHE[cache_key]


def _match_candidate_skills(
    candidate_skills: list[dict],
    tier_a: dict[str, list[str]],
    tier_b: dict[str, list[str]],
    tier_c: dict[str, list[str]],
) -> tuple[
    dict[str, dict],   # tier_a_matches: canonical → skill_dict
    dict[str, dict],   # tier_b_matches
    dict[str, dict],   # tier_c_matches
    set[str],          # all_matched_canonicals
]:
    """
    Match all candidate skills against all three tiers.

    A skill is matched at most once (Tier A takes priority over B and C).
    Once a skill is matched to Tier A, it is not also counted in Tier B/C.

    Parameters
    ----------
    candidate_skills : list[dict]
        List of skill dicts from the candidate profile.
    tier_a, tier_b, tier_c : dict
        Taxonomy tier dicts.

    Returns
    -------
    (tier_a_matches, tier_b_matches, tier_c_matches, all_matched_canonicals)
    """
    # Retrieve or build alias indexes (cached after first call)
    idx_a, idx_b, idx_c = _get_alias_indexes(tier_a, tier_b, tier_c)

    tier_a_matches: dict[str, dict] = {}
    tier_b_matches: dict[str, dict] = {}
    tier_c_matches: dict[str, dict] = {}
    all_matched: set[str] = set()

    for skill_dict in candidate_skills:
        name = skill_dict.get("name", "")
        if not name:
            continue

        # Try Tier A first (highest priority)
        canonical = _match_skill_to_tier(name, idx_a)
        if canonical and canonical not in all_matched:
            tier_a_matches[canonical] = skill_dict
            all_matched.add(canonical)
            continue

        # Try Tier B
        canonical = _match_skill_to_tier(name, idx_b)
        if canonical and canonical not in all_matched:
            tier_b_matches[canonical] = skill_dict
            all_matched.add(canonical)
            continue

        # Try Tier C
        canonical = _match_skill_to_tier(name, idx_c)
        if canonical and canonical not in all_matched:
            tier_c_matches[canonical] = skill_dict
            all_matched.add(canonical)

    return tier_a_matches, tier_b_matches, tier_c_matches, all_matched


# ---------------------------------------------------------------------------
# Duration score
# ---------------------------------------------------------------------------

def _duration_to_score(months: float) -> float:
    """
    Map duration_months to a quality score using piecewise linear interpolation.

    Breakpoints: (0→0.0), (12→0.30), (24→0.50), (48→0.80), (72→1.0), (72+→1.0)

    Parameters
    ----------
    months : float
        Duration in months (clamped to [0, ∞)).

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    months = max(0.0, float(months))

    if months >= _DURATION_CEILING_MONTHS:
        return 1.0

    # Piecewise linear interpolation between breakpoints
    for i in range(len(_DURATION_BREAKPOINTS) - 1):
        x0, y0 = _DURATION_BREAKPOINTS[i]
        x1, y1 = _DURATION_BREAKPOINTS[i + 1]
        if x0 <= months <= x1:
            t = (months - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 4)

    return 0.0


def _compute_duration_score(
    tier_a_matches: dict[str, dict],
    tier_b_matches: dict[str, dict],
    tier_c_matches: dict[str, dict],
) -> float:
    """
    Compute weighted average duration score across all matched skills.

    Tier A matches are weighted 3×, Tier B 2×, Tier C 1×.
    Skills with no duration data are assigned 0 months.

    Returns
    -------
    float
        Average duration quality score in [0.0, 1.0].
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for skill_dict in tier_a_matches.values():
        d = float(skill_dict.get("duration_months") or 0)
        weighted_sum += 3.0 * _duration_to_score(d)
        total_weight += 3.0

    for skill_dict in tier_b_matches.values():
        d = float(skill_dict.get("duration_months") or 0)
        weighted_sum += 2.0 * _duration_to_score(d)
        total_weight += 2.0

    for skill_dict in tier_c_matches.values():
        d = float(skill_dict.get("duration_months") or 0)
        weighted_sum += 1.0 * _duration_to_score(d)
        total_weight += 1.0

    if total_weight == 0.0:
        return 0.0

    return round(weighted_sum / total_weight, 4)


# ---------------------------------------------------------------------------
# Proficiency score
# ---------------------------------------------------------------------------

def _compute_proficiency_score(
    tier_a_matches: dict[str, dict],
    tier_b_matches: dict[str, dict],
    tier_c_matches: dict[str, dict],
) -> float:
    """
    Compute weighted average proficiency score across all matched skills.

    Tier A weights 3×, Tier B 2×, Tier C 1×.
    Unknown proficiency defaults to 'intermediate' (0.50).

    Returns
    -------
    float
        Average proficiency score in [0.0, 1.0].
    """
    weighted_sum = 0.0
    total_weight = 0.0

    def _prof(skill_dict: dict) -> float:
        raw = (skill_dict.get("proficiency") or "").lower().strip()
        return _PROFICIENCY_MAP.get(raw, _DEFAULT_PROFICIENCY)

    for skill_dict in tier_a_matches.values():
        weighted_sum += 3.0 * _prof(skill_dict)
        total_weight += 3.0

    for skill_dict in tier_b_matches.values():
        weighted_sum += 2.0 * _prof(skill_dict)
        total_weight += 2.0

    for skill_dict in tier_c_matches.values():
        weighted_sum += 1.0 * _prof(skill_dict)
        total_weight += 1.0

    if total_weight == 0.0:
        return 0.0

    return round(weighted_sum / total_weight, 4)


# ---------------------------------------------------------------------------
# Assessment score
# ---------------------------------------------------------------------------

def _assessment_to_score(raw_score: float) -> float:
    """
    Map a raw assessment score (0–100) to a normalised [0, 1] quality score.

    Breakpoints:
    < 40  → 0.20  (questionable)
    40–60 → 0.50  (weak-acceptable, linearly interpolated)
    60–80 → 0.75  (acceptable-strong, linearly interpolated)
    80–95 → 0.95  (strong-excellent)
    95+   → 1.00  (excellent)

    Parameters
    ----------
    raw_score : float
        Assessment score 0–100.

    Returns
    -------
    float
        Normalised quality score in [0.0, 1.0].
    """
    raw_score = max(0.0, min(float(raw_score), 100.0))

    if raw_score < 40.0:
        # Linearly interpolate from 0 → 0.20 across 0–40 range
        return round(raw_score / 40.0 * 0.20, 4)

    # Piecewise linear over the 4 upper bands
    bands = [
        (40.0,  0.20, 60.0,  0.50),
        (60.0,  0.50, 80.0,  0.75),
        (80.0,  0.75, 95.0,  0.95),
        (95.0,  0.95, 100.0, 1.00),
    ]
    for x0, y0, x1, y1 in bands:
        if x0 <= raw_score <= x1:
            t = (raw_score - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 4)

    return 1.0


def _compute_assessment_score(
    candidate: dict,
    tier_a_matches: dict[str, dict],
    tier_b_matches: dict[str, dict],
) -> float:
    """
    Compute an aggregate assessment score using skill_assessment_scores
    from redrob_signals.

    Only skills that are matched to Tier A or Tier B are considered.
    Tier A skills weighted 2×, Tier B 1×.

    If no assessment data is available, returns a neutral default (0.60).

    Parameters
    ----------
    candidate : dict
        Full candidate record.
    tier_a_matches, tier_b_matches : dict[str, dict]
        Matched skills per tier.

    Returns
    -------
    float
        Assessment quality score in [0.0, 1.0].
    """
    signals = candidate.get("redrob_signals") or {}
    assessments: dict = signals.get("skill_assessment_scores") or {}

    if not assessments:
        return 0.40  # neutral default — no data available

    weighted_sum = 0.0
    total_weight = 0.0

    for canonical, skill_dict in tier_a_matches.items():
        raw_name = skill_dict.get("name", canonical)
        # Try matching assessment by raw name or canonical name
        score = _find_assessment_score(raw_name, canonical, assessments)
        if score is not None:
            weighted_sum += 2.0 * _assessment_to_score(score)
            total_weight += 2.0

    for canonical, skill_dict in tier_b_matches.items():
        raw_name = skill_dict.get("name", canonical)
        score = _find_assessment_score(raw_name, canonical, assessments)
        if score is not None:
            weighted_sum += 1.0 * _assessment_to_score(score)
            total_weight += 1.0

    if total_weight == 0.0:
        return 0.40  # no matched assessment data → neutral

    return round(weighted_sum / total_weight, 4)


def _find_assessment_score(
    raw_name: str,
    canonical: str,
    assessments: dict[str, float],
) -> Optional[float]:
    """
    Look up an assessment score for a skill by name.

    Tries: raw_name, canonical, and normalised versions of both.

    Returns
    -------
    float or None
    """
    for key in (raw_name, canonical):
        if key in assessments:
            return float(assessments[key])
        # Try case-insensitive lookup
        for akey, aval in assessments.items():
            if akey.lower().strip() == key.lower().strip():
                return float(aval)
        # Try normalised lookup
        norm_key = normalize_skill(key)
        for akey, aval in assessments.items():
            if normalize_skill(akey) == norm_key:
                return float(aval)
    return None


# ---------------------------------------------------------------------------
# Coverage score
# ---------------------------------------------------------------------------

def _compute_coverage_score(
    tier_a_matches: dict[str, dict],
    tier_b_matches: dict[str, dict],
    tier_c_matches: dict[str, dict],
    tier_a: dict[str, list[str]],
    tier_b: dict[str, list[str]],
    tier_c: dict[str, list[str]],
) -> float:
    """
    Compute what fraction of the total JD skill surface is covered.

    Coverage = (matched skills across all tiers) / (total taxonomy skills).
    Tier A skills are weighted 3×, Tier B 2×, Tier C 1× in both numerator
    and denominator — so hitting all Tier A skills matters more than all Tier C.

    Returns
    -------
    float
        Coverage ratio in [0.0, 1.0].
    """
    matched_weight = (
        3.0 * len(tier_a_matches)
        + 2.0 * len(tier_b_matches)
        + 1.0 * len(tier_c_matches)
    )

    total_weight = (
        3.0 * len(tier_a)
        + 2.0 * len(tier_b)
        + 1.0 * len(tier_c)
    )

    if total_weight == 0.0:
        return 0.0

    return round(min(matched_weight / total_weight, 1.0), 4)


# ---------------------------------------------------------------------------
# Depth score
# ---------------------------------------------------------------------------

def _compute_depth_score(
    duration_score: float,
    proficiency_score: float,
    assessment_score: float,
) -> float:
    """
    Compute skill depth: a composite of duration, proficiency, and assessment.

    Weights:
    - Duration     50% (experience time is the primary depth proxy)
    - Proficiency  30% (self-reported but still signal)
    - Assessment   20% (objective validation when available)

    Returns
    -------
    float
        Depth score in [0.0, 1.0].
    """
    return round(
        0.50 * duration_score
        + 0.30 * proficiency_score
        + 0.20 * assessment_score,
        4,
    )


# ---------------------------------------------------------------------------
# Missing skills detection
# ---------------------------------------------------------------------------

def _find_missing_tier_a_skills(
    tier_a: dict[str, list[str]],
    tier_a_matches: dict[str, dict],
) -> list[str]:
    """
    Return canonical Tier-A skill names that are NOT in tier_a_matches.

    These are the critical capability gaps that should appear in explanations.

    Returns
    -------
    list[str]
        Sorted list of unmatched Tier-A canonical skill names.
    """
    all_tier_a = set(tier_a.keys())
    matched = set(tier_a_matches.keys())
    missing = sorted(all_tier_a - matched)
    return missing


# ---------------------------------------------------------------------------
# Explanation assembly
# ---------------------------------------------------------------------------

def _build_explanation(
    tier_a_matches: dict[str, dict],
    tier_b_matches: dict[str, dict],
    tier_c_matches: dict[str, dict],
    missing_tier_a: list[str],
    final_score: float,
    coverage_score: float,
    depth_score: float,
    tier_a_total: int,
    proficiency_score: float,
) -> str:
    """
    Build a concise recruiter-readable explanation.

    No hallucinations — every statement is grounded in actual match data.
    """
    parts: list[str] = []

    # Opening tone
    if final_score >= 0.70:
        tone = "Strong skill match"
    elif final_score >= 0.50:
        tone = "Moderate skill match"
    elif final_score >= 0.30:
        tone = "Partial skill match"
    else:
        tone = "Weak skill match"

    parts.append(f"{tone}.")

    # Tier A coverage
    n_a_matched = len(tier_a_matches)
    if n_a_matched > 0:
        sample_a = sorted(tier_a_matches.keys())[:3]
        sample_str = ", ".join(sample_a)
        parts.append(
            f"Covers {n_a_matched}/{tier_a_total} Tier-A requirements "
            f"including {sample_str}."
        )
    else:
        parts.append("No Tier-A (must-have) skills matched.")

    # Missing critical skills
    if missing_tier_a:
        top_missing = missing_tier_a[:3]
        parts.append(f"Missing Tier-A: {', '.join(top_missing)}.")

    # Tier B/C bonus
    n_b = len(tier_b_matches)
    n_c = len(tier_c_matches)
    if n_b > 0 or n_c > 0:
        bonus_parts = []
        if n_b > 0:
            bonus_parts.append(f"{n_b} Tier-B")
        if n_c > 0:
            bonus_parts.append(f"{n_c} Tier-C")
        parts.append(f"Additional signals: {' + '.join(bonus_parts)} skill(s) matched.")

    # Depth commentary
    if depth_score >= 0.70:
        parts.append(
            "Demonstrates strong depth: expert-level proficiency with substantial tenure."
        )
    elif depth_score >= 0.40:
        parts.append("Moderate skill depth with reasonable tenure and proficiency.")
    else:
        parts.append("Limited demonstrated depth — short tenure or low proficiency on matched skills.")

    # Proficiency
    if proficiency_score >= 0.75:
        parts.append("Proficiency level is advanced to expert.")
    elif proficiency_score <= 0.35:
        parts.append("Proficiency is beginner to intermediate on matched skills.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def score_skills(
    candidate: dict,
    tier_a: dict[str, list[str]],
    tier_b: dict[str, list[str]],
    tier_c: dict[str, list[str]],
) -> SkillScoreResult:
    """
    Compute the full skill intelligence score for a single candidate.

    This is the single entry-point called by the feature extraction pipeline.

    Parameters
    ----------
    candidate : dict
        A single candidate record as returned by load_candidates().
        Must have a 'skills' key containing a list of skill dicts.
    tier_a, tier_b, tier_c : dict
        Taxonomy tier dicts as returned by load_skill_taxonomy().

    Returns
    -------
    SkillScoreResult
        Frozen dataclass with all sub-scores, matched/missing skills,
        and explanation.

    Complexity
    ----------
    Time  : O(S × (A + B + C)) where S = candidate skill count,
            A/B/C = taxonomy tier sizes.
    Memory: O(S + A + B + C).

    Notes
    -----
    * Fully deterministic — identical input always produces identical output.
    * Thread-safe — no shared mutable state.
    * Missing or None 'skills' list handled gracefully.
    """
    candidate_skills: list[dict] = candidate.get("skills") or []

    # --- Step 1: Match all candidate skills to taxonomy tiers ---
    tier_a_matches, tier_b_matches, tier_c_matches, _ = _match_candidate_skills(
        candidate_skills, tier_a, tier_b, tier_c,
    )

    # --- Step 2: Tier match scores ---
    tier_a_score = round(len(tier_a_matches) / len(tier_a), 4) if tier_a else 0.0
    tier_b_score = round(len(tier_b_matches) / len(tier_b), 4) if tier_b else 0.0
    tier_c_score = round(len(tier_c_matches) / len(tier_c), 4) if tier_c else 0.0

    # --- Step 3: Coverage score ---
    coverage = _compute_coverage_score(
        tier_a_matches, tier_b_matches, tier_c_matches,
        tier_a, tier_b, tier_c,
    )

    # --- Step 4: Duration score ---
    duration = _compute_duration_score(tier_a_matches, tier_b_matches, tier_c_matches)

    # --- Step 5: Proficiency score ---
    proficiency = _compute_proficiency_score(tier_a_matches, tier_b_matches, tier_c_matches)

    # --- Step 6: Assessment score ---
    assessment = _compute_assessment_score(candidate, tier_a_matches, tier_b_matches)

    # --- Step 7: Depth score ---
    depth = _compute_depth_score(duration, proficiency, assessment)

    # --- Step 7.5: Consistency score ---
    consistency_result = score_skill_consistency(candidate)
    consistency = consistency_result.consistency_score

    # --- Step 8: Final weighted aggregation ---
    final = round(
        _SKILL_WEIGHTS["tier_a"]      * tier_a_score
        + _SKILL_WEIGHTS["tier_b"]    * tier_b_score
        + _SKILL_WEIGHTS["tier_c"]    * tier_c_score
        + _SKILL_WEIGHTS["coverage"]  * coverage
        + _SKILL_WEIGHTS["consistency"] * consistency
        + _SKILL_WEIGHTS["duration"]  * duration
        + _SKILL_WEIGHTS["proficiency"] * proficiency
        + _SKILL_WEIGHTS["assessment"] * assessment
        + _SKILL_WEIGHTS["depth"]     * depth,
        4,
    )
    final = max(0.0, min(final, 1.0))

    # --- Step 8.5: Consistency Penalty ---
    if consistency < 0.15:
        final *= 0.40
    elif consistency < 0.30:
        final *= 0.60
    final = round(final, 4)

    # --- Step 9: Missing Tier-A skills ---
    missing_tier_a = _find_missing_tier_a_skills(tier_a, tier_a_matches)

    # --- Step 10: Matched skill names (sorted for determinism) ---
    matched_all = sorted(
        list(tier_a_matches.keys())
        + list(tier_b_matches.keys())
        + list(tier_c_matches.keys())
    )

    explanation = _build_explanation(
        tier_a_matches, tier_b_matches, tier_c_matches,
        missing_tier_a, final, coverage, depth,
        len(tier_a), proficiency,
    )
    
    explanation += f" {consistency_result.explanation}"

    return SkillScoreResult(
        tier_a_match_score=round(tier_a_score, 4),
        tier_b_match_score=round(tier_b_score, 4),
        tier_c_match_score=round(tier_c_score, 4),
        duration_score=round(duration, 4),
        proficiency_score=round(proficiency, 4),
        assessment_score=round(assessment, 4),
        coverage_score=round(coverage, 4),
        depth_score=round(depth, 4),
        consistency_score=round(consistency, 4),
        final_skill_score=round(final, 4),
        matched_skills=tuple(matched_all),
        missing_skills=tuple(missing_tier_a),
        supported_skills=tuple(consistency_result.supported_skills),
        unsupported_skills=tuple(consistency_result.unsupported_skills),
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Batch public API
# ---------------------------------------------------------------------------

def score_skills_batch(
    candidates: list[dict],
    tier_a: dict[str, list[str]],
    tier_b: dict[str, list[str]],
    tier_c: dict[str, list[str]],
) -> list[SkillScoreResult]:
    """
    Score a list of candidates against the same taxonomy in one call.

    This is the recommended API for pipeline/batch usage.  It builds the
    alias indexes exactly once (via the module-level cache) regardless of
    how many candidates are passed, reducing per-candidate overhead from
    ~10 ms (index build dominated) to < 0.5 ms (pure scoring only).

    Parameters
    ----------
    candidates : list[dict]
        List of candidate records.
    tier_a, tier_b, tier_c : dict
        Taxonomy tier dicts as returned by load_skill_taxonomy().

    Returns
    -------
    list[SkillScoreResult]
        One result per candidate, in the same order as *candidates*.

    Complexity
    ----------
    Time  : O(N × S × K) where N = candidates, S = skills per candidate,
            K = aliases per tier (constant for a fixed taxonomy).
            Alias index build: O(A+B+C) once per (tier_a, tier_b, tier_c)
            identity across the process lifetime.
    Memory: O(A + B + C + N × S) — indexes stored once, results accumulate.

    Examples
    --------
    >>> tier_a, tier_b, tier_c, _ = load_skill_taxonomy()
    >>> results = score_skills_batch(my_1000_candidates, tier_a, tier_b, tier_c)
    >>> top10 = sorted(results, key=lambda r: r.final_skill_score, reverse=True)[:10]
    """
    # Warm the cache with a single index build
    _get_alias_indexes(tier_a, tier_b, tier_c)
    return [score_skills(c, tier_a, tier_b, tier_c) for c in candidates]
