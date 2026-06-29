"""
tests/test_career_scorer.py
============================
Unit tests for src/features/career_scorer.py

Test strategy
-------------
* Five candidate personas cover the full scoring spectrum.
* All tests inject a fixed `today` date for determinism.
* Sub-scorer functions are tested independently where possible.
* Edge cases (empty history, None dates, consulting-only) are verified.
* Score bounds (0-1) are asserted on every result.

Personas
--------
1. ml_engineer      — 7yr ML Engineer at product companies         → ≥ 0.75
2. data_scientist   — 5yr Data Scientist with some ML exposure      → ≥ 0.50
3. hr_manager       — HR career with AI keywords stuffed in skills  → ≤ 0.15
4. consulting_only  — All roles at TCS/Infosys                      → ≤ 0.40
5. product_company  — SaaS + Fintech ML roles                       → ≥ 0.65
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.features.career_scorer import (
    CareerScoreResult,
    _score_career_consistency,
    _score_career_history_relevance,
    _score_product_company,
    _score_relevant_experience,
    _score_title_relevance,
    load_taxonomies,
    score_career,
)
from src.utils.date_utils import (
    career_gap_months,
    months_between,
    parse_date,
    recency_decay,
    years_between,
)
from src.utils.text_utils import (
    fuzzy_match,
    keyword_relevance,
    normalize_skill,
    normalize_title,
    title_similarity,
)

# ---------------------------------------------------------------------------
# Fixed reference date for all tests (keeps scores deterministic)
# ---------------------------------------------------------------------------
TODAY = date(2025, 6, 1)

# ---------------------------------------------------------------------------
# Load taxonomies once for all tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def taxonomies() -> tuple[dict, dict]:
    """Load title and industry taxonomies from data/ directory."""
    title_tax, industry_tax = load_taxonomies()
    return title_tax, industry_tax


# ---------------------------------------------------------------------------
# Candidate fixture builders
# ---------------------------------------------------------------------------

def _ml_engineer_candidate() -> dict:
    """
    Persona 1: Ideal ML Engineer candidate.
    7 years total, roles at product companies, retrieval/ranking work throughout.
    Expected final_career_score >= 0.75
    """
    return {
        "candidate_id": "CAND_TEST001",
        "profile": {
            "name": "Aarav Sharma",
            "current_title": "Senior ML Engineer",
            "current_industry": "AI/ML",
            "years_of_experience": 7,
            "location": "Pune",
            "country": "India",
        },
        "career_history": [
            {
                "title": "Senior ML Engineer",
                "company": "Qdrant Technologies",
                "company_industry": "AI/ML",
                "start_date": "2022-01-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 41,
                "description": (
                    "Built dense retrieval and ranking systems using embeddings and FAISS. "
                    "Designed evaluation framework with NDCG, MRR for search ranking. "
                    "Deployed vector database at scale; handled embedding drift and index refresh. "
                    "Led re-ranking with cross-encoder models."
                ),
            },
            {
                "title": "ML Engineer",
                "company": "Swiggy",
                "company_industry": "Food Delivery",
                "start_date": "2019-06-01",
                "end_date": "2021-12-31",
                "is_current": False,
                "duration_months": 30,
                "description": (
                    "Developed recommendation systems using collaborative filtering and matrix factorization. "
                    "Built NLP pipelines for content understanding. "
                    "Used PyTorch and transformers for model training."
                ),
            },
            {
                "title": "Data Scientist",
                "company": "Razorpay",
                "company_industry": "Fintech",
                "start_date": "2017-07-01",
                "end_date": "2019-05-31",
                "is_current": False,
                "duration_months": 23,
                "description": (
                    "Applied machine learning to fraud detection and risk scoring. "
                    "Feature engineering and scikit-learn model development. "
                    "Experimented with XGBoost for gradient boosting ranking."
                ),
            },
        ],
        "skills": [
            {"name": "PyTorch", "proficiency": "expert", "duration_months": 60},
            {"name": "Elasticsearch", "proficiency": "advanced", "duration_months": 36},
            {"name": "FAISS", "proficiency": "advanced", "duration_months": 30},
            {"name": "Recommendation Systems", "proficiency": "advanced", "duration_months": 30},
            {"name": "NLP", "proficiency": "expert", "duration_months": 60},
        ],
        "education": [
            {"degree": "B.Tech", "field": "Computer Science", "start_year": 2013, "end_year": 2017},
        ],
        "redrob_signals": {
            "last_active_date": "2025-05-01",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.80,
            "notice_period_days": 30,
            "expected_salary_range_inr_lpa": {"min": 30, "max": 55},
            "skill_assessment_scores": {},
            "github_activity_score": 65,
            "interview_completion_rate": 0.85,
            "offer_acceptance_rate": 0.70,
        },
    }


def _data_scientist_candidate() -> dict:
    """
    Persona 2: Data Scientist with moderate ML exposure.
    5 years, mix of product and neutral companies.
    Expected final_career_score >= 0.50
    """
    return {
        "candidate_id": "CAND_TEST002",
        "profile": {
            "name": "Priya Mehta",
            "current_title": "Senior Data Scientist",
            "current_industry": "SaaS",
            "years_of_experience": 5,
            "location": "Bangalore",
            "country": "India",
        },
        "career_history": [
            {
                "title": "Senior Data Scientist",
                "company": "Freshworks",
                "company_industry": "SaaS",
                "start_date": "2022-03-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 39,
                "description": (
                    "Worked on machine learning models for customer churn prediction. "
                    "Built NLP text classification pipelines using transformers and BERT. "
                    "Experimented with embeddings for semantic search in support tickets. "
                    "Used scikit-learn and XGBoost for tabular predictions."
                ),
            },
            {
                "title": "Data Scientist",
                "company": "HDFC Bank",
                "company_industry": "Banking",
                "start_date": "2020-01-01",
                "end_date": "2022-02-28",
                "is_current": False,
                "duration_months": 26,
                "description": (
                    "Built statistical models for credit risk. "
                    "Feature engineering with pandas. "
                    "Some machine learning model evaluation using cross-validation."
                ),
            },
        ],
        "skills": [
            {"name": "Python", "proficiency": "expert", "duration_months": 60},
            {"name": "NLP", "proficiency": "advanced", "duration_months": 36},
            {"name": "Machine Learning", "proficiency": "advanced", "duration_months": 48},
            {"name": "BERT", "proficiency": "intermediate", "duration_months": 24},
        ],
        "education": [
            {"degree": "M.Tech", "field": "Data Science", "start_year": 2018, "end_year": 2020},
        ],
        "redrob_signals": {
            "last_active_date": "2025-04-15",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.60,
            "notice_period_days": 60,
            "expected_salary_range_inr_lpa": {"min": 20, "max": 40},
            "skill_assessment_scores": {},
            "github_activity_score": 35,
            "interview_completion_rate": 0.70,
            "offer_acceptance_rate": 0.60,
        },
    }


def _hr_manager_candidate() -> dict:
    """
    Persona 3: HR Manager / keyword stuffer.
    Entire career in HR, but lists AI/ML skills to game the system.
    Expected final_career_score <= 0.15
    """
    return {
        "candidate_id": "CAND_TEST003",
        "profile": {
            "name": "Sunita Rao",
            "current_title": "HR Manager",
            "current_industry": "IT Services",
            "years_of_experience": 8,
            "location": "Chennai",
            "country": "India",
        },
        "career_history": [
            {
                "title": "HR Manager",
                "company": "Infosys",
                "company_industry": "IT Services",
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 65,
                "description": (
                    "Managed recruitment and onboarding for engineering teams. "
                    "Handled payroll processing and employee engagement initiatives. "
                    "Conducted performance reviews and talent acquisition campaigns."
                ),
            },
            {
                "title": "Talent Acquisition Manager",
                "company": "TCS",
                "company_industry": "IT Services",
                "start_date": "2017-04-01",
                "end_date": "2019-12-31",
                "is_current": False,
                "duration_months": 33,
                "description": (
                    "Led campus recruitment drives across top engineering colleges. "
                    "HR policy design and employee lifecycle management. "
                    "Coordinated with hiring managers for technical screening."
                ),
            },
        ],
        "skills": [
            # Keyword stuffed AI skills — should not help
            {"name": "Machine Learning", "proficiency": "advanced", "duration_months": 0},
            {"name": "Deep Learning", "proficiency": "advanced", "duration_months": 0},
            {"name": "NLP", "proficiency": "expert", "duration_months": 0},
            {"name": "Python", "proficiency": "intermediate", "duration_months": 0},
            {"name": "PyTorch", "proficiency": "advanced", "duration_months": 0},
            {"name": "Transformers", "proficiency": "advanced", "duration_months": 0},
            # Legitimate HR skills
            {"name": "Recruitment", "proficiency": "expert", "duration_months": 96},
            {"name": "HR Management", "proficiency": "expert", "duration_months": 96},
        ],
        "education": [
            {"degree": "MBA", "field": "Human Resources", "start_year": 2015, "end_year": 2017},
        ],
        "redrob_signals": {
            "last_active_date": "2025-05-20",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.50,
            "notice_period_days": 45,
            "expected_salary_range_inr_lpa": {"min": 15, "max": 25},
            "skill_assessment_scores": {},
            "github_activity_score": 0,
            "interview_completion_rate": 0.40,
            "offer_acceptance_rate": 0.50,
        },
    }


def _consulting_only_candidate() -> dict:
    """
    Persona 4: Consulting-only career.
    Entire career at TCS and Wipro. Has some ML work description.
    Expected final_career_score <= 0.40
    """
    return {
        "candidate_id": "CAND_TEST004",
        "profile": {
            "name": "Rahul Kumar",
            "current_title": "Senior ML Engineer",
            "current_industry": "IT Services",
            "years_of_experience": 6,
            "location": "Noida",
            "country": "India",
        },
        "career_history": [
            {
                "title": "Senior ML Engineer",
                "company": "TCS",
                "company_industry": "IT Services",
                "start_date": "2021-01-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 53,
                "description": (
                    "Developed machine learning models for client projects. "
                    "Used Python and scikit-learn for basic classification tasks. "
                    "Delivered reports to banking clients on model predictions."
                ),
            },
            {
                "title": "ML Engineer",
                "company": "Wipro",
                "company_industry": "IT Services",
                "start_date": "2018-07-01",
                "end_date": "2020-12-31",
                "is_current": False,
                "duration_months": 30,
                "description": (
                    "Built data pipelines using Spark and Airflow for ETL. "
                    "Some machine learning model deployment work. "
                    "Worked on NLP classification for client document processing."
                ),
            },
        ],
        "skills": [
            {"name": "Python", "proficiency": "advanced", "duration_months": 72},
            {"name": "Machine Learning", "proficiency": "advanced", "duration_months": 60},
            {"name": "NLP", "proficiency": "intermediate", "duration_months": 36},
            {"name": "Spark", "proficiency": "intermediate", "duration_months": 30},
        ],
        "education": [
            {"degree": "B.E.", "field": "Computer Science", "start_year": 2014, "end_year": 2018},
        ],
        "redrob_signals": {
            "last_active_date": "2025-03-01",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.40,
            "notice_period_days": 90,
            "expected_salary_range_inr_lpa": {"min": 18, "max": 35},
            "skill_assessment_scores": {},
            "github_activity_score": 15,
            "interview_completion_rate": 0.55,
            "offer_acceptance_rate": 0.45,
        },
    }


def _product_company_candidate() -> dict:
    """
    Persona 5: Strong product-company ML candidate.
    SaaS + Fintech + AI roles with retrieval/ranking experience.
    Expected final_career_score >= 0.65
    """
    return {
        "candidate_id": "CAND_TEST005",
        "profile": {
            "name": "Kavya Nair",
            "current_title": "AI Engineer",
            "current_industry": "AI/ML",
            "years_of_experience": 6,
            "location": "Hyderabad",
            "country": "India",
        },
        "career_history": [
            {
                "title": "AI Engineer",
                "company": "Sarvam AI",
                "company_industry": "Conversational AI",
                "start_date": "2023-01-01",
                "end_date": None,
                "is_current": True,
                "duration_months": 29,
                "description": (
                    "Building LLM-based retrieval augmented generation (RAG) pipelines. "
                    "Dense retrieval using sentence-transformers and vector databases (Weaviate, Qdrant). "
                    "Implemented hybrid search with BM25 and dense retrieval. "
                    "Evaluated ranking quality using NDCG and MRR metrics."
                ),
            },
            {
                "title": "Senior Data Scientist",
                "company": "PhonePe",
                "company_industry": "Fintech",
                "start_date": "2021-01-01",
                "end_date": "2022-12-31",
                "is_current": False,
                "duration_months": 24,
                "description": (
                    "Built recommendation systems for financial product suggestions. "
                    "NLP-based transaction categorization using transformers. "
                    "Machine learning models for fraud detection with ranking-based evaluation."
                ),
            },
            {
                "title": "Data Scientist",
                "company": "Zoho",
                "company_industry": "SaaS",
                "start_date": "2019-01-01",
                "end_date": "2020-12-31",
                "is_current": False,
                "duration_months": 24,
                "description": (
                    "Developed ML models for customer segmentation and churn prediction. "
                    "Built semantic search features using embeddings. "
                    "Used scikit-learn, XGBoost for tabular ML."
                ),
            },
        ],
        "skills": [
            {"name": "Sentence Transformers", "proficiency": "advanced", "duration_months": 30},
            {"name": "Weaviate", "proficiency": "advanced", "duration_months": 24},
            {"name": "Qdrant", "proficiency": "intermediate", "duration_months": 18},
            {"name": "RAG", "proficiency": "advanced", "duration_months": 24},
            {"name": "NLP", "proficiency": "expert", "duration_months": 60},
            {"name": "Recommendation Systems", "proficiency": "advanced", "duration_months": 36},
        ],
        "education": [
            {"degree": "B.Tech", "field": "Computer Science", "start_year": 2015, "end_year": 2019},
        ],
        "redrob_signals": {
            "last_active_date": "2025-05-25",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.75,
            "notice_period_days": 30,
            "expected_salary_range_inr_lpa": {"min": 28, "max": 50},
            "skill_assessment_scores": {},
            "github_activity_score": 55,
            "interview_completion_rate": 0.80,
            "offer_acceptance_rate": 0.65,
        },
    }


# ===========================================================================
# Tests for date_utils
# ===========================================================================

class TestDateUtils:
    """Unit tests for src/utils/date_utils.py functions."""

    def test_parse_date_full_iso(self):
        assert parse_date("2022-03-15") == date(2022, 3, 15)

    def test_parse_date_year_month(self):
        result = parse_date("2022-03")
        assert result is not None
        assert result.year == 2022 and result.month == 3

    def test_parse_date_year_only(self):
        result = parse_date("2022")
        assert result is not None
        assert result.year == 2022

    def test_parse_date_none(self):
        assert parse_date(None) is None

    def test_parse_date_empty_string(self):
        assert parse_date("") is None

    def test_parse_date_invalid_format(self):
        assert parse_date("not-a-date") is None
        assert parse_date("32-13-2020") is None

    def test_months_between_basic(self):
        assert months_between(date(2020, 1, 1), date(2022, 7, 1)) == 30

    def test_months_between_same_date(self):
        assert months_between(date(2022, 1, 1), date(2022, 1, 1)) == 0

    def test_months_between_reversed(self):
        # Returns 0 for reversed dates, not negative
        assert months_between(date(2022, 7, 1), date(2020, 1, 1)) == 0

    def test_years_between_basic(self):
        yrs = years_between(date(2018, 1, 1), date(2024, 7, 1))
        assert 6.0 <= yrs <= 7.0

    def test_years_between_zero(self):
        assert years_between(date(2022, 1, 1), date(2022, 1, 1)) == 0.0

    def test_career_gap_no_gaps(self):
        history = [
            {"start_date": "2018-01-01", "end_date": "2020-01-01", "is_current": False},
            {"start_date": "2020-01-01", "end_date": "2022-01-01", "is_current": False},
        ]
        assert career_gap_months(history, TODAY) == 0

    def test_career_gap_with_gap(self):
        history = [
            {"start_date": "2018-01-01", "end_date": "2020-01-01", "is_current": False},
            {"start_date": "2021-01-01", "end_date": "2023-01-01", "is_current": False},
        ]
        gap = career_gap_months(history, TODAY)
        assert gap == 12  # 12-month gap between Jan 2020 and Jan 2021

    def test_career_gap_overlapping_roles(self):
        # Overlapping roles should not produce negative gaps
        history = [
            {"start_date": "2019-01-01", "end_date": "2021-06-01", "is_current": False},
            {"start_date": "2020-01-01", "end_date": "2022-01-01", "is_current": False},
        ]
        gap = career_gap_months(history, TODAY)
        assert gap >= 0

    def test_career_gap_empty_history(self):
        assert career_gap_months([], TODAY) == 0

    def test_recency_decay_today(self):
        result = recency_decay(TODAY, today=TODAY, half_life_days=365)
        assert result == 1.0

    def test_recency_decay_half_life(self):
        event = date(TODAY.year - 1, TODAY.month, TODAY.day)
        result = recency_decay(event, today=TODAY, half_life_days=365)
        assert 0.45 <= result <= 0.55  # approximately 0.5

    def test_recency_decay_future_date(self):
        future = date(TODAY.year + 1, 1, 1)
        result = recency_decay(future, today=TODAY, half_life_days=365)
        assert result == 1.0  # future events get full weight


# ===========================================================================
# Tests for text_utils
# ===========================================================================

class TestTextUtils:
    """Unit tests for src/utils/text_utils.py functions."""

    def test_normalize_title_abbreviations(self):
        assert normalize_title("Sr. ML Engineer") == "senior machine learning engineer"

    def test_normalize_title_sde(self):
        result = normalize_title("SDE-2")
        assert "senior" in result and "software engineer" in result

    def test_normalize_title_nlp(self):
        result = normalize_title("NLP Scientist")
        assert "natural language processing" in result

    def test_normalize_title_lowercase(self):
        result = normalize_title("SENIOR AI ENGINEER")
        assert result == result.lower()

    def test_normalize_title_empty(self):
        assert normalize_title("") == ""

    def test_normalize_skill_sbert(self):
        assert normalize_skill("SBERT") == "sentence transformers"

    def test_normalize_skill_sklearn(self):
        assert normalize_skill("sklearn") == "scikit learn"

    def test_normalize_skill_xgboost(self):
        assert normalize_skill("XGBoost") == "xgboost"

    def test_normalize_skill_empty(self):
        assert normalize_skill("") == ""

    def test_fuzzy_match_exact_after_normalize(self):
        result = fuzzy_match(
            "senior ml engineer",
            ["senior machine learning engineer", "data scientist"],
        )
        assert result is not None
        matched, score = result
        assert score >= 80.0

    def test_fuzzy_match_no_match_below_threshold(self):
        result = fuzzy_match("hr manager", ["machine learning engineer"], threshold=80)
        assert result is None

    def test_fuzzy_match_empty_query(self):
        assert fuzzy_match("", ["machine learning engineer"]) is None

    def test_title_similarity_identical(self):
        score = title_similarity("Senior ML Engineer", "Senior ML Engineer")
        assert score == 1.0

    def test_title_similarity_dissimilar(self):
        score = title_similarity("HR Manager", "Senior ML Engineer")
        assert score < 0.5

    def test_keyword_relevance_full_match(self):
        text = "retrieval ranking embeddings recommendation vector NLP machine learning"
        keywords = ["retrieval", "ranking", "embeddings"]
        score = keyword_relevance(text, keywords)
        assert score == 1.0

    def test_keyword_relevance_partial_match(self):
        text = "Built ranking and retrieval system"
        keywords = ["retrieval", "ranking", "embeddings", "NLP"]
        score = keyword_relevance(text, keywords)
        assert score == pytest.approx(0.5, abs=0.01)

    def test_keyword_relevance_no_match(self):
        text = "Managed HR operations and payroll"
        keywords = ["retrieval", "ranking", "embeddings"]
        score = keyword_relevance(text, keywords)
        assert score == 0.0

    def test_keyword_relevance_empty_text(self):
        assert keyword_relevance("", ["retrieval"]) == 0.0

    def test_keyword_relevance_weighted(self):
        text = "retrieval ranking"
        keywords = ["retrieval", "ranking", "embeddings"]
        weights = {"retrieval": 2.0, "ranking": 1.0, "embeddings": 1.0}
        score = keyword_relevance(text, keywords, weights)
        # matched: retrieval (2.0) + ranking (1.0) = 3.0 / total (4.0) = 0.75
        assert score == pytest.approx(0.75, abs=0.01)


# ===========================================================================
# Integration tests — score_career() with full personas
# ===========================================================================

class TestCareerScorerPersonas:
    """Integration tests for score_career() using the five candidate personas."""

    # ------------------------------------------------------------------
    # Persona 1: ML Engineer — should score HIGH
    # ------------------------------------------------------------------

    def test_ml_engineer_final_score_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)

        assert isinstance(result, CareerScoreResult)
        assert 0.0 <= result.final_career_score <= 1.0
        assert result.final_career_score >= 0.75, (
            f"ML Engineer should score >= 0.75, got {result.final_career_score:.3f}\n"
            f"Explanation: {result.explanation}"
        )

    def test_ml_engineer_title_relevance_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert result.title_relevance_score >= 0.60

    def test_ml_engineer_product_company_score_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert result.product_company_score >= 0.60, (
            f"ML Engineer at product companies should score >= 0.60, got {result.product_company_score:.3f}"
        )

    def test_ml_engineer_relevant_experience_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert result.relevant_experience_score >= 0.60

    def test_ml_engineer_has_explanation(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 50

    # ------------------------------------------------------------------
    # Persona 2: Data Scientist — should score MODERATE
    # ------------------------------------------------------------------

    def test_data_scientist_final_score_moderate(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _data_scientist_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)

        assert 0.0 <= result.final_career_score <= 1.0
        assert result.final_career_score >= 0.45, (
            f"Data Scientist should score >= 0.45, got {result.final_career_score:.3f}\n"
            f"Explanation: {result.explanation}"
        )

    def test_data_scientist_scores_below_ml_engineer(self, taxonomies):
        title_tax, industry_tax = taxonomies
        ml_result = score_career(_ml_engineer_candidate(), title_tax, industry_tax, today=TODAY)
        ds_result = score_career(_data_scientist_candidate(), title_tax, industry_tax, today=TODAY)
        assert ml_result.final_career_score > ds_result.final_career_score, (
            f"ML Engineer ({ml_result.final_career_score:.3f}) should score higher "
            f"than Data Scientist ({ds_result.final_career_score:.3f})"
        )

    # ------------------------------------------------------------------
    # Persona 3: HR Manager — should score VERY LOW
    # ------------------------------------------------------------------

    def test_hr_manager_final_score_low(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _hr_manager_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)

        assert 0.0 <= result.final_career_score <= 1.0
        assert result.final_career_score <= 0.20, (
            f"HR Manager should score <= 0.20 (honeypot pattern), got {result.final_career_score:.3f}\n"
            f"Explanation: {result.explanation}"
        )

    def test_hr_manager_title_relevance_zero(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _hr_manager_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        # HR Manager is Tier 4 in taxonomy
        assert result.title_relevance_score <= 0.10

    def test_hr_manager_career_history_relevance_low(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _hr_manager_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        # HR descriptions have no retrieval/ranking keywords
        assert result.career_history_relevance_score <= 0.15

    # ------------------------------------------------------------------
    # Persona 4: Consulting-only — should score LOW-MODERATE
    # ------------------------------------------------------------------

    def test_consulting_only_final_score_low(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _consulting_only_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)

        assert 0.0 <= result.final_career_score <= 1.0
        assert result.final_career_score <= 0.45, (
            f"Consulting-only candidate should score <= 0.45, got {result.final_career_score:.3f}\n"
            f"Explanation: {result.explanation}"
        )

    def test_consulting_only_product_company_score_low(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _consulting_only_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        # TCS/Wipro → should have low product company score
        assert result.product_company_score <= 0.40

    def test_consulting_scores_below_product_company(self, taxonomies):
        """Consulting-only should always score lower than product company ML candidate."""
        title_tax, industry_tax = taxonomies
        consulting_result = score_career(_consulting_only_candidate(), title_tax, industry_tax, today=TODAY)
        product_result = score_career(_product_company_candidate(), title_tax, industry_tax, today=TODAY)
        assert product_result.final_career_score > consulting_result.final_career_score

    # ------------------------------------------------------------------
    # Persona 5: Product Company — should score HIGH
    # ------------------------------------------------------------------

    def test_product_company_final_score_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _product_company_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)

        assert 0.0 <= result.final_career_score <= 1.0
        assert result.final_career_score >= 0.65, (
            f"Product-company ML candidate should score >= 0.65, got {result.final_career_score:.3f}\n"
            f"Explanation: {result.explanation}"
        )

    def test_product_company_career_history_relevance_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _product_company_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        # Descriptions have retrieval, vector DB, NDCG — should be high
        assert result.career_history_relevance_score >= 0.50

    def test_product_company_product_score_high(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = _product_company_candidate()
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert result.product_company_score >= 0.60


# ===========================================================================
# Ordering tests — relative ordering between personas
# ===========================================================================

class TestScoringOrdering:
    """Verify that the scorer produces correct relative ordering between personas."""

    def test_full_ordering(self, taxonomies):
        """
        Expected ordering from highest to lowest:
        ml_engineer > product_company > data_scientist > consulting_only > hr_manager
        """
        title_tax, industry_tax = taxonomies

        ml = score_career(_ml_engineer_candidate(), title_tax, industry_tax, today=TODAY)
        product = score_career(_product_company_candidate(), title_tax, industry_tax, today=TODAY)
        ds = score_career(_data_scientist_candidate(), title_tax, industry_tax, today=TODAY)
        consulting = score_career(_consulting_only_candidate(), title_tax, industry_tax, today=TODAY)
        hr = score_career(_hr_manager_candidate(), title_tax, industry_tax, today=TODAY)

        scores = {
            "ml_engineer": ml.final_career_score,
            "product_company": product.final_career_score,
            "data_scientist": ds.final_career_score,
            "consulting_only": consulting.final_career_score,
            "hr_manager": hr.final_career_score,
        }

        # Technical ML candidates should score higher than non-technical
        assert ml.final_career_score > hr.final_career_score, (
            f"ml_engineer ({scores['ml_engineer']:.3f}) should beat hr_manager ({scores['hr_manager']:.3f})"
        )
        assert product.final_career_score > hr.final_career_score, (
            f"product_company ({scores['product_company']:.3f}) should beat hr_manager ({scores['hr_manager']:.3f})"
        )
        assert ds.final_career_score > hr.final_career_score, (
            f"data_scientist ({scores['data_scientist']:.3f}) should beat hr_manager ({scores['hr_manager']:.3f})"
        )

        # Product companies should beat consulting-only
        assert product.final_career_score > consulting.final_career_score, (
            f"product_company ({scores['product_company']:.3f}) should beat "
            f"consulting_only ({scores['consulting_only']:.3f})"
        )

    def test_all_scores_in_bounds(self, taxonomies):
        """All final_career_score values must be in [0.0, 1.0]."""
        title_tax, industry_tax = taxonomies
        candidates = [
            _ml_engineer_candidate(),
            _data_scientist_candidate(),
            _hr_manager_candidate(),
            _consulting_only_candidate(),
            _product_company_candidate(),
        ]
        for c in candidates:
            result = score_career(c, title_tax, industry_tax, today=TODAY)
            assert 0.0 <= result.final_career_score <= 1.0, (
                f"Score out of bounds for {c['candidate_id']}: {result.final_career_score}"
            )
            assert 0.0 <= result.title_relevance_score <= 1.0
            assert 0.0 <= result.career_history_relevance_score <= 1.0
            assert 0.0 <= result.product_company_score <= 1.0
            assert 0.0 <= result.relevant_experience_score <= 1.0
            assert 0.0 <= result.career_consistency_score <= 1.0


# ===========================================================================
# Edge case tests
# ===========================================================================

class TestEdgeCases:
    """Edge cases: empty history, None dates, minimal profiles."""

    def test_empty_career_history(self, taxonomies):
        title_tax, industry_tax = taxonomies
        candidate = {
            "candidate_id": "CAND_EDGE001",
            "profile": {
                "current_title": "ML Engineer",
                "current_industry": "Software",
                "years_of_experience": 0,
                "location": "Pune",
                "country": "India",
            },
            "career_history": [],
            "skills": [],
            "education": [],
            "redrob_signals": {
                "last_active_date": "2025-01-01",
                "open_to_work_flag": False,
                "recruiter_response_rate": 0.5,
                "notice_period_days": 30,
                "expected_salary_range_inr_lpa": {"min": 10, "max": 20},
                "skill_assessment_scores": {},
                "github_activity_score": 0,
                "interview_completion_rate": 0.5,
                "offer_acceptance_rate": 0.5,
            },
        }
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert 0.0 <= result.final_career_score <= 1.0
        # Minimal profile — score should be low but not crash
        assert result.final_career_score < 0.5

    def test_missing_dates_in_roles(self, taxonomies):
        """Roles without start_date should not crash; should use defaults."""
        title_tax, industry_tax = taxonomies
        candidate = {
            "candidate_id": "CAND_EDGE002",
            "profile": {
                "current_title": "Data Scientist",
                "current_industry": "SaaS",
                "years_of_experience": 3,
                "location": "Pune",
                "country": "India",
            },
            "career_history": [
                {
                    "title": "Data Scientist",
                    "company": "Startup Inc",
                    "company_industry": "SaaS",
                    "start_date": None,    # No start date
                    "end_date": None,
                    "is_current": True,
                    "duration_months": 36,
                    "description": "Machine learning and NLP work",
                },
            ],
            "skills": [],
            "education": [],
            "redrob_signals": {
                "last_active_date": "2025-01-01",
                "open_to_work_flag": True,
                "recruiter_response_rate": 0.5,
                "notice_period_days": 30,
                "expected_salary_range_inr_lpa": {"min": 10, "max": 20},
                "skill_assessment_scores": {},
                "github_activity_score": 0,
                "interview_completion_rate": 0.5,
                "offer_acceptance_rate": 0.5,
            },
        }
        # Must not raise
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert 0.0 <= result.final_career_score <= 1.0

    def test_single_role_candidate(self, taxonomies):
        """Single role — should still produce valid scores."""
        title_tax, industry_tax = taxonomies
        candidate = {
            "candidate_id": "CAND_EDGE003",
            "profile": {
                "current_title": "Senior ML Engineer",
                "current_industry": "AI/ML",
                "years_of_experience": 4,
                "location": "Bangalore",
                "country": "India",
            },
            "career_history": [
                {
                    "title": "Senior ML Engineer",
                    "company": "OpenAI Partner",
                    "company_industry": "AI/ML",
                    "start_date": "2021-01-01",
                    "end_date": None,
                    "is_current": True,
                    "duration_months": 53,
                    "description": "Retrieval and ranking systems using embeddings and vector databases.",
                },
            ],
            "skills": [{"name": "Python", "proficiency": "expert", "duration_months": 48}],
            "education": [],
            "redrob_signals": {
                "last_active_date": "2025-05-01",
                "open_to_work_flag": True,
                "recruiter_response_rate": 0.8,
                "notice_period_days": 30,
                "expected_salary_range_inr_lpa": {"min": 25, "max": 45},
                "skill_assessment_scores": {},
                "github_activity_score": 50,
                "interview_completion_rate": 0.75,
                "offer_acceptance_rate": 0.6,
            },
        }
        result = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert 0.0 <= result.final_career_score <= 1.0
        # Strong single role should still produce a reasonable score
        assert result.final_career_score >= 0.40

    def test_result_is_frozen_dataclass(self, taxonomies):
        """CareerScoreResult must be immutable (frozen dataclass)."""
        title_tax, industry_tax = taxonomies
        result = score_career(_ml_engineer_candidate(), title_tax, industry_tax, today=TODAY)
        with pytest.raises((AttributeError, TypeError)):
            result.final_career_score = 0.0  # type: ignore[misc]

    def test_determinism(self, taxonomies):
        """Same input always produces same output."""
        title_tax, industry_tax = taxonomies
        candidate = _ml_engineer_candidate()
        r1 = score_career(candidate, title_tax, industry_tax, today=TODAY)
        r2 = score_career(candidate, title_tax, industry_tax, today=TODAY)
        assert r1.final_career_score == r2.final_career_score
        assert r1.explanation == r2.explanation
