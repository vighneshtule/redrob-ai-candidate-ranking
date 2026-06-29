"""
src/pipeline/reasoning_generator.py
=====================================
Fact-grounded explanation generator for the Redrob ranking engine.

Produces recruiter-readable reasoning strings from CandidateFeatures.
All statements are derived directly from feature values — no hallucination.

Design principles
-----------------
* Deterministic: same input → same output, always.
* Data-grounded: every claim traceable to a feature value.
* No LLMs, no templates with placeholder text.
* Tone scales with final_score: Strong / Good / Moderate / Weak / Vetoed.
* Modular: each feature block generates an independent phrase,
  assembled into a coherent sentence.

Public API
----------
    generate_explanation(features: CandidateFeatures, final_score: float) -> str
"""

from __future__ import annotations

from src.pipeline.feature_extractor import CandidateFeatures

# ---------------------------------------------------------------------------
# Score band thresholds
# ---------------------------------------------------------------------------

_STRONG_THRESHOLD: float = 0.70
_GOOD_THRESHOLD: float = 0.50
_MODERATE_THRESHOLD: float = 0.30

# Sub-score thresholds for phrase selection
_HIGH: float = 0.70
_MED: float = 0.40
_LOW: float = 0.20


# ---------------------------------------------------------------------------
# Private phrase builders
# ---------------------------------------------------------------------------

def _tone_phrase(final_score: float) -> str:
    """Opening tone based on overall final_score band."""
    if final_score >= _STRONG_THRESHOLD:
        return "Strong candidate"
    if final_score >= _GOOD_THRESHOLD:
        return "Good candidate"
    if final_score >= _MODERATE_THRESHOLD:
        return "Moderate-fit candidate"
    return "Weak candidate"


def _career_phrase(features: CandidateFeatures) -> str:
    """Describe career relevance signal."""
    s = features.career_score
    if s >= _HIGH:
        return "with highly relevant AI/ML/Search career background"
    if s >= _MED:
        return "with relevant technical career history"
    if s >= _LOW:
        return "with partially relevant career experience"
    return "with limited AI/ML career relevance"


def _skill_phrase(features: CandidateFeatures) -> str:
    """Describe Tier-A skill coverage."""
    fv = features.final_feature_vector
    tier_a = fv.get("tier_a_match_score", 0.0)
    cov = fv.get("coverage_score", 0.0)
    skill = features.skill_score

    if skill >= _HIGH and tier_a >= _HIGH:
        return (
            f"Tier-A skill coverage is strong (score={tier_a:.2f}); "
            f"broad taxonomy coverage ({cov:.0%})"
        )
    if skill >= _MED and tier_a >= _MED:
        return (
            f"moderate Tier-A skill match (score={tier_a:.2f}) "
            f"with {cov:.0%} overall taxonomy coverage"
        )
    if tier_a > 0:
        return (
            f"partial Tier-A skill match (score={tier_a:.2f}); "
            f"limited taxonomy coverage ({cov:.0%})"
        )
    return "no Tier-A skill matches against the JD taxonomy"


def _behavior_phrase(features: CandidateFeatures) -> str:
    """Describe behavioral signals: availability, engagement, notice."""
    fv = features.final_feature_vector
    avail = fv.get("availability_score", 0.0)
    eng = fv.get("recruiter_engagement_score", 0.0)
    notice = fv.get("notice_period_score", 0.0)
    risk = fv.get("behavioral_risk_score", 1.0)

    parts: list[str] = []

    if avail >= _HIGH:
        parts.append("highly available")
    elif avail >= _MED:
        parts.append("reasonably available")
    else:
        parts.append("limited availability")

    if eng >= _HIGH:
        parts.append("strong recruiter engagement")
    elif eng >= _MED:
        parts.append("moderate recruiter responsiveness")
    else:
        parts.append("low recruiter responsiveness")

    if notice >= _HIGH:
        parts.append("short notice period")
    elif notice >= _MED:
        parts.append("acceptable notice period")
    else:
        parts.append("long notice period")

    if risk <= 0.30:
        parts.append("low behavioral risk")
    elif risk >= 0.70:
        parts.append("elevated behavioral risk")

    return "; ".join(parts) if parts else "behavioral signals are neutral"


def _integrity_phrase(features: CandidateFeatures) -> str:
    """Describe integrity health."""
    if features.anomaly_count == 0 and features.stuffing_score < 0.20:
        return "Clean profile — no anomalies detected"
    parts: list[str] = []
    if features.anomaly_count > 0:
        parts.append(
            f"{features.anomaly_count} anomaly point(s) detected "
            f"({'; '.join(features.anomaly_flags[:2])})"
        )
    if features.stuffing_score >= 0.50:
        parts.append(
            f"keyword-stuffing risk = {features.stuffing_score:.0%}"
        )
    return "; ".join(parts) if parts else "Minor integrity signals"


def _veto_phrase(features: CandidateFeatures) -> str:
    """Explain why a candidate was vetoed."""
    flags_text = (
        " | ".join(features.anomaly_flags[:3]) if features.anomaly_flags
        else "threshold exceeded"
    )
    return (
        f"VETOED — candidate excluded from ranking due to honeypot signals "
        f"(anomaly_count={features.anomaly_count}): {flags_text}."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_explanation(
    features: CandidateFeatures,
    final_score: float,
) -> str:
    """
    Generate a recruiter-readable explanation for a scored candidate.

    All statements are derived from feature values — no hallucinated content.

    Parameters
    ----------
    features : CandidateFeatures
        Feature record from extract_features().
    final_score : float
        The computed ranking score (from compute_final_score()).

    Returns
    -------
    str
        A single-paragraph explanation string.  Always non-empty.

    Examples
    --------
    >>> # A strong candidate
    >>> expl = generate_explanation(features, 0.82)
    >>> "Strong candidate" in expl
    True

    >>> # A vetoed candidate
    >>> expl = generate_explanation(vetoed_features, 0.0)
    >>> "VETOED" in expl
    True

    Complexity: O(1)
    """
    if features.veto_candidate:
        return _veto_phrase(features)

    tone = _tone_phrase(final_score)
    career = _career_phrase(features)
    skills = _skill_phrase(features)
    behavior = _behavior_phrase(features)
    integrity = _integrity_phrase(features)

    explanation = (
        f"{tone} {career}. "
        f"Skills: {skills}. "
        f"Behavioral signals: {behavior}. "
        f"Integrity: {integrity}."
    )

    return explanation
