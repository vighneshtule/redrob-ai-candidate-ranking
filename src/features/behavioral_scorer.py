"""
src/features/behavioral_scorer.py
===================================
Behavioral Intelligence Engine for the Redrob candidate ranking system.

This module answers ONE question:
    "Is this candidate realistically hireable right now?"

It does NOT measure technical ability. It models recruiter reality:
platform engagement, responsiveness, interview reliability, offer acceptance,
notice period logistics, and inferred hiring friction.

Design principles
-----------------
* Pure Python — no LLMs, no embeddings, no external calls.
* Deterministic — identical input always produces identical output.
* All scoring is transparent: every number can be traced to a raw signal.
* Graceful degradation — missing fields fall back to conservative defaults
  (never crash, never assume best case on missing data).
* Thread-safe — no shared mutable state.

Signal Sources (from redrob_signals)
--------------------------------------
    open_to_work_flag           bool
    last_active_date            str (ISO-8601)
    recruiter_response_rate     float  [0, 1]
    saved_by_recruiters_30d     int    (optional)
    search_appearance_30d       int    (optional)
    interview_completion_rate   float  [0, 1]
    offer_acceptance_rate       float  [0, 1]
    notice_period_days          int
    github_activity_score       float  [0, 100]

Output
------
    BehaviorScoreResult  — frozen dataclass with 9 fields + explanation

Sub-scorer weights (sum to 1.0 over non-risk scorers)
-------------------------------------------------------
    availability_score          0.20
    activity_score              0.20
    recruiter_engagement_score  0.20
    interview_reliability_score 0.15
    hiring_probability_score    0.15
    notice_period_score         0.10

Behavioral risk is applied as a penalty multiplier, NOT a direct weight:
    final = weighted_sum × (1 − 0.5 × behavioral_risk_score)

Public API
----------
    score_behavior(candidate, today=None) -> BehaviorScoreResult
    BehaviorScoreResult                   — frozen dataclass
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from src.utils.date_utils import parse_date

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BehaviorScoreResult:
    """
    Output of score_behavior().  Frozen → hashable, thread-safe.

    Attributes
    ----------
    availability_score : float [0, 1]
        Whether the candidate is signalling openness to opportunities.
    activity_score : float [0, 1]
        How recently the candidate was active on the platform.
    recruiter_engagement_score : float [0, 1]
        How responsive this candidate is to recruiter outreach.
    interview_reliability_score : float [0, 1]
        Historical interview completion rate — proxy for show-up reliability.
    hiring_probability_score : float [0, 1]
        Historical offer acceptance rate — proxy for hire probability.
    notice_period_score : float [0, 1]
        How quickly the candidate can join (lower notice = higher score).
    behavioral_risk_score : float [0, 1]
        Composite negative-risk signal. Higher = riskier to pursue.
    final_behavior_score : float [0, 1]
        Weighted aggregate with risk penalty applied.
    explanation : str
        Human-readable recruiter-facing reasoning string.
    """

    availability_score: float
    activity_score: float
    recruiter_engagement_score: float
    interview_reliability_score: float
    hiring_probability_score: float
    notice_period_score: float
    behavioral_risk_score: float
    final_behavior_score: float
    explanation: str


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Sub-scorer weights (must sum to 1.0 — risk applied separately as a multiplier)
_BEHAVIOR_WEIGHTS: dict[str, float] = {
    "availability":           0.20,
    "activity":               0.20,
    "recruiter_engagement":   0.20,
    "interview_reliability":  0.15,
    "hiring_probability":     0.15,
    "notice_period":          0.10,
}
assert abs(sum(_BEHAVIOR_WEIGHTS.values()) - 1.0) < 1e-9, "Behavior weights must sum to 1.0"

# Risk penalty fraction: final = weighted × (1 − RISK_PENALTY_FRACTION × risk)
_RISK_PENALTY_FRACTION: float = 0.50

# Activity score breakpoints (days_since_active → score)
_ACTIVITY_BREAKPOINTS: list[tuple[int, float]] = [
    (7,   1.00),
    (30,  0.90),
    (60,  0.70),
    (90,  0.50),
    (180, 0.30),
]
_ACTIVITY_FLOOR: float = 0.10  # score for > 180 days inactive

# Notice period score breakpoints (notice_period_days → score)
_NOTICE_BREAKPOINTS: list[tuple[int, float]] = [
    (30,  1.00),
    (60,  0.80),
    (90,  0.60),
    (120, 0.40),
]
_NOTICE_FLOOR: float = 0.20  # score for > 120 days notice

# Availability scores
_OPEN_TO_WORK_SCORE: float = 1.0
_NOT_OPEN_TO_WORK_SCORE: float = 0.40  # Never 0 — strong candidates may not flag

# Recruiter engagement: saved_by_recruiters_30d and search_appearance_30d bonuses
_SAVED_BY_RECRUITERS_BONUS_THRESHOLD: int = 3   # ≥3 saves → add bonus
_SAVED_BY_RECRUITERS_BONUS: float = 0.05
_SEARCH_APPEARANCE_BONUS_THRESHOLD: int = 50    # ≥50 appearances → add bonus
_SEARCH_APPEARANCE_BONUS: float = 0.03

# Risk thresholds for component categorisation
_INACTIVE_RISK_THRESHOLD_DAYS: int = 90         # > 90 days → contributes to risk
_LOW_RESPONSE_RISK_THRESHOLD: float = 0.25      # < 0.25 response rate → risk
_LONG_NOTICE_RISK_THRESHOLD_DAYS: int = 90      # > 90 days notice → risk
_LOW_INTERVIEW_RISK_THRESHOLD: float = 0.40     # < 0.40 completion rate → risk
_LOW_ACCEPTANCE_RISK_THRESHOLD: float = 0.30    # < 0.30 acceptance rate → risk

# Default fallback values for missing fields (conservative but not zero)
_DEFAULT_RECRUITER_RESPONSE: float = 0.50       # median assumption
_DEFAULT_INTERVIEW_COMPLETION: float = 0.60     # median assumption
_DEFAULT_OFFER_ACCEPTANCE: float = 0.50         # median assumption
_DEFAULT_NOTICE_PERIOD_DAYS: int = 60           # 60 days — common in India


# ---------------------------------------------------------------------------
# Helper: today
# ---------------------------------------------------------------------------

def _get_today() -> date:
    """Return UTC today. Separate function so tests can monkeypatch or inject."""
    return datetime.utcnow().date()


# ---------------------------------------------------------------------------
# Helper: piecewise step-function lookup
# ---------------------------------------------------------------------------

def _step_lookup(
    value: float,
    breakpoints: list[tuple[int, float]],
    floor: float,
) -> float:
    """
    Apply a piecewise step function to map *value* to a score.

    *breakpoints* is an ordered list of (threshold, score) tuples.
    If value ≤ threshold → return score (first match wins).
    If value exceeds all thresholds → return *floor*.

    Parameters
    ----------
    value : float
        The input value to map (e.g. days since active, notice period days).
    breakpoints : list of (int, float)
        Ordered (threshold, score) pairs, ascending thresholds.
    floor : float
        Score returned when value exceeds all thresholds.

    Returns
    -------
    float
        Mapped score.
    """
    for threshold, score in breakpoints:
        if value <= threshold:
            return score
    return floor


# ---------------------------------------------------------------------------
# Sub-scorer 1: Availability
# ---------------------------------------------------------------------------

def _score_availability(signals: dict) -> tuple[float, str]:
    """
    Compute availability score from open_to_work_flag.

    Logic
    -----
    open_to_work = True  → 1.0 (actively signalling)
    open_to_work = False → 0.40 (not flagged but could still be reachable)
    Missing / None       → 0.40 (conservative default — don't assume availability)

    Returns
    -------
    (score, explanation_fragment)
    """
    flag = signals.get("open_to_work_flag")

    if flag is True:
        return _OPEN_TO_WORK_SCORE, "actively open to work"
    elif flag is False:
        return _NOT_OPEN_TO_WORK_SCORE, "not currently flagged as open to work"
    else:
        # None / missing — conservative default
        return _NOT_OPEN_TO_WORK_SCORE, "availability status unknown"


# ---------------------------------------------------------------------------
# Sub-scorer 2: Activity
# ---------------------------------------------------------------------------

def _score_activity(signals: dict, today: date) -> tuple[float, str]:
    """
    Compute activity score from last_active_date.

    Maps days-since-active to a score using a step function:
    0-7d → 1.0, 8-30d → 0.9, 31-60d → 0.7, 61-90d → 0.5,
    91-180d → 0.3, >180d → 0.1

    Missing or unparseable last_active_date defaults to 0.3 (moderately stale).

    Returns
    -------
    (score, explanation_fragment)
    """
    raw = signals.get("last_active_date")
    last_active = parse_date(raw) if raw else None

    if last_active is None:
        return 0.30, "last active date unknown"

    days_since = (today - last_active).days
    if days_since < 0:
        days_since = 0  # future date in data → treat as today

    score = _step_lookup(float(days_since), _ACTIVITY_BREAKPOINTS, _ACTIVITY_FLOOR)

    if days_since <= 7:
        expl = f"active {days_since} day(s) ago (very recent)"
    elif days_since <= 30:
        expl = f"active {days_since} days ago (recent)"
    elif days_since <= 60:
        expl = f"active {days_since} days ago (moderately recent)"
    elif days_since <= 90:
        expl = f"active {days_since} days ago (somewhat stale)"
    elif days_since <= 180:
        expl = f"inactive for {days_since} days (concerning)"
    else:
        expl = f"inactive for {days_since} days (significant inactivity)"

    return round(score, 4), expl


# ---------------------------------------------------------------------------
# Sub-scorer 3: Recruiter Engagement
# ---------------------------------------------------------------------------

def _score_recruiter_engagement(signals: dict) -> tuple[float, str]:
    """
    Compute recruiter engagement score from recruiter_response_rate,
    with optional bonuses from saved_by_recruiters_30d and search_appearance_30d.

    Formula
    -------
    base = recruiter_response_rate (normalised to [0, 1])
    + bonus_saved    if saved_by_recruiters_30d >= threshold
    + bonus_search   if search_appearance_30d >= threshold
    Capped at 1.0.

    Missing recruiter_response_rate → default 0.50.

    Returns
    -------
    (score, explanation_fragment)
    """
    raw_rate = signals.get("recruiter_response_rate")

    if raw_rate is None:
        base = _DEFAULT_RECRUITER_RESPONSE
        rate_str = "response rate unknown (using default)"
    else:
        # rate is already [0, 1] per schema; clamp defensively
        base = max(0.0, min(float(raw_rate), 1.0))
        pct = int(base * 100)
        rate_str = f"{pct}% recruiter response rate"

    # Optional engagement bonuses
    bonus = 0.0
    bonus_parts: list[str] = []

    saved = signals.get("saved_by_recruiters_30d") or signals.get("saved_by_recruiters") or 0
    if isinstance(saved, (int, float)) and saved >= _SAVED_BY_RECRUITERS_BONUS_THRESHOLD:
        bonus += _SAVED_BY_RECRUITERS_BONUS
        bonus_parts.append(f"saved by {int(saved)} recruiter(s)")

    appearances = signals.get("search_appearance_30d") or signals.get("search_appearance_count") or 0
    if isinstance(appearances, (int, float)) and appearances >= _SEARCH_APPEARANCE_BONUS_THRESHOLD:
        bonus += _SEARCH_APPEARANCE_BONUS
        bonus_parts.append(f"{int(appearances)} search appearances")

    score = round(min(base + bonus, 1.0), 4)

    expl = rate_str
    if bonus_parts:
        expl += f"; {', '.join(bonus_parts)}"

    return score, expl


# ---------------------------------------------------------------------------
# Sub-scorer 4: Interview Reliability
# ---------------------------------------------------------------------------

def _score_interview_reliability(signals: dict) -> tuple[float, str]:
    """
    Compute interview reliability score from interview_completion_rate.

    A high completion rate means the candidate shows up, follows process,
    and doesn't ghost after accepting interview slots.

    interview_completion_rate is [0, 1] per schema.
    Missing → default 0.60 (moderate assumption).

    Returns
    -------
    (score, explanation_fragment)
    """
    raw = signals.get("interview_completion_rate")

    if raw is None:
        score = _DEFAULT_INTERVIEW_COMPLETION
        expl = "interview completion rate unknown (using default)"
    else:
        score = round(max(0.0, min(float(raw), 1.0)), 4)
        pct = int(score * 100)
        if score >= 0.80:
            expl = f"{pct}% interview completion rate (highly reliable)"
        elif score >= 0.60:
            expl = f"{pct}% interview completion rate (reliable)"
        elif score >= 0.40:
            expl = f"{pct}% interview completion rate (moderate)"
        else:
            expl = f"{pct}% interview completion rate (low — may ghost interviews)"

    return round(score, 4), expl


# ---------------------------------------------------------------------------
# Sub-scorer 5: Hiring Probability
# ---------------------------------------------------------------------------

def _score_hiring_probability(signals: dict) -> tuple[float, str]:
    """
    Compute hiring probability score from offer_acceptance_rate.

    A high acceptance rate indicates the candidate is serious about
    offers they entertain and is likely to convert if made an offer.

    offer_acceptance_rate is [0, 1] per schema.
    Missing → default 0.50 (unknown).

    Returns
    -------
    (score, explanation_fragment)
    """
    raw = signals.get("offer_acceptance_rate")

    if raw is None:
        score = _DEFAULT_OFFER_ACCEPTANCE
        expl = "offer acceptance rate unknown (using default)"
    else:
        score = round(max(0.0, min(float(raw), 1.0)), 4)
        pct = int(score * 100)
        if score >= 0.70:
            expl = f"{pct}% offer acceptance rate (high conversion likelihood)"
        elif score >= 0.50:
            expl = f"{pct}% offer acceptance rate (moderate conversion)"
        elif score >= 0.30:
            expl = f"{pct}% offer acceptance rate (low — may decline offers)"
        else:
            expl = f"{pct}% offer acceptance rate (very low — high drop-off risk)"

    return round(score, 4), expl


# ---------------------------------------------------------------------------
# Sub-scorer 6: Notice Period
# ---------------------------------------------------------------------------

def _score_notice_period(signals: dict) -> tuple[float, str]:
    """
    Compute notice period score from notice_period_days.

    Lower notice period = higher score (can join sooner).

    Step function:
    0-30d   → 1.00 (ideal — can join within month or immediately)
    31-60d  → 0.80 (acceptable)
    61-90d  → 0.60 (standard — manageable)
    91-120d → 0.40 (long — reduces priority)
    >120d   → 0.20 (very long — significant hiring friction)

    Missing notice_period_days → default 60 days (common in India).

    Returns
    -------
    (score, explanation_fragment)
    """
    raw = signals.get("notice_period_days")

    if raw is None:
        days = _DEFAULT_NOTICE_PERIOD_DAYS
        expl = f"notice period unknown (assuming {days} days)"
    else:
        days = int(max(0, float(raw)))
        expl = f"{days}-day notice period"

    score = _step_lookup(float(days), _NOTICE_BREAKPOINTS, _NOTICE_FLOOR)

    if days <= 30:
        expl += " (can join quickly)"
    elif days <= 60:
        expl += " (manageable)"
    elif days <= 90:
        expl += " (standard but slower)"
    else:
        expl += " (significant hiring delay)"

    return round(score, 4), expl


# ---------------------------------------------------------------------------
# Sub-scorer 7: Behavioral Risk
# ---------------------------------------------------------------------------

def _score_behavioral_risk(
    signals: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute a composite behavioral risk score [0, 1].

    Higher = riskier. Applied as a penalty multiplier on final_behavior_score.

    Risk components (equally weighted):
    ────────────────────────────────────
    1. Inactivity risk     — days_since_active > 90 days
    2. Response risk       — recruiter_response_rate < 0.25
    3. Notice period risk  — notice_period_days > 90
    4. Interview risk      — interview_completion_rate < 0.40
    5. Acceptance risk     — offer_acceptance_rate < 0.30

    Each component contributes 0.0 or its magnitude to total risk.
    Risk magnitude is proportional to how far beyond the threshold the value is.
    Score is normalised to [0, 1].

    Returns
    -------
    (score, explanation_fragment)
    """
    risk_components: list[float] = []
    risk_flags: list[str] = []

    # --- Inactivity risk ---
    raw_active = signals.get("last_active_date")
    last_active = parse_date(raw_active) if raw_active else None
    if last_active is None:
        # Unknown → moderate inactivity risk
        inactivity_risk = 0.40
        risk_flags.append("last active date unknown")
    else:
        days_since = max(0, (today - last_active).days)
        if days_since > _INACTIVE_RISK_THRESHOLD_DAYS:
            # Linear risk: 90d→0.2, 180d→0.6, 365d→1.0
            inactivity_risk = min(
                (days_since - _INACTIVE_RISK_THRESHOLD_DAYS) / 275.0, 1.0
            )
            risk_flags.append(f"inactive {days_since}d")
        else:
            inactivity_risk = 0.0

    risk_components.append(inactivity_risk)

    # --- Response risk ---
    raw_rate = signals.get("recruiter_response_rate")
    if raw_rate is None:
        response_risk = 0.20  # unknown → mild risk
    else:
        rate = max(0.0, min(float(raw_rate), 1.0))
        if rate < _LOW_RESPONSE_RISK_THRESHOLD:
            # Linear: 0.25→0, 0.0→1.0
            response_risk = 1.0 - (rate / _LOW_RESPONSE_RISK_THRESHOLD)
            risk_flags.append(f"low response rate ({int(rate*100)}%)")
        else:
            response_risk = 0.0

    risk_components.append(response_risk)

    # --- Notice period risk ---
    raw_notice = signals.get("notice_period_days")
    if raw_notice is None:
        notice_risk = 0.15  # unknown → mild risk
    else:
        notice_days = int(max(0, float(raw_notice)))
        if notice_days > _LONG_NOTICE_RISK_THRESHOLD_DAYS:
            # Linear: 90d→0, 180d→0.5, 270d+→1.0
            notice_risk = min((notice_days - _LONG_NOTICE_RISK_THRESHOLD_DAYS) / 180.0, 1.0)
            risk_flags.append(f"{notice_days}d notice period")
        else:
            notice_risk = 0.0

    risk_components.append(notice_risk)

    # --- Interview completion risk ---
    raw_interview = signals.get("interview_completion_rate")
    if raw_interview is None:
        interview_risk = 0.15  # unknown → mild risk
    else:
        completion = max(0.0, min(float(raw_interview), 1.0))
        if completion < _LOW_INTERVIEW_RISK_THRESHOLD:
            # Linear: 0.40→0, 0.0→1.0
            interview_risk = 1.0 - (completion / _LOW_INTERVIEW_RISK_THRESHOLD)
            risk_flags.append(f"low interview completion ({int(completion*100)}%)")
        else:
            interview_risk = 0.0

    risk_components.append(interview_risk)

    # --- Offer acceptance risk ---
    raw_acceptance = signals.get("offer_acceptance_rate")
    if raw_acceptance is None:
        acceptance_risk = 0.15  # unknown → mild risk
    else:
        acceptance = max(0.0, min(float(raw_acceptance), 1.0))
        if acceptance < _LOW_ACCEPTANCE_RISK_THRESHOLD:
            # Linear: 0.30→0, 0.0→1.0
            acceptance_risk = 1.0 - (acceptance / _LOW_ACCEPTANCE_RISK_THRESHOLD)
            risk_flags.append(f"low offer acceptance ({int(acceptance*100)}%)")
        else:
            acceptance_risk = 0.0

    risk_components.append(acceptance_risk)

    # Aggregate: simple average of all 5 risk components
    risk_score = sum(risk_components) / len(risk_components)
    risk_score = round(min(risk_score, 1.0), 4)

    if risk_flags:
        expl = f"risk factors: {'; '.join(risk_flags)}"
    else:
        expl = "no significant behavioral risk factors"

    return risk_score, expl


# ---------------------------------------------------------------------------
# Explanation assembly
# ---------------------------------------------------------------------------

def _build_explanation(
    availability_expl: str,
    activity_expl: str,
    engagement_expl: str,
    interview_expl: str,
    hiring_expl: str,
    notice_expl: str,
    risk_expl: str,
    final_score: float,
    signals: dict,
) -> str:
    """
    Assemble a concise, recruiter-readable explanation from sub-scorer fragments.

    Uses conditional templates to produce natural language rather than
    a mechanical concatenation of all fragments.

    No hallucinations — every statement maps directly to a raw value.
    """
    parts: list[str] = []

    # Opening tone: based on final score
    if final_score >= 0.75:
        tone = "Strong behavioral signals"
    elif final_score >= 0.55:
        tone = "Moderate behavioral signals"
    elif final_score >= 0.35:
        tone = "Mixed behavioral signals"
    else:
        tone = "Weak behavioral signals"

    parts.append(f"{tone}.")

    # Availability
    open_to_work = signals.get("open_to_work_flag")
    if open_to_work is True:
        parts.append("Candidate is actively open to work.")

    # Activity
    parts.append(f"Platform activity: {activity_expl}.")

    # Recruiter engagement
    raw_rate = signals.get("recruiter_response_rate")
    if raw_rate is not None:
        rate_pct = int(float(raw_rate) * 100)
        if rate_pct >= 70:
            parts.append(f"Highly responsive to recruiters ({rate_pct}% response rate).")
        elif rate_pct >= 40:
            parts.append(f"Responds to recruiters ({rate_pct}% response rate).")
        else:
            parts.append(f"Low recruiter responsiveness ({rate_pct}% response rate).")

    # Interview reliability
    interview_rate = signals.get("interview_completion_rate")
    if interview_rate is not None:
        pct = int(float(interview_rate) * 100)
        if pct >= 80:
            parts.append(f"Strong interview attendance history ({pct}% completion rate).")
        elif pct < 50:
            parts.append(f"Poor interview completion history ({pct}% completion rate).")

    # Hiring probability
    acceptance_rate = signals.get("offer_acceptance_rate")
    if acceptance_rate is not None:
        pct = int(float(acceptance_rate) * 100)
        if pct >= 70:
            parts.append(f"High offer acceptance rate ({pct}%).")
        elif pct < 30:
            parts.append(f"Low offer acceptance rate ({pct}%) — conversion risk.")

    # Notice period
    notice_days = signals.get("notice_period_days")
    if notice_days is not None:
        nd = int(notice_days)
        if nd <= 30:
            parts.append(f"Can join within {nd} day(s).")
        elif nd <= 60:
            parts.append(f"Notice period: {nd} days (manageable).")
        else:
            parts.append(f"Notice period: {nd} days (significant delay).")

    # Risk flags (only if non-trivial)
    if "no significant" not in risk_expl:
        parts.append(f"Behavioral risk: {risk_expl}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def score_behavior(
    candidate: dict,
    today: Optional[date] = None,
) -> BehaviorScoreResult:
    """
    Compute the full behavioral score for a single candidate.

    This is the single entry-point called by the feature extraction pipeline.
    All six sub-scorers run independently; results are aggregated with a
    risk penalty into ``final_behavior_score``.

    Parameters
    ----------
    candidate : dict
        A single candidate record as returned by ``load_candidates()``.
        Must contain a ``redrob_signals`` key.
    today : date, optional
        Reference date for recency calculations.  Defaults to UTC today.
        Inject a fixed date in tests for determinism.

    Returns
    -------
    BehaviorScoreResult
        Frozen dataclass with all sub-scores, final score, and explanation.

    Complexity
    ----------
    Time  : O(1) — fixed number of dict lookups and arithmetic operations.
    Memory: O(1) — no variable-size data structures.

    Notes
    -----
    * Function is PURELY FUNCTIONAL — no side-effects, no global state writes.
    * Safe to call from multiple threads simultaneously.
    * Missing redrob_signals keys are handled gracefully via defaults.
    """
    ref_today: date = today or _get_today()
    signals: dict = candidate.get("redrob_signals") or {}

    # --- Run all sub-scorers ---
    availability, avail_expl = _score_availability(signals)
    activity, act_expl = _score_activity(signals, ref_today)
    engagement, eng_expl = _score_recruiter_engagement(signals)
    interview, int_expl = _score_interview_reliability(signals)
    hiring, hire_expl = _score_hiring_probability(signals)
    notice, notice_expl = _score_notice_period(signals)
    risk, risk_expl = _score_behavioral_risk(signals, ref_today)

    # --- Weighted aggregation ---
    weighted_sum = (
        _BEHAVIOR_WEIGHTS["availability"]          * availability
        + _BEHAVIOR_WEIGHTS["activity"]              * activity
        + _BEHAVIOR_WEIGHTS["recruiter_engagement"]  * engagement
        + _BEHAVIOR_WEIGHTS["interview_reliability"] * interview
        + _BEHAVIOR_WEIGHTS["hiring_probability"]    * hiring
        + _BEHAVIOR_WEIGHTS["notice_period"]         * notice
    )

    # --- Risk penalty ---
    final = weighted_sum * (1.0 - _RISK_PENALTY_FRACTION * risk)
    final = round(max(0.0, min(final, 1.0)), 4)

    # --- Explanation ---
    explanation = _build_explanation(
        avail_expl, act_expl, eng_expl, int_expl,
        hire_expl, notice_expl, risk_expl, final, signals,
    )

    return BehaviorScoreResult(
        availability_score=round(availability, 4),
        activity_score=round(activity, 4),
        recruiter_engagement_score=round(engagement, 4),
        interview_reliability_score=round(interview, 4),
        hiring_probability_score=round(hiring, 4),
        notice_period_score=round(notice, 4),
        behavioral_risk_score=round(risk, 4),
        final_behavior_score=final,
        explanation=explanation,
    )
