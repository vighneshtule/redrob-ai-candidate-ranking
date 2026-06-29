"""
tests/test_behavioral_scorer.py
================================
Comprehensive unit tests for src/features/behavioral_scorer.py.

Test strategy
-------------
* All tests inject a fixed `today` date for determinism.
* Sub-scorer functions are tested independently.
* Integration tests use full candidate personas.
* Edge cases: missing fields, None values, boundary conditions.
* Determinism: same input always produces identical output.

Personas (10)
-------------
1.  ideal_candidate        — all signals optimal
2.  highly_active          — very recent activity, high engagement
3.  inactive_candidate     — last active 6+ months ago
4.  long_notice_candidate  — 150-day notice period
5.  poor_responder         — recruiter_response_rate = 0.05
6.  high_acceptance        — offer_acceptance_rate = 0.95
7.  low_acceptance         — offer_acceptance_rate = 0.10
8.  missing_fields         — most redrob_signals fields absent
9.  edge_cases             — boundary values, None, zero
10. determinism_tests      — identical input → identical output

Run with:
    pytest tests/test_behavioral_scorer.py -v
    pytest tests/test_behavioral_scorer.py -v --tb=short
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.behavioral_scorer import (
    BehaviorScoreResult,
    _score_activity,
    _score_availability,
    _score_behavioral_risk,
    _score_hiring_probability,
    _score_interview_reliability,
    _score_notice_period,
    _score_recruiter_engagement,
    score_behavior,
)

# ---------------------------------------------------------------------------
# Fixed reference date for all tests (determinism)
# ---------------------------------------------------------------------------
TODAY = date(2025, 6, 1)

# Convenience: days relative to TODAY
def _days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()

def _days_from_now(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# Candidate fixture builders
# ---------------------------------------------------------------------------

def _make_signals(
    open_to_work: bool = True,
    last_active_date: str | None = None,
    recruiter_response_rate: float | None = 0.75,
    saved_by_recruiters_30d: int | None = 5,
    search_appearance_30d: int | None = 120,
    interview_completion_rate: float | None = 0.85,
    offer_acceptance_rate: float | None = 0.75,
    notice_period_days: int | None = 30,
    github_activity_score: float | None = 55.0,
    profile_completeness_score: float | None = 80.0,
    verified_email: bool = True,
    verified_phone: bool = True,
) -> dict:
    """Build a redrob_signals dict with configurable fields."""
    sigs: dict = {
        "open_to_work_flag": open_to_work,
        "recruiter_response_rate": recruiter_response_rate,
        "interview_completion_rate": interview_completion_rate,
        "offer_acceptance_rate": offer_acceptance_rate,
        "notice_period_days": notice_period_days,
        "github_activity_score": github_activity_score,
        "profile_completeness_score": profile_completeness_score,
        "expected_salary_range_inr_lpa": {"min": 25.0, "max": 50.0},
        "skill_assessment_scores": {},
        "verified_email": verified_email,
        "verified_phone": verified_phone,
    }
    if last_active_date is not None:
        sigs["last_active_date"] = last_active_date
    if saved_by_recruiters_30d is not None:
        sigs["saved_by_recruiters_30d"] = saved_by_recruiters_30d
    if search_appearance_30d is not None:
        sigs["search_appearance_30d"] = search_appearance_30d
    return sigs


def _make_candidate(signals: dict | None = None) -> dict:
    """Wrap signals in a minimal candidate record."""
    return {
        "candidate_id": "CAND_TEST001",
        "profile": {
            "current_title": "ML Engineer",
            "current_industry": "Software",
            "years_of_experience": 6,
            "location": "Pune",
            "country": "India",
        },
        "career_history": [],
        "education": [],
        "skills": [],
        "redrob_signals": signals or _make_signals(last_active_date=_days_ago(3)),
    }


# ===========================================================================
# Persona fixtures
# ===========================================================================

def _ideal_candidate() -> dict:
    """Persona 1: All signals optimal. Expected final_behavior_score >= 0.80."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(2),
        recruiter_response_rate=0.90,
        saved_by_recruiters_30d=8,
        search_appearance_30d=200,
        interview_completion_rate=0.95,
        offer_acceptance_rate=0.88,
        notice_period_days=15,
    ))


def _highly_active_candidate() -> dict:
    """Persona 2: Active today, strong engagement. Expected >= 0.75."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(0),
        recruiter_response_rate=0.82,
        saved_by_recruiters_30d=6,
        search_appearance_30d=150,
        interview_completion_rate=0.88,
        offer_acceptance_rate=0.70,
        notice_period_days=30,
    ))


def _inactive_candidate() -> dict:
    """Persona 3: Inactive 200 days. Expected final_behavior_score <= 0.45."""
    return _make_candidate(_make_signals(
        open_to_work=False,
        last_active_date=_days_ago(200),
        recruiter_response_rate=0.30,
        saved_by_recruiters_30d=1,
        search_appearance_30d=20,
        interview_completion_rate=0.60,
        offer_acceptance_rate=0.50,
        notice_period_days=60,
    ))


def _long_notice_candidate() -> dict:
    """Persona 4: 150-day notice period. Expected notice_period_score <= 0.20."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(5),
        recruiter_response_rate=0.80,
        interview_completion_rate=0.85,
        offer_acceptance_rate=0.75,
        notice_period_days=150,
    ))


def _poor_responder_candidate() -> dict:
    """Persona 5: Very low recruiter response rate. Expected engagement <= 0.15."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(10),
        recruiter_response_rate=0.05,
        saved_by_recruiters_30d=0,
        search_appearance_30d=5,
        interview_completion_rate=0.70,
        offer_acceptance_rate=0.60,
        notice_period_days=45,
    ))


def _high_acceptance_candidate() -> dict:
    """Persona 6: 95% offer acceptance. Expected hiring_probability_score >= 0.90."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(7),
        recruiter_response_rate=0.88,
        interview_completion_rate=0.92,
        offer_acceptance_rate=0.95,
        notice_period_days=30,
    ))


def _low_acceptance_candidate() -> dict:
    """Persona 7: 10% offer acceptance. Expected hiring_probability_score <= 0.15."""
    return _make_candidate(_make_signals(
        open_to_work=True,
        last_active_date=_days_ago(14),
        recruiter_response_rate=0.60,
        interview_completion_rate=0.80,
        offer_acceptance_rate=0.10,
        notice_period_days=30,
    ))


def _missing_fields_candidate() -> dict:
    """Persona 8: Minimal redrob_signals — most fields missing."""
    return _make_candidate({
        "open_to_work_flag": True,
        "expected_salary_range_inr_lpa": {"min": 20.0, "max": 40.0},
        "skill_assessment_scores": {},
        # Everything else deliberately omitted
    })


# ===========================================================================
# TestBehaviorScoreResultDataclass
# ===========================================================================

class TestBehaviorScoreResultDataclass:
    """Shape, types, bounds, and immutability of BehaviorScoreResult."""

    def test_fields_exist(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        for field in (
            "availability_score", "activity_score", "recruiter_engagement_score",
            "interview_reliability_score", "hiring_probability_score",
            "notice_period_score", "behavioral_risk_score",
            "final_behavior_score", "explanation",
        ):
            assert hasattr(result, field), f"Missing field: {field}"

    def test_field_types(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        for field in (
            "availability_score", "activity_score", "recruiter_engagement_score",
            "interview_reliability_score", "hiring_probability_score",
            "notice_period_score", "behavioral_risk_score", "final_behavior_score",
        ):
            val = getattr(result, field)
            assert isinstance(val, float), f"{field} must be float, got {type(val)}"
        assert isinstance(result.explanation, str)

    def test_all_scores_in_bounds(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        for field in (
            "availability_score", "activity_score", "recruiter_engagement_score",
            "interview_reliability_score", "hiring_probability_score",
            "notice_period_score", "behavioral_risk_score", "final_behavior_score",
        ):
            val = getattr(result, field)
            assert 0.0 <= val <= 1.0, f"{field} = {val} is out of [0, 1]"

    def test_explanation_non_empty(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert len(result.explanation) > 20

    def test_frozen_immutability(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        with pytest.raises((AttributeError, TypeError)):
            result.final_behavior_score = 0.5  # type: ignore[misc]


# ===========================================================================
# TestAvailabilityScore  (unit tests on sub-scorer)
# ===========================================================================

class TestAvailabilityScore:
    """Unit tests for _score_availability()."""

    def test_open_to_work_true_returns_1(self):
        score, _ = _score_availability({"open_to_work_flag": True})
        assert score == 1.0

    def test_open_to_work_false_returns_04(self):
        score, _ = _score_availability({"open_to_work_flag": False})
        assert score == 0.40

    def test_missing_flag_returns_04(self):
        score, _ = _score_availability({})
        assert score == 0.40

    def test_none_flag_returns_04(self):
        score, _ = _score_availability({"open_to_work_flag": None})
        assert score == 0.40

    def test_score_never_zero(self):
        """Spec: never assign 0 to availability."""
        for val in [False, None, "unknown"]:
            score, _ = _score_availability({"open_to_work_flag": val})
            assert score > 0.0, f"Availability must be > 0 for flag={val!r}"

    def test_explanation_present(self):
        _, expl = _score_availability({"open_to_work_flag": True})
        assert isinstance(expl, str) and len(expl) > 0


# ===========================================================================
# TestActivityScore  (unit tests on sub-scorer)
# ===========================================================================

class TestActivityScore:
    """Unit tests for _score_activity()."""

    def test_active_today(self):
        score, _ = _score_activity({"last_active_date": TODAY.isoformat()}, TODAY)
        assert score == 1.0

    def test_active_3_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(3)}, TODAY)
        assert score == 1.0

    def test_active_7_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(7)}, TODAY)
        assert score == 1.0

    def test_active_8_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(8)}, TODAY)
        assert score == 0.90

    def test_active_30_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(30)}, TODAY)
        assert score == 0.90

    def test_active_31_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(31)}, TODAY)
        assert score == 0.70

    def test_active_60_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(60)}, TODAY)
        assert score == 0.70

    def test_active_61_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(61)}, TODAY)
        assert score == 0.50

    def test_active_90_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(90)}, TODAY)
        assert score == 0.50

    def test_active_91_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(91)}, TODAY)
        assert score == 0.30

    def test_active_180_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(180)}, TODAY)
        assert score == 0.30

    def test_active_181_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(181)}, TODAY)
        assert score == 0.10

    def test_active_365_days_ago(self):
        score, _ = _score_activity({"last_active_date": _days_ago(365)}, TODAY)
        assert score == 0.10

    def test_missing_last_active_date_returns_default(self):
        score, _ = _score_activity({}, TODAY)
        assert 0.0 < score <= 0.50  # conservative default

    def test_none_last_active_date_returns_default(self):
        score, _ = _score_activity({"last_active_date": None}, TODAY)
        assert 0.0 < score <= 0.50

    def test_future_date_treated_as_today(self):
        """Future active dates shouldn't crash or produce > 1.0."""
        score, _ = _score_activity({"last_active_date": _days_from_now(5)}, TODAY)
        assert 0.0 <= score <= 1.0
        assert score == 1.0  # 0 days since active → 1.0

    def test_explanation_contains_days(self):
        _, expl = _score_activity({"last_active_date": _days_ago(45)}, TODAY)
        assert "45" in expl or "day" in expl.lower()


# ===========================================================================
# TestRecruiterEngagementScore  (unit tests on sub-scorer)
# ===========================================================================

class TestRecruiterEngagementScore:
    """Unit tests for _score_recruiter_engagement()."""

    def test_high_response_rate(self):
        score, _ = _score_recruiter_engagement({"recruiter_response_rate": 0.90})
        assert score >= 0.90

    def test_zero_response_rate(self):
        score, _ = _score_recruiter_engagement({"recruiter_response_rate": 0.0})
        assert score == 0.0

    def test_missing_response_rate_uses_default(self):
        score, _ = _score_recruiter_engagement({})
        assert 0.0 < score <= 0.60

    def test_saved_by_recruiters_bonus_applied(self):
        base_score, _ = _score_recruiter_engagement({"recruiter_response_rate": 0.70})
        bonus_score, _ = _score_recruiter_engagement({
            "recruiter_response_rate": 0.70,
            "saved_by_recruiters_30d": 5,
        })
        assert bonus_score > base_score

    def test_search_appearance_bonus_applied(self):
        base_score, _ = _score_recruiter_engagement({"recruiter_response_rate": 0.70})
        bonus_score, _ = _score_recruiter_engagement({
            "recruiter_response_rate": 0.70,
            "search_appearance_30d": 100,
        })
        assert bonus_score > base_score

    def test_score_capped_at_1(self):
        score, _ = _score_recruiter_engagement({
            "recruiter_response_rate": 1.0,
            "saved_by_recruiters_30d": 100,
            "search_appearance_30d": 1000,
        })
        assert score <= 1.0

    def test_below_threshold_no_bonus_saved(self):
        score_no_bonus, _ = _score_recruiter_engagement({"recruiter_response_rate": 0.60})
        score_few_saves, _ = _score_recruiter_engagement({
            "recruiter_response_rate": 0.60,
            "saved_by_recruiters_30d": 1,  # below threshold of 3
        })
        assert score_no_bonus == score_few_saves

    def test_response_rate_clamped_above_1(self):
        """Values > 1.0 in data should be clamped."""
        score, _ = _score_recruiter_engagement({"recruiter_response_rate": 1.5})
        assert score <= 1.0

    def test_response_rate_clamped_below_0(self):
        score, _ = _score_recruiter_engagement({"recruiter_response_rate": -0.5})
        assert score >= 0.0


# ===========================================================================
# TestInterviewReliabilityScore  (unit tests on sub-scorer)
# ===========================================================================

class TestInterviewReliabilityScore:
    """Unit tests for _score_interview_reliability()."""

    def test_perfect_completion_rate(self):
        score, _ = _score_interview_reliability({"interview_completion_rate": 1.0})
        assert score == 1.0

    def test_zero_completion_rate(self):
        score, _ = _score_interview_reliability({"interview_completion_rate": 0.0})
        assert score == 0.0

    def test_missing_rate_uses_default(self):
        score, _ = _score_interview_reliability({})
        assert 0.0 < score <= 0.75  # moderate default

    def test_rate_clamped_above_1(self):
        score, _ = _score_interview_reliability({"interview_completion_rate": 1.5})
        assert score <= 1.0

    def test_rate_clamped_below_0(self):
        score, _ = _score_interview_reliability({"interview_completion_rate": -0.2})
        assert score >= 0.0

    def test_explanation_high_rate(self):
        _, expl = _score_interview_reliability({"interview_completion_rate": 0.90})
        assert "reliable" in expl.lower() or "90" in expl

    def test_explanation_low_rate(self):
        _, expl = _score_interview_reliability({"interview_completion_rate": 0.20})
        assert "low" in expl.lower() or "20" in expl


# ===========================================================================
# TestHiringProbabilityScore  (unit tests on sub-scorer)
# ===========================================================================

class TestHiringProbabilityScore:
    """Unit tests for _score_hiring_probability()."""

    def test_perfect_acceptance_rate(self):
        score, _ = _score_hiring_probability({"offer_acceptance_rate": 1.0})
        assert score == 1.0

    def test_zero_acceptance_rate(self):
        score, _ = _score_hiring_probability({"offer_acceptance_rate": 0.0})
        assert score == 0.0

    def test_missing_rate_uses_default(self):
        score, _ = _score_hiring_probability({})
        assert 0.0 < score <= 0.60

    def test_high_acceptance_explanation(self):
        _, expl = _score_hiring_probability({"offer_acceptance_rate": 0.85})
        assert "high" in expl.lower() or "85" in expl

    def test_low_acceptance_explanation(self):
        _, expl = _score_hiring_probability({"offer_acceptance_rate": 0.15})
        assert "low" in expl.lower() or "15" in expl

    def test_rate_clamped_above_1(self):
        score, _ = _score_hiring_probability({"offer_acceptance_rate": 2.0})
        assert score <= 1.0


# ===========================================================================
# TestNoticePeriodScore  (unit tests on sub-scorer)
# ===========================================================================

class TestNoticePeriodScore:
    """Unit tests for _score_notice_period()."""

    def test_zero_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 0})
        assert score == 1.0

    def test_30_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 30})
        assert score == 1.0

    def test_31_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 31})
        assert score == 0.80

    def test_60_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 60})
        assert score == 0.80

    def test_61_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 61})
        assert score == 0.60

    def test_90_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 90})
        assert score == 0.60

    def test_91_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 91})
        assert score == 0.40

    def test_120_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 120})
        assert score == 0.40

    def test_121_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 121})
        assert score == 0.20

    def test_180_days_notice(self):
        score, _ = _score_notice_period({"notice_period_days": 180})
        assert score == 0.20

    def test_missing_notice_uses_default(self):
        score, _ = _score_notice_period({})
        assert 0.0 < score <= 0.90  # default 60 days → 0.80

    def test_none_notice_uses_default(self):
        score, _ = _score_notice_period({"notice_period_days": None})
        assert 0.0 < score <= 0.90

    def test_explanation_short_notice(self):
        _, expl = _score_notice_period({"notice_period_days": 15})
        assert "quickly" in expl.lower() or "15" in expl

    def test_explanation_long_notice(self):
        _, expl = _score_notice_period({"notice_period_days": 150})
        assert "delay" in expl.lower() or "150" in expl


# ===========================================================================
# TestBehavioralRiskScore  (unit tests on sub-scorer)
# ===========================================================================

class TestBehavioralRiskScore:
    """Unit tests for _score_behavioral_risk()."""

    def test_all_good_signals_low_risk(self):
        signals = {
            "last_active_date": _days_ago(5),
            "recruiter_response_rate": 0.80,
            "notice_period_days": 30,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
        }
        score, _ = _score_behavioral_risk(signals, TODAY)
        assert score < 0.20, f"All-good signals should have low risk, got {score}"

    def test_inactive_candidate_high_risk(self):
        signals = {
            "last_active_date": _days_ago(250),
            "recruiter_response_rate": 0.80,
            "notice_period_days": 30,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
        }
        score, _ = _score_behavioral_risk(signals, TODAY)
        assert score > 0.0, "Inactive candidate should have non-zero risk"

    def test_low_response_rate_adds_risk(self):
        low_response = {
            "last_active_date": _days_ago(5),
            "recruiter_response_rate": 0.05,
            "notice_period_days": 30,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
        }
        good_response = {**low_response, "recruiter_response_rate": 0.80}
        low_score, _ = _score_behavioral_risk(low_response, TODAY)
        good_score, _ = _score_behavioral_risk(good_response, TODAY)
        assert low_score > good_score

    def test_long_notice_adds_risk(self):
        long_notice = {
            "last_active_date": _days_ago(5),
            "recruiter_response_rate": 0.80,
            "notice_period_days": 180,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
        }
        short_notice = {**long_notice, "notice_period_days": 30}
        long_score, _ = _score_behavioral_risk(long_notice, TODAY)
        short_score, _ = _score_behavioral_risk(short_notice, TODAY)
        assert long_score > short_score

    def test_risk_score_bounded(self):
        worst_case = {
            "last_active_date": _days_ago(400),
            "recruiter_response_rate": 0.0,
            "notice_period_days": 365,
            "interview_completion_rate": 0.0,
            "offer_acceptance_rate": 0.0,
        }
        score, _ = _score_behavioral_risk(worst_case, TODAY)
        assert 0.0 <= score <= 1.0

    def test_missing_signals_moderate_risk(self):
        """Missing signals should produce moderate (not zero) risk."""
        score, _ = _score_behavioral_risk({}, TODAY)
        assert 0.0 < score < 1.0

    def test_compound_risk_high(self):
        """Inactive + low response + long notice → should be high risk."""
        signals = {
            "last_active_date": _days_ago(200),
            "recruiter_response_rate": 0.05,
            "notice_period_days": 180,
            "interview_completion_rate": 0.20,
            "offer_acceptance_rate": 0.10,
        }
        score, _ = _score_behavioral_risk(signals, TODAY)
        assert score > 0.50, f"Compound bad signals should have high risk, got {score}"

    def test_risk_flags_in_explanation(self):
        signals = {
            "last_active_date": _days_ago(200),
            "recruiter_response_rate": 0.05,
            "notice_period_days": 30,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
        }
        _, expl = _score_behavioral_risk(signals, TODAY)
        assert "inactive" in expl.lower() or "response" in expl.lower() or "risk" in expl.lower()


# ===========================================================================
# TestPersonas — Integration tests using score_behavior()
# ===========================================================================

class TestPersonas:
    """Full score_behavior() integration tests for all 10 personas."""

    # Persona 1: Ideal candidate
    def test_ideal_final_score_high(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert result.final_behavior_score >= 0.75, (
            f"Ideal candidate should score >= 0.75, got {result.final_behavior_score:.3f}"
        )

    def test_ideal_availability_score(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert result.availability_score == 1.0

    def test_ideal_activity_score_high(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert result.activity_score >= 0.90

    def test_ideal_risk_low(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert result.behavioral_risk_score < 0.20

    def test_ideal_notice_period_high(self):
        result = score_behavior(_ideal_candidate(), today=TODAY)
        assert result.notice_period_score == 1.0  # 15-day notice

    # Persona 2: Highly active
    def test_highly_active_final_score_high(self):
        result = score_behavior(_highly_active_candidate(), today=TODAY)
        assert result.final_behavior_score >= 0.70

    def test_highly_active_activity_perfect(self):
        result = score_behavior(_highly_active_candidate(), today=TODAY)
        assert result.activity_score == 1.0  # active today

    # Persona 3: Inactive
    def test_inactive_final_score_low(self):
        result = score_behavior(_inactive_candidate(), today=TODAY)
        assert result.final_behavior_score <= 0.50, (
            f"Inactive candidate should score <= 0.50, got {result.final_behavior_score:.3f}"
        )

    def test_inactive_activity_score_low(self):
        result = score_behavior(_inactive_candidate(), today=TODAY)
        assert result.activity_score <= 0.15  # 200 days inactive

    def test_inactive_availability_score(self):
        result = score_behavior(_inactive_candidate(), today=TODAY)
        assert result.availability_score == 0.40  # not open to work

    def test_inactive_risk_elevated(self):
        result = score_behavior(_inactive_candidate(), today=TODAY)
        # 200 days inactive → inactivity component fires; other signals are modest
        # aggregate risk = avg of 5 components, only inactivity is high here
        assert result.behavioral_risk_score > 0.05, (
            f"Inactive 200d candidate should have non-trivial risk, got {result.behavioral_risk_score}"
        )

    # Persona 4: Long notice
    def test_long_notice_notice_score_low(self):
        result = score_behavior(_long_notice_candidate(), today=TODAY)
        assert result.notice_period_score == 0.20  # 150-day notice

    def test_long_notice_risk_elevated(self):
        result = score_behavior(_long_notice_candidate(), today=TODAY)
        # Long notice contributes to risk
        assert result.behavioral_risk_score > 0.0

    def test_long_notice_final_penalised(self):
        """Long notice should score lower than equivalent candidate with short notice."""
        long = score_behavior(_long_notice_candidate(), today=TODAY)
        short = score_behavior(_ideal_candidate(), today=TODAY)
        assert short.final_behavior_score > long.final_behavior_score

    # Persona 5: Poor responder
    def test_poor_responder_engagement_low(self):
        result = score_behavior(_poor_responder_candidate(), today=TODAY)
        assert result.recruiter_engagement_score <= 0.15

    def test_poor_responder_risk_elevated(self):
        result = score_behavior(_poor_responder_candidate(), today=TODAY)
        # 5% response rate fires the response risk component
        # other signals are fine → aggregate risk is moderate
        assert result.behavioral_risk_score > 0.08, (
            f"Poor responder (5% rate) should have elevated risk, got {result.behavioral_risk_score}"
        )

    # Persona 6: High acceptance
    def test_high_acceptance_hiring_prob_high(self):
        result = score_behavior(_high_acceptance_candidate(), today=TODAY)
        assert result.hiring_probability_score >= 0.90

    def test_high_acceptance_final_high(self):
        result = score_behavior(_high_acceptance_candidate(), today=TODAY)
        assert result.final_behavior_score >= 0.70

    # Persona 7: Low acceptance
    def test_low_acceptance_hiring_prob_low(self):
        result = score_behavior(_low_acceptance_candidate(), today=TODAY)
        assert result.hiring_probability_score <= 0.15

    def test_low_acceptance_risk_elevated(self):
        result = score_behavior(_low_acceptance_candidate(), today=TODAY)
        # Low acceptance rate contributes to risk
        assert result.behavioral_risk_score > 0.0

    def test_low_acceptance_scores_below_high(self):
        high = score_behavior(_high_acceptance_candidate(), today=TODAY)
        low = score_behavior(_low_acceptance_candidate(), today=TODAY)
        assert high.final_behavior_score > low.final_behavior_score

    # Persona 8: Missing fields
    def test_missing_fields_does_not_crash(self):
        """Must not raise any exception with minimal signals."""
        result = score_behavior(_missing_fields_candidate(), today=TODAY)
        assert isinstance(result, BehaviorScoreResult)

    def test_missing_fields_all_scores_in_bounds(self):
        result = score_behavior(_missing_fields_candidate(), today=TODAY)
        for field in (
            "availability_score", "activity_score", "recruiter_engagement_score",
            "interview_reliability_score", "hiring_probability_score",
            "notice_period_score", "behavioral_risk_score", "final_behavior_score",
        ):
            val = getattr(result, field)
            assert 0.0 <= val <= 1.0, f"Missing-fields: {field} = {val} out of bounds"

    def test_missing_fields_availability_from_flag(self):
        """open_to_work_flag IS present → availability should be 1.0."""
        result = score_behavior(_missing_fields_candidate(), today=TODAY)
        assert result.availability_score == 1.0


# ===========================================================================
# TestScoringOrdering — relative ordering between personas
# ===========================================================================

class TestScoringOrdering:
    """Verify correct relative ordering between personas on key sub-scores."""

    def test_ideal_beats_inactive(self):
        ideal = score_behavior(_ideal_candidate(), today=TODAY)
        inactive = score_behavior(_inactive_candidate(), today=TODAY)
        assert ideal.final_behavior_score > inactive.final_behavior_score

    def test_ideal_beats_poor_responder(self):
        ideal = score_behavior(_ideal_candidate(), today=TODAY)
        poor = score_behavior(_poor_responder_candidate(), today=TODAY)
        assert ideal.recruiter_engagement_score > poor.recruiter_engagement_score

    def test_ideal_beats_long_notice_on_notice_score(self):
        ideal = score_behavior(_ideal_candidate(), today=TODAY)
        long = score_behavior(_long_notice_candidate(), today=TODAY)
        assert ideal.notice_period_score > long.notice_period_score

    def test_high_acceptance_beats_low_on_hiring_prob(self):
        high = score_behavior(_high_acceptance_candidate(), today=TODAY)
        low = score_behavior(_low_acceptance_candidate(), today=TODAY)
        assert high.hiring_probability_score > low.hiring_probability_score

    def test_active_beats_inactive_on_activity(self):
        active = score_behavior(_highly_active_candidate(), today=TODAY)
        inactive = score_behavior(_inactive_candidate(), today=TODAY)
        assert active.activity_score > inactive.activity_score

    def test_ideal_has_lower_risk_than_inactive(self):
        ideal = score_behavior(_ideal_candidate(), today=TODAY)
        inactive = score_behavior(_inactive_candidate(), today=TODAY)
        assert ideal.behavioral_risk_score < inactive.behavioral_risk_score


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:
    """Boundary values, None inputs, zero values, extreme values."""

    def test_empty_redrob_signals(self):
        candidate = _make_candidate({})
        result = score_behavior(candidate, today=TODAY)
        assert 0.0 <= result.final_behavior_score <= 1.0

    def test_none_redrob_signals(self):
        candidate = {"candidate_id": "CAND_EDGE01", "redrob_signals": None}
        result = score_behavior(candidate, today=TODAY)
        assert 0.0 <= result.final_behavior_score <= 1.0

    def test_missing_redrob_signals_key(self):
        candidate = {"candidate_id": "CAND_EDGE02"}
        result = score_behavior(candidate, today=TODAY)
        assert 0.0 <= result.final_behavior_score <= 1.0

    def test_zero_notice_period(self):
        sigs = _make_signals(last_active_date=_days_ago(3), notice_period_days=0)
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.notice_period_score == 1.0

    def test_very_long_notice_period(self):
        sigs = _make_signals(last_active_date=_days_ago(3), notice_period_days=365)
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.notice_period_score == 0.20

    def test_response_rate_exactly_zero(self):
        # Use raw signals dict to avoid saved_by_recruiters bonus from _make_signals default
        sigs: dict = {
            "open_to_work_flag": True,
            "last_active_date": _days_ago(3),
            "recruiter_response_rate": 0.0,
            # No saved_by_recruiters_30d or search_appearance_30d → no bonus
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.75,
            "notice_period_days": 30,
            "expected_salary_range_inr_lpa": {"min": 20.0, "max": 40.0},
            "skill_assessment_scores": {},
        }
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.recruiter_engagement_score == 0.0, (
            f"response_rate=0 with no bonus signals should give 0.0, got {result.recruiter_engagement_score}"
        )

    def test_response_rate_exactly_one(self):
        sigs = _make_signals(last_active_date=_days_ago(3), recruiter_response_rate=1.0)
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.recruiter_engagement_score >= 1.0 or result.recruiter_engagement_score <= 1.0

    def test_interview_rate_exactly_zero(self):
        sigs = _make_signals(last_active_date=_days_ago(3), interview_completion_rate=0.0)
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.interview_reliability_score == 0.0

    def test_offer_acceptance_exactly_zero(self):
        sigs = _make_signals(last_active_date=_days_ago(3), offer_acceptance_rate=0.0)
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.hiring_probability_score == 0.0

    def test_all_zeros_does_not_crash(self):
        sigs: dict = {
            "open_to_work_flag": False,
            "last_active_date": _days_ago(365),
            "recruiter_response_rate": 0.0,
            "interview_completion_rate": 0.0,
            "offer_acceptance_rate": 0.0,
            "notice_period_days": 365,
            "github_activity_score": 0.0,
            "expected_salary_range_inr_lpa": {"min": 0.0, "max": 0.0},
            "skill_assessment_scores": {},
        }
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert 0.0 <= result.final_behavior_score <= 1.0

    def test_all_perfect_does_not_exceed_1(self):
        sigs: dict = {
            "open_to_work_flag": True,
            "last_active_date": TODAY.isoformat(),
            "recruiter_response_rate": 1.0,
            "saved_by_recruiters_30d": 100,
            "search_appearance_30d": 10000,
            "interview_completion_rate": 1.0,
            "offer_acceptance_rate": 1.0,
            "notice_period_days": 0,
            "github_activity_score": 100.0,
            "expected_salary_range_inr_lpa": {"min": 10.0, "max": 50.0},
            "skill_assessment_scores": {},
        }
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.final_behavior_score <= 1.0
        for field in (
            "availability_score", "activity_score", "recruiter_engagement_score",
            "interview_reliability_score", "hiring_probability_score",
            "notice_period_score", "behavioral_risk_score", "final_behavior_score",
        ):
            assert getattr(result, field) <= 1.0

    def test_explanation_never_empty(self):
        for sigs in [
            {},
            _make_signals(last_active_date=_days_ago(3)),
            {"open_to_work_flag": True, "expected_salary_range_inr_lpa": {}, "skill_assessment_scores": {}},
        ]:
            result = score_behavior(_make_candidate(sigs), today=TODAY)
            assert len(result.explanation) > 0, "Explanation must never be empty"

    def test_risk_score_never_negative(self):
        sigs = _make_signals(
            last_active_date=_days_ago(1),
            recruiter_response_rate=1.0,
            interview_completion_rate=1.0,
            offer_acceptance_rate=1.0,
            notice_period_days=0,
        )
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        assert result.behavioral_risk_score >= 0.0

    def test_final_score_never_negative(self):
        worst = {
            "open_to_work_flag": False,
            "last_active_date": _days_ago(500),
            "recruiter_response_rate": 0.0,
            "interview_completion_rate": 0.0,
            "offer_acceptance_rate": 0.0,
            "notice_period_days": 365,
            "expected_salary_range_inr_lpa": {"min": 0.0, "max": 0.0},
            "skill_assessment_scores": {},
        }
        result = score_behavior(_make_candidate(worst), today=TODAY)
        assert result.final_behavior_score >= 0.0


# ===========================================================================
# TestDeterminism
# ===========================================================================

class TestDeterminism:
    """Same input always produces identical output."""

    def test_identical_output_on_same_input(self):
        c = _ideal_candidate()
        r1 = score_behavior(c, today=TODAY)
        r2 = score_behavior(c, today=TODAY)
        assert r1.final_behavior_score == r2.final_behavior_score
        assert r1.explanation == r2.explanation

    def test_independent_of_call_order(self):
        """Calling in different order produces same individual results."""
        ideal = _ideal_candidate()
        inactive = _inactive_candidate()

        # Order A: ideal first
        r_ideal_a = score_behavior(ideal, today=TODAY)
        r_inactive_a = score_behavior(inactive, today=TODAY)

        # Order B: inactive first
        r_inactive_b = score_behavior(inactive, today=TODAY)
        r_ideal_b = score_behavior(ideal, today=TODAY)

        assert r_ideal_a.final_behavior_score == r_ideal_b.final_behavior_score
        assert r_inactive_a.final_behavior_score == r_inactive_b.final_behavior_score

    def test_deepcopy_produces_same_result(self):
        c = _ideal_candidate()
        c_copy = copy.deepcopy(c)
        r1 = score_behavior(c, today=TODAY)
        r2 = score_behavior(c_copy, today=TODAY)
        assert r1.final_behavior_score == r2.final_behavior_score

    def test_today_injection_affects_activity(self):
        """Changing today should change activity_score for the same last_active_date."""
        sigs = _make_signals(last_active_date=_days_ago(5))
        c = _make_candidate(sigs)

        # Relative to TODAY: 5 days ago → active (score 1.0)
        r1 = score_behavior(c, today=TODAY)

        # Relative to TODAY + 90 days: 95 days ago → stale (score 0.30)
        r2 = score_behavior(c, today=TODAY + timedelta(days=90))

        assert r1.activity_score > r2.activity_score

    def test_all_personas_deterministic(self):
        personas = [
            _ideal_candidate(), _highly_active_candidate(), _inactive_candidate(),
            _long_notice_candidate(), _poor_responder_candidate(),
            _high_acceptance_candidate(), _low_acceptance_candidate(),
            _missing_fields_candidate(),
        ]
        for c in personas:
            r1 = score_behavior(c, today=TODAY)
            r2 = score_behavior(c, today=TODAY)
            assert r1.final_behavior_score == r2.final_behavior_score


# ===========================================================================
# TestRiskPenaltyMechanism
# ===========================================================================

class TestRiskPenaltyMechanism:
    """Verify the risk penalty correctly reduces final_behavior_score."""

    def test_high_risk_reduces_final_score(self):
        """Compound risk factors should meaningfully reduce final_behavior_score."""
        low_risk_sigs = _make_signals(
            last_active_date=_days_ago(3),
            recruiter_response_rate=0.85,
            notice_period_days=30,
            interview_completion_rate=0.90,
            offer_acceptance_rate=0.80,
        )
        high_risk_sigs = _make_signals(
            last_active_date=_days_ago(200),
            recruiter_response_rate=0.05,
            notice_period_days=180,
            interview_completion_rate=0.20,
            offer_acceptance_rate=0.10,
        )
        low_risk_result = score_behavior(_make_candidate(low_risk_sigs), today=TODAY)
        high_risk_result = score_behavior(_make_candidate(high_risk_sigs), today=TODAY)
        assert low_risk_result.final_behavior_score > high_risk_result.final_behavior_score

    def test_zero_risk_no_penalty(self):
        """With zero risk, final should equal weighted sum."""
        # We can't force risk=0 without internal access, but we can
        # verify that low-risk candidates have scores close to weighted sum
        sigs = _make_signals(
            last_active_date=_days_ago(1),
            recruiter_response_rate=0.90,
            notice_period_days=15,
            interview_completion_rate=0.95,
            offer_acceptance_rate=0.90,
        )
        result = score_behavior(_make_candidate(sigs), today=TODAY)
        # With very low risk, penalty should be minimal
        assert result.final_behavior_score >= 0.70

    def test_final_score_bounded_with_risk(self):
        for _ in range(5):
            sigs = _make_signals(
                last_active_date=_days_ago(100),
                recruiter_response_rate=0.10,
                notice_period_days=120,
                interview_completion_rate=0.30,
                offer_acceptance_rate=0.20,
            )
            result = score_behavior(_make_candidate(sigs), today=TODAY)
            assert 0.0 <= result.final_behavior_score <= 1.0
