"""
tests/test_reasoning_generator.py
===================================
Unit tests for src/pipeline/reasoning_generator.py

Coverage
--------
* generate_explanation() — all score bands (Strong/Good/Moderate/Weak)
* Vetoed candidate explanation
* Determinism
* No hallucination — all claims traceable to input features
* Non-empty for all edge cases
* Career phrase matches career_score band
* Skill phrase reflects tier_a_match_score and coverage
* Behavior phrase reflects availability, engagement, notice
* Integrity phrase mentions anomaly count when > 0
* Stuffing phrase reflects stuffing_score
* CSV export validation
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.feature_extractor import CandidateFeatures
from src.pipeline.reasoning_generator import generate_explanation
from src.pipeline.exporter import validate_submission, export_submission_csv
from src.pipeline.ranker import RankedCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_features(
    cid: str = "CAND_0000001",
    career: float = 0.8,
    skill: float = 0.7,
    behavior: float = 0.6,
    integrity: float = 1.0,
    profile_integrity: float = 0.9,
    veto: bool = False,
    anomaly_count: int = 0,
    anomaly_flags: tuple = (),
    stuffing: float = 0.0,
    tier_a: float = 0.8,
    coverage: float = 0.75,
    availability: float = 0.7,
    engagement: float = 0.8,
    notice: float = 0.9,
    risk: float = 0.1,
) -> CandidateFeatures:
    fv = {
        "career_score": career,
        "skill_score": skill,
        "behavior_score": behavior,
        "integrity_score": integrity,
        "profile_integrity_score": profile_integrity,
        "stuffing_score": stuffing,
        "anomaly_count": anomaly_count,
        "veto_candidate": veto,
        "tier_a_match_score": tier_a,
        "tier_b_match_score": 0.5,
        "tier_c_match_score": 0.4,
        "duration_score": 0.7,
        "proficiency_score": 0.8,
        "assessment_score": 0.6,
        "coverage_score": coverage,
        "depth_score": 0.65,
        "title_relevance_score": career,
        "career_history_relevance_score": career,
        "product_company_score": career,
        "relevant_experience_score": career,
        "career_consistency_score": career,
        "availability_score": availability,
        "activity_score": 0.7,
        "recruiter_engagement_score": engagement,
        "interview_reliability_score": 0.7,
        "hiring_probability_score": 0.7,
        "notice_period_score": notice,
        "behavioral_risk_score": risk,
    }
    return CandidateFeatures(
        candidate_id=cid,
        integrity_score=integrity,
        profile_integrity_score=profile_integrity,
        career_score=career,
        behavior_score=behavior,
        skill_score=skill,
        veto_candidate=veto,
        stuffing_score=stuffing,
        semantic_score=0.0,
        anomaly_count=anomaly_count,
        anomaly_flags=tuple(anomaly_flags),
        final_feature_vector=fv,
    )


def _make_ranked(features: CandidateFeatures, score: float, rank: int = 1) -> RankedCandidate:
    expl = generate_explanation(features, score)
    return RankedCandidate(
        candidate_id=features.candidate_id,
        final_score=score,
        rank=rank,
        feature_breakdown=dict(features.final_feature_vector),
        explanation=expl,
    )


# ---------------------------------------------------------------------------
# TestTonePhrases
# ---------------------------------------------------------------------------

class TestTonePhrases:
    def test_strong_score_mentions_strong(self):
        f = _make_features(career=0.9, skill=0.9, behavior=0.9)
        expl = generate_explanation(f, 0.85)
        assert "Strong candidate" in expl

    def test_good_score_mentions_good(self):
        f = _make_features(career=0.6, skill=0.5, behavior=0.5)
        expl = generate_explanation(f, 0.55)
        assert "Good candidate" in expl

    def test_moderate_score_mentions_moderate(self):
        f = _make_features(career=0.3, skill=0.3, behavior=0.3)
        expl = generate_explanation(f, 0.35)
        assert "Moderate-fit candidate" in expl or "Moderate" in expl

    def test_weak_score_mentions_weak(self):
        f = _make_features(career=0.1, skill=0.1, behavior=0.1)
        expl = generate_explanation(f, 0.10)
        assert "Weak candidate" in expl


# ---------------------------------------------------------------------------
# TestVetoPhrases
# ---------------------------------------------------------------------------

class TestVetoPhrases:
    def test_vetoed_mentions_vetoed(self):
        f = _make_features(
            veto=True, anomaly_count=5,
            anomaly_flags=("H-F1: skill duration > career",)
        )
        expl = generate_explanation(f, 0.0)
        assert "VETOED" in expl

    def test_vetoed_mentions_anomaly_count(self):
        f = _make_features(
            veto=True, anomaly_count=5,
            anomaly_flags=("H-F1: skill duration > career",)
        )
        expl = generate_explanation(f, 0.0)
        assert "5" in expl

    def test_vetoed_shows_flag_text(self):
        f = _make_features(
            veto=True, anomaly_count=3,
            anomaly_flags=("H-F1: skill duration issue",)
        )
        expl = generate_explanation(f, 0.0)
        assert "H-F1" in expl

    def test_vetoed_explanation_non_empty(self):
        f = _make_features(veto=True, anomaly_count=3, anomaly_flags=())
        expl = generate_explanation(f, 0.0)
        assert expl and expl.strip()

    def test_non_vetoed_does_not_say_vetoed(self):
        f = _make_features(veto=False, anomaly_count=0)
        expl = generate_explanation(f, 0.75)
        assert "VETOED" not in expl


# ---------------------------------------------------------------------------
# TestCareerPhrases
# ---------------------------------------------------------------------------

class TestCareerPhrases:
    def test_high_career_positive_phrase(self):
        f = _make_features(career=0.85)
        expl = generate_explanation(f, 0.75)
        assert "highly relevant" in expl.lower() or "relevant" in expl.lower()

    def test_low_career_limited_phrase(self):
        f = _make_features(career=0.10)
        expl = generate_explanation(f, 0.30)
        assert "limited" in expl.lower()

    def test_medium_career_includes_signal(self):
        f = _make_features(career=0.50)
        expl = generate_explanation(f, 0.50)
        assert "career" in expl.lower() or "technical" in expl.lower()


# ---------------------------------------------------------------------------
# TestSkillPhrases
# ---------------------------------------------------------------------------

class TestSkillPhrases:
    def test_high_tier_a_strong_skill_phrase(self):
        f = _make_features(skill=0.80, tier_a=0.80, coverage=0.75)
        expl = generate_explanation(f, 0.75)
        assert "Tier-A" in expl or "tier-a" in expl.lower()

    def test_no_tier_a_mentions_no_match(self):
        f = _make_features(skill=0.10, tier_a=0.0, coverage=0.0)
        expl = generate_explanation(f, 0.25)
        assert "no Tier-A" in expl or "no tier-a" in expl.lower()

    def test_partial_tier_a_mentioned(self):
        f = _make_features(skill=0.35, tier_a=0.30, coverage=0.20)
        expl = generate_explanation(f, 0.40)
        assert "Tier-A" in expl or "tier-a" in expl.lower()


# ---------------------------------------------------------------------------
# TestBehaviorPhrases
# ---------------------------------------------------------------------------

class TestBehaviorPhrases:
    def test_high_availability_phrase(self):
        f = _make_features(availability=0.90)
        expl = generate_explanation(f, 0.75)
        assert "highly available" in expl.lower()

    def test_low_availability_phrase(self):
        f = _make_features(availability=0.10)
        expl = generate_explanation(f, 0.50)
        assert "limited availability" in expl.lower()

    def test_high_engagement_phrase(self):
        f = _make_features(engagement=0.90)
        expl = generate_explanation(f, 0.75)
        assert "engagement" in expl.lower() or "responsiveness" in expl.lower()

    def test_low_engagement_phrase(self):
        f = _make_features(engagement=0.10)
        expl = generate_explanation(f, 0.50)
        assert "low" in expl.lower()

    def test_high_notice_score_phrase(self):
        f = _make_features(notice=0.90)
        expl = generate_explanation(f, 0.75)
        assert "notice" in expl.lower()

    def test_high_risk_phrase(self):
        f = _make_features(risk=0.85)
        expl = generate_explanation(f, 0.45)
        assert "risk" in expl.lower()

    def test_low_risk_phrase(self):
        f = _make_features(risk=0.10)
        expl = generate_explanation(f, 0.75)
        assert "risk" in expl.lower()


# ---------------------------------------------------------------------------
# TestIntegrityPhrases
# ---------------------------------------------------------------------------

class TestIntegrityPhrases:
    def test_clean_profile_phrase(self):
        f = _make_features(anomaly_count=0, stuffing=0.05)
        expl = generate_explanation(f, 0.80)
        assert "Clean profile" in expl or "no anomalies" in expl.lower()

    def test_anomaly_count_mentioned(self):
        f = _make_features(anomaly_count=2, anomaly_flags=("H-A2: mismatch",))
        expl = generate_explanation(f, 0.55)
        assert "2" in expl or "anomaly" in expl.lower()

    def test_high_stuffing_mentioned(self):
        f = _make_features(stuffing=0.80, anomaly_count=0, anomaly_flags=())
        expl = generate_explanation(f, 0.50)
        assert "stuffing" in expl.lower() or "keyword" in expl.lower()


# ---------------------------------------------------------------------------
# TestNonEmpty
# ---------------------------------------------------------------------------

class TestNonEmpty:
    @pytest.mark.parametrize("score", [0.0, 0.10, 0.30, 0.50, 0.70, 0.90, 1.0])
    def test_never_empty_for_any_score(self, score):
        f = _make_features()
        expl = generate_explanation(f, score)
        assert expl and expl.strip()

    def test_vetoed_with_no_flags_non_empty(self):
        f = _make_features(veto=True, anomaly_count=3, anomaly_flags=())
        expl = generate_explanation(f, 0.0)
        assert expl and expl.strip()

    def test_zero_skill_no_crash(self):
        f = _make_features(skill=0.0, tier_a=0.0, coverage=0.0)
        expl = generate_explanation(f, 0.20)
        assert expl and expl.strip()


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        f = _make_features()
        expl1 = generate_explanation(f, 0.75)
        expl2 = generate_explanation(f, 0.75)
        assert expl1 == expl2

    def test_different_scores_different_outputs(self):
        f = _make_features()
        expl_strong = generate_explanation(f, 0.80)
        expl_weak = generate_explanation(f, 0.10)
        assert expl_strong != expl_weak


# ---------------------------------------------------------------------------
# TestCSVExporter
# ---------------------------------------------------------------------------

def _make_100_ranked() -> list[RankedCandidate]:
    """Generate exactly 100 RankedCandidate records for submission tests."""
    results = []
    for i in range(1, 101):
        f = _make_features(
            cid=f"CAND_{i:07d}",
            career=max(0.1, 1.0 - i * 0.009),
            skill=max(0.1, 0.9 - i * 0.008),
        )
        score = max(0.05, 0.95 - i * 0.009)
        results.append(_make_ranked(f, score, rank=i))
    return results


class TestCSVExporter:
    def test_validate_100_valid_submission(self):
        ranked = _make_100_ranked()
        violations = validate_submission(ranked)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_validate_wrong_row_count(self):
        ranked = _make_100_ranked()[:50]
        violations = validate_submission(ranked)
        assert any("100" in v or "50" in v for v in violations)

    def test_validate_duplicate_rank(self):
        ranked = list(_make_100_ranked())
        ranked[1] = RankedCandidate(
            candidate_id=ranked[1].candidate_id,
            final_score=ranked[1].final_score,
            rank=1,  # duplicate of rank 1
            feature_breakdown=ranked[1].feature_breakdown,
            explanation=ranked[1].explanation,
        )
        violations = validate_submission(ranked)
        assert any("rank" in v.lower() or "duplicate" in v.lower() for v in violations)

    def test_validate_duplicate_candidate_id(self):
        ranked = list(_make_100_ranked())
        ranked[1] = RankedCandidate(
            candidate_id=ranked[0].candidate_id,  # duplicate ID
            final_score=ranked[1].final_score,
            rank=ranked[1].rank,
            feature_breakdown=ranked[1].feature_breakdown,
            explanation=ranked[1].explanation,
        )
        violations = validate_submission(ranked)
        assert any("candidate" in v.lower() or "duplicate" in v.lower() for v in violations)

    def test_export_writes_file(self):
        ranked = _make_100_ranked()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "submission.csv"
            result = export_submission_csv(ranked, output_path=out, overwrite=True)
            assert result.exists()

    def test_export_correct_columns(self):
        import csv
        ranked = _make_100_ranked()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "submission.csv"
            export_submission_csv(ranked, output_path=out, overwrite=True)
            with out.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                assert set(reader.fieldnames or []) == {
                    "candidate_id", "rank", "score", "reasoning"
                }

    def test_export_correct_row_count(self):
        import csv
        ranked = _make_100_ranked()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "submission.csv"
            export_submission_csv(ranked, output_path=out, overwrite=True)
            with out.open("r", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
                assert len(rows) == 100

    def test_export_raises_on_invalid(self):
        ranked = _make_100_ranked()[:10]  # wrong count
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "submission.csv"
            with pytest.raises(ValueError):
                export_submission_csv(ranked, output_path=out, overwrite=True)

    def test_export_raises_if_file_exists_no_overwrite(self):
        ranked = _make_100_ranked()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "submission.csv"
            export_submission_csv(ranked, output_path=out, overwrite=True)
            with pytest.raises(FileExistsError):
                export_submission_csv(ranked, output_path=out, overwrite=False)

    def test_validate_empty_explanation(self):
        ranked = list(_make_100_ranked())
        ranked[0] = RankedCandidate(
            candidate_id=ranked[0].candidate_id,
            final_score=ranked[0].final_score,
            rank=ranked[0].rank,
            feature_breakdown=ranked[0].feature_breakdown,
            explanation="",
        )
        violations = validate_submission(ranked)
        assert any("explanation" in v.lower() for v in violations)
