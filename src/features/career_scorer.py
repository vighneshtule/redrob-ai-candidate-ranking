"""
src/features/career_scorer.py
==============================
Career relevance scoring for the Redrob candidate ranking engine.

This is the highest-signal feature block in the Phase 3 pipeline.
It evaluates WHAT a candidate has done and WHERE they have done it —
not how many AI buzzwords they listed.

Design principles
-----------------
* No embeddings, no LLMs, no external network calls.
* Pure Python + stdlib + rapidfuzz.
* Deterministic — identical input → identical output.
* Every sub-scorer is independently callable for testing and debugging.
* All state is local; module is thread-safe.

Sub-scorers
-----------
1. Title Relevance       — current title + career history titles vs title_taxonomy
2. Career History Relevance — role description keyword coverage, duration-weighted
3. Product Company Score — industry/company type classification, recency-weighted
4. Relevant Experience   — AI/ML/Search relevant months → score curve
5. Career Consistency    — title progression, industry stability, gap penalty

Public API
----------
    score_career(candidate, title_taxonomy, industry_taxonomy) -> CareerScoreResult
    CareerScoreResult                                          -- frozen dataclass
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.utils.date_utils import (
    career_gap_months,
    months_between,
    parse_date,
    recency_decay,
)
from src.utils.text_utils import keyword_relevance, normalize_title


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CareerScoreResult:
    """
    Output of score_career().  Frozen → hashable, thread-safe.

    Attributes
    ----------
    title_relevance_score : float [0, 1]
        How relevant is the candidate's title history to the target role.
    career_history_relevance_score : float [0, 1]
        How much of the candidate's work description overlaps with
        retrieval/ranking/ML keywords.
    product_company_score : float [0, 1]
        Fraction of career at product companies (vs IT services/consulting).
    relevant_experience_score : float [0, 1]
        Converts AI/ML/Search relevant years into a score tuned to the JD's
        5–9 year target band.
    career_consistency_score : float [0, 1]
        Title progression + industry stability + timeline continuity.
    final_career_score : float [0, 1]
        Weighted aggregate of all five sub-scores.
    explanation : str
        Human-readable reasoning string for transparency.
    """

    title_relevance_score: float
    career_history_relevance_score: float
    product_company_score: float
    relevant_experience_score: float
    career_consistency_score: float
    final_career_score: float
    explanation: str


# ---------------------------------------------------------------------------
# Module-level constants (immutable)
# ---------------------------------------------------------------------------

# Tier score mapping for title taxonomy
_TIER_SCORES: dict[str, float] = {
    "tier_1": 1.00,
    "tier_2": 0.65,
    "tier_3": 0.30,
    "tier_4": 0.00,
}

# Half-life for title/role recency decay (1 year)
_TITLE_RECENCY_HALF_LIFE_DAYS: float = 365.0

# Half-life for product company recency decay (2 years — company type is stickier)
_COMPANY_RECENCY_HALF_LIFE_DAYS: float = 730.0

# Domain keywords for career history relevance and relevant experience detection.
# Grouped by tier: must-have retrieval topics (high weight) vs adjacent (lower weight).
_RETRIEVAL_KEYWORDS_WEIGHTED: dict[str, float] = {
    # Core retrieval / ranking (Tier-A JD terms)
    "retrieval":            2.0,
    "ranking":              2.0,
    "search":               1.5,
    "embeddings":           2.0,
    "embedding":            2.0,
    "recommendation":       1.5,
    "recommender":          1.5,
    "vector database":      2.0,
    "vector db":            2.0,
    "vector store":         2.0,
    "information retrieval": 2.0,
    "faiss":                1.5,
    "pinecone":             1.5,
    "weaviate":             1.5,
    "qdrant":               1.5,
    "milvus":               1.5,
    "opensearch":           1.5,
    "elasticsearch":        1.0,
    "hybrid search":        2.0,
    "bm25":                 1.5,
    "dense retrieval":      2.0,
    "re-ranking":           1.5,
    "reranking":            1.5,
    # Evaluation
    "ndcg":                 1.5,
    "mrr":                  1.5,
    "a/b testing":          1.0,
    "offline evaluation":   1.5,
    # NLP / ML core
    "nlp":                  1.5,
    "natural language processing": 1.5,
    "machine learning":     1.0,
    "deep learning":        1.0,
    "llm":                  1.0,
    "large language model": 1.0,
    "transformers":         1.0,
    "bert":                 1.0,
    "fine-tuning":          1.0,
    "fine tuning":          1.0,
    "model training":       0.8,
    "neural network":       0.8,
    "pytorch":              0.8,
    "tensorflow":           0.8,
    # Learning to rank
    "learning to rank":     1.5,
    "ltr":                  1.5,
    "lambdamart":           1.5,
    # Adjacent positive
    "rag":                  1.0,
    "retrieval augmented":  1.0,
    "semantic search":      1.5,
    "sentence transformers": 1.5,
}

# Flat list of keywords (used where weights aren't needed)
_RETRIEVAL_KEYWORDS: list[str] = list(_RETRIEVAL_KEYWORDS_WEIGHTED.keys())

# Minimum keyword relevance score for a role to count toward "relevant experience"
_RELEVANCE_THRESHOLD: float = 0.08

# Seniority level map for progression scoring
_SENIORITY_KEYWORDS: list[tuple[list[str], int]] = [
    (["intern", "trainee", "apprentice"], 1),
    (["junior", "associate", "entry"], 2),
    (["engineer", "developer", "scientist", "analyst"], 3),    # mid-level default
    (["senior", "lead"], 4),
    (["staff", "principal", "distinguished"], 5),
    (["director", "vp", "chief", "head of", "cto", "cmo"], 6),
    (["manager"], 3),    # management track separate — treated as same as mid
]

# Industry taxonomy category → score multiplier
_INDUSTRY_MULTIPLIER_MAP: dict[str, float] = {
    # Product companies (positive)
    "Software":         1.0,
    "SaaS":             1.0,
    "Fintech":          1.0,
    "E-commerce":       1.0,
    "AI/ML":            1.1,
    "AI Services":      1.0,
    "HealthTech":       0.9,
    "HealthTech AI":    1.0,
    "EdTech":           0.9,
    "Gaming":           0.9,
    "Conversational AI": 1.1,
    "AdTech":           0.9,
    "Insurance Tech":   0.9,
    "Transportation":   0.85,
    "Food Delivery":    0.85,
    "Media Tech":       0.9,
    "Cloud":            1.0,
    "Cybersecurity":    0.9,
    "PropTech":         0.85,
    "LegalTech":        0.85,
    "RegTech":          0.85,
    # IT Services / Consulting (negative)
    "IT Services":      0.50,
    "Consulting":       0.50,
    # Neutral
    "Conglomerate":     0.75,
    "Manufacturing":    0.75,
    "Paper Products":   0.75,
    "Retail":           0.75,
    "Banking":          0.75,
    "Telecom":          0.75,
    "Healthcare":       0.75,
    "Education":        0.75,
    "Government":       0.75,
    "Non-profit":       0.75,
}

# Negative company names (substring match, lowercased)
_NEGATIVE_COMPANY_NAMES: frozenset[str] = frozenset({
    "tcs", "tata consultancy", "infosys", "wipro", "accenture",
    "cognizant", "capgemini", "hcl", "tech mahindra", "mphasis",
    "mindtree", "ltimindtree", "l&t infotech", "lti", "hexaware",
    "zensar", "persistent systems", "niit technologies", "cyient",
    "igate", "patni", "kpit", "birlasoft", "mastech",
})

# Product company industry set (for quick membership check)
_PRODUCT_INDUSTRIES: frozenset[str] = frozenset({
    "Software", "SaaS", "Fintech", "E-commerce", "AI/ML", "AI Services",
    "HealthTech", "HealthTech AI", "EdTech", "Gaming", "Conversational AI",
    "AdTech", "Insurance Tech", "Transportation", "Food Delivery",
    "Media Tech", "Cloud", "Cybersecurity", "PropTech", "LegalTech", "RegTech",
})

_CAREER_WEIGHTS: dict[str, float] = {
    "title_relevance":           0.35,
    "career_history_relevance":  0.35,
    "product_company":           0.10,
    "relevant_experience":       0.15,
    "career_consistency":        0.05,
}
assert abs(sum(_CAREER_WEIGHTS.values()) - 1.0) < 1e-9, "Career sub-weights must sum to 1.0"

# Reference date — set at module load, overrideable in tests via parameter injection
_TODAY: date = datetime.utcnow().date()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_today() -> date:
    """Returns UTC today; override in tests by patching this function or passing today."""
    return datetime.utcnow().date()


def _lookup_tier(
    normalized_title: str,
    tier_lists: dict[str, list[str]],
) -> tuple[str, float]:
    """
    Look up a normalised title against tier lists from title_taxonomy.json.

    Returns the best (tier_name, score) tuple.  If no match: ('none', 0.0).

    Strategy
    ---------
    1. Exact substring match against tier lists (tier_1 → tier_4 priority order).
    2. Return the first matching tier found.
    3. If no match found in any tier → ('none', 0.0) — unknown title, not penalised.

    Note: tier_4 IS explicitly 0.0, distinguishing it from 'no match'.
    """
    for tier_name in ("tier_1", "tier_2", "tier_3", "tier_4"):
        tier_titles = tier_lists.get(tier_name, {}).get("titles", [])
        for t in tier_titles:
            if t in normalized_title or normalized_title in t:
                return (tier_name, _TIER_SCORES[tier_name])

    return ("none", 0.35)  # Unknown title → treat as weak tier-3 equivalent


def _apply_company_modifier(
    base_score: float,
    company_name: str,
    company_industry: str,
    title_taxonomy: dict,
) -> float:
    """
    Apply company-context modifier from title_taxonomy.json.

    Modifiers (applied multiplicatively, capped at 1.0 for tier scores > 0):
    - AI/ML company:      ×1.2
    - Product startup:    ×1.1 (company_size in small ranges)
    - Consulting firm:    ×0.6
    """
    if base_score == 0.0:
        return 0.0  # Tier-4 — no modifier can rescue it

    modifiers = title_taxonomy.get("company_context_modifiers", {})

    # Check AI/ML company
    ai_industries = set(modifiers.get("ai_ml_company", {}).get("industries", []))
    if company_industry in ai_industries:
        return min(base_score * modifiers.get("ai_ml_company", {}).get("modifier", 1.2), 1.0)

    # Check consulting firm by name
    consulting_names = [
        n.lower() for n in modifiers.get("consulting_firm", {}).get("company_names", [])
    ]
    company_lower = company_name.lower()
    if any(neg in company_lower for neg in consulting_names):
        return base_score * modifiers.get("consulting_firm", {}).get("modifier", 0.6)

    return base_score


def _get_seniority_level(title: str) -> int:
    """
    Map a job title to an integer seniority level (1=intern, 6=C-suite).

    Returns 3 (mid-level default) if no clear signal is found.
    """
    nt = normalize_title(title)
    best_level = 3  # default mid

    for keywords, level in _SENIORITY_KEYWORDS:
        if any(kw in nt for kw in keywords):
            best_level = max(best_level, level)

    return best_level


def _is_negative_company(company_name: str) -> bool:
    """Return True if company_name matches a known IT services/consulting firm."""
    cn = company_name.lower().strip()
    return any(neg in cn for neg in _NEGATIVE_COMPANY_NAMES)


def _classify_industry(
    company_industry: str,
    company_name: str,
) -> float:
    """
    Return a [0.4, 1.1] multiplier for a company based on industry + name.

    Logic mirrors industry_taxonomy.json classification_logic:
    1. Check name against known negatives → 0.4
    2. Check industry against IT Services / Consulting → 0.5
    3. Check against product company list → 1.0 (or 1.1 for AI/ML)
    4. Else neutral → 0.75
    """
    # Step 1: Name-based hard penalty (stronger than industry classification)
    if _is_negative_company(company_name):
        return 0.4

    # Step 2: Industry-level lookup
    multiplier = _INDUSTRY_MULTIPLIER_MAP.get(company_industry, 0.75)
    return multiplier


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _score_title_relevance(
    candidate: dict,
    title_taxonomy: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute title relevance score [0, 1].

    Formula
    -------
    score = 0.40 × current_title_score + 0.60 × weighted_history_score

    History weighting: each role's tier score is multiplied by
    duration_months × recency_decay(role_start, today, half_life=365d).
    """
    profile = candidate.get("profile") or {}
    career_history = candidate.get("career_history") or []

    tier_lists = title_taxonomy  # tier_1, tier_2, tier_3, tier_4 at top level

    # --- Current title ---
    current_raw = profile.get("current_title", "")
    current_norm = normalize_title(current_raw)
    current_industry = profile.get("current_industry", "")

    _, current_score = _lookup_tier(current_norm, tier_lists)

    # Apply company context modifier for current role
    current_company = ""
    if career_history:
        current_roles = [r for r in career_history if r.get("is_current")]
        if current_roles:
            current_company = current_roles[0].get("company", "")
    current_score = _apply_company_modifier(
        current_score, current_company, current_industry, title_taxonomy
    )
    current_score = min(current_score, 1.0)

    # --- Career history titles ---
    total_weight = 0.0
    weighted_sum = 0.0
    roles_desc: list[str] = []

    for role in career_history:
        role_title_raw = role.get("title", "")
        if not role_title_raw:
            continue

        norm_role_title = normalize_title(role_title_raw)
        tier_name, tier_score = _lookup_tier(norm_role_title, tier_lists)

        # Company context modifier
        role_company = role.get("company", "")
        role_industry = role.get("company_industry", "")
        tier_score = _apply_company_modifier(
            tier_score, role_company, role_industry, title_taxonomy
        )
        tier_score = min(tier_score, 1.0)

        # Duration weight
        duration_months = float(role.get("duration_months", 0) or 0)
        if duration_months <= 0:
            # Estimate from dates if available
            start = parse_date(role.get("start_date"))
            end_str = role.get("end_date")
            is_current = role.get("is_current", False)
            if start:
                end = parse_date(end_str) if (end_str and not is_current) else today
                if end:
                    duration_months = float(max(0, months_between(start, end)))
            if duration_months <= 0:
                duration_months = 12.0  # default 1-year estimate

        # Recency decay: use start_date as the reference point for the role
        start_date = parse_date(role.get("start_date"))
        if start_date:
            decay = recency_decay(start_date, today, _TITLE_RECENCY_HALF_LIFE_DAYS)
        else:
            decay = 0.5  # unknown date → moderate recency

        role_weight = duration_months * decay
        weighted_sum += tier_score * role_weight
        total_weight += role_weight
        roles_desc.append(f"{role_title_raw}({tier_name})")

    history_score = (weighted_sum / total_weight) if total_weight > 0 else 0.0
    history_score = min(history_score, 1.0)

    # Combine
    combined = 0.40 * current_score + 0.60 * history_score
    combined = round(min(combined, 1.0), 4)

    # Explanation fragment
    tier_label = "Tier 1" if current_score >= 0.95 else \
                 "Tier 2" if current_score >= 0.60 else \
                 "Tier 3" if current_score >= 0.25 else "Tier 4"
    expl = (
        f"Current title '{current_raw}' ({tier_label}, score={current_score:.2f}). "
        f"Career history: {len(career_history)} roles."
    )

    return combined, expl


def _score_career_history_relevance(
    candidate: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute career history relevance score [0, 1].

    For each role, compute keyword_relevance(description, RETRIEVAL_KEYWORDS).
    Weight by duration_months × recency_decay.  Take duration-weighted mean.
    """
    career_history = candidate.get("career_history") or []

    if not career_history:
        return 0.0, "No career history."

    total_weight = 0.0
    weighted_relevance = 0.0
    top_roles: list[str] = []

    for role in career_history:
        description = role.get("description", "") or ""
        title_text = role.get("title", "") or ""
        # Combine title and description for keyword search
        combined_text = f"{title_text} {description}"

        rel = keyword_relevance(combined_text, _RETRIEVAL_KEYWORDS, _RETRIEVAL_KEYWORDS_WEIGHTED)

        duration_months = float(role.get("duration_months", 0) or 0)
        if duration_months <= 0:
            start = parse_date(role.get("start_date"))
            end_str = role.get("end_date")
            is_current = role.get("is_current", False)
            if start:
                end = parse_date(end_str) if (end_str and not is_current) else today
                if end:
                    duration_months = float(max(0, months_between(start, end)))
            if duration_months <= 0:
                duration_months = 12.0

        start_date = parse_date(role.get("start_date"))
        decay = recency_decay(start_date, today, _TITLE_RECENCY_HALF_LIFE_DAYS) if start_date else 0.5

        role_weight = duration_months * decay
        weighted_relevance += rel * role_weight
        total_weight += role_weight

        if rel > 0.10:
            top_roles.append(f"'{role.get('title', '?')}' (rel={rel:.2f})")

    score = (weighted_relevance / total_weight) if total_weight > 0 else 0.0

    # Scale: keyword_relevance naturally stays low (many keywords, few matched)
    # Apply a sigmoid-like scaling: max raw score ≈ 0.3-0.5 for excellent profiles
    # Scale so that raw 0.25+ → near 1.0
    score = min(score / 0.25, 1.0)
    score = round(score, 4)

    expl = (
        f"Retrieval/ranking/ML exposure in {len(top_roles)} role(s). "
        + (f"Top: {', '.join(top_roles[:3])}." if top_roles else "No strong ML/retrieval signal found.")
    )

    return score, expl


def _score_product_company(
    candidate: dict,
    industry_taxonomy: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute product-company score [0, 1].

    Each role contributes:  industry_multiplier × duration_months × recency_decay.
    The raw sum is normalised by total duration (with multiplier 1.0 as baseline).

    If ANY role is at a product company → floor = 0.2 (not a pure services candidate).
    """
    career_history = candidate.get("career_history") or []

    if not career_history:
        return 0.0, "No career history."

    total_months = 0.0
    weighted_product_months = 0.0
    has_product_company = False
    has_consulting_only = True
    company_notes: list[str] = []

    for role in career_history:
        company_name = role.get("company", "") or ""
        company_industry = role.get("company_industry", "") or ""

        multiplier = _classify_industry(company_industry, company_name)

        duration_months = float(role.get("duration_months", 0) or 0)
        if duration_months <= 0:
            start = parse_date(role.get("start_date"))
            end_str = role.get("end_date")
            is_current = role.get("is_current", False)
            if start:
                end = parse_date(end_str) if (end_str and not is_current) else today
                if end:
                    duration_months = float(max(0, months_between(start, end)))
            if duration_months <= 0:
                duration_months = 12.0

        start_date = parse_date(role.get("start_date"))
        decay = recency_decay(start_date, today, _COMPANY_RECENCY_HALF_LIFE_DAYS) if start_date else 0.5

        role_weight = duration_months * decay

        # Track whether this is a product company
        is_product = company_industry in _PRODUCT_INDUSTRIES and not _is_negative_company(company_name)
        is_consulting = (
            company_industry in {"IT Services", "Consulting"}
            or _is_negative_company(company_name)
        )

        if is_product:
            has_product_company = True
        if not is_consulting:
            has_consulting_only = False

        weighted_product_months += multiplier * role_weight
        total_months += role_weight  # baseline: all roles at 1.0 multiplier

        note = f"{company_name or '?'} ({company_industry or 'unknown'}, ×{multiplier:.1f})"
        company_notes.append(note)

    # Normalise: divide by total months (so 1.0 = all time at product companies)
    score = (weighted_product_months / total_months) if total_months > 0 else 0.0

    # Apply floor if any product company exposure
    if has_product_company and score < 0.2:
        score = 0.2

    score = round(min(score, 1.0), 4)

    if has_consulting_only:
        expl = (
            f"Entire career at IT services/consulting firms "
            f"({', '.join(c.split('(')[0].strip() for c in company_notes[:3])}). "
            f"Significant negative signal."
        )
    elif has_product_company:
        expl = (
            f"Product company experience detected. "
            f"Companies: {', '.join(company_notes[:3])}{'...' if len(company_notes) > 3 else ''}."
        )
    else:
        expl = f"Mixed industry background. Companies: {', '.join(company_notes[:3])}."

    return score, expl


def _score_relevant_experience(
    candidate: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute relevant experience score [0, 1] based on AI/ML/Search relevant months.

    Only roles with keyword_relevance > _RELEVANCE_THRESHOLD count toward
    relevant experience (to avoid crediting generic software engineering time).

    Score curve (tuned for JD's 5-9yr sweet spot):
    ─────────────────────────────────────────────
    0.0 → 2.0 yr : linear  0.00 → 0.40
    2.0 → 5.0 yr : linear  0.40 → 0.75
    5.0 → 8.0 yr : linear  0.75 → 1.00  ← JD sweet spot
    8.0 → 12.0yr : linear  1.00 → 0.85  ← mild over-qualified signal
    > 12.0 yr    : 0.80 (flat)
    """
    career_history = candidate.get("career_history") or []

    if not career_history:
        return 0.0, "No career history."

    relevant_months = 0.0

    for role in career_history:
        description = role.get("description", "") or ""
        title_text = role.get("title", "") or ""
        combined_text = f"{title_text} {description}"

        rel = keyword_relevance(combined_text, _RETRIEVAL_KEYWORDS, _RETRIEVAL_KEYWORDS_WEIGHTED)

        if rel < _RELEVANCE_THRESHOLD:
            continue  # This role doesn't count as ML/Search relevant

        duration_months = float(role.get("duration_months", 0) or 0)
        if duration_months <= 0:
            start = parse_date(role.get("start_date"))
            end_str = role.get("end_date")
            is_current = role.get("is_current", False)
            if start:
                end = parse_date(end_str) if (end_str and not is_current) else today
                if end:
                    duration_months = float(max(0, months_between(start, end)))
            if duration_months <= 0:
                duration_months = 12.0

        relevant_months += duration_months

    relevant_years = relevant_months / 12.0

    # Piecewise score curve
    if relevant_years <= 0.0:
        score = 0.0
    elif relevant_years <= 2.0:
        score = (relevant_years / 2.0) * 0.40
    elif relevant_years <= 5.0:
        score = 0.40 + ((relevant_years - 2.0) / 3.0) * 0.35
    elif relevant_years <= 8.0:
        score = 0.75 + ((relevant_years - 5.0) / 3.0) * 0.25
    elif relevant_years <= 12.0:
        score = 1.00 - ((relevant_years - 8.0) / 4.0) * 0.15
    else:
        score = 0.80

    score = round(min(score, 1.0), 4)

    expl = (
        f"{relevant_years:.1f} years of AI/ML/Search-relevant experience "
        f"(from {len(career_history)} roles, threshold={_RELEVANCE_THRESHOLD:.0%} keyword coverage)."
    )

    return score, expl


def _score_career_consistency(
    candidate: dict,
    today: date,
) -> tuple[float, str]:
    """
    Compute career consistency score [0, 1].

    Four sub-signals
    ----------------
    1. Title progression   (0.30) — Are titles getting more senior over time?
    2. Industry consistency (0.30) — Fraction of roles in same broad domain
    3. Timeline continuity  (0.20) — Penalise large unexplained gaps
    4. Company type trajectory (0.20) — Services → product is positive; reverse is negative

    Weighted average of the four sub-signals.
    """
    career_history = candidate.get("career_history") or []

    if not career_history:
        return 0.5, "No career history — neutral consistency score."

    # ---- Sub-signal 1: Title progression ----
    # Assign seniority level to each role; sort by start_date; compute trend
    timed_levels: list[tuple[date, int]] = []
    for role in career_history:
        start = parse_date(role.get("start_date"))
        if start is None:
            continue
        level = _get_seniority_level(role.get("title", ""))
        timed_levels.append((start, level))

    timed_levels.sort(key=lambda x: x[0])

    progression_score = 0.5  # default neutral
    if len(timed_levels) >= 2:
        # Simple Spearman-like: count pairs where later role >= earlier role
        n = len(timed_levels)
        concordant = 0
        total_pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_pairs += 1
                if timed_levels[j][1] >= timed_levels[i][1]:
                    concordant += 1
        progression_score = concordant / total_pairs if total_pairs > 0 else 0.5

    # ---- Sub-signal 2: Industry consistency ----
    # "Tech product" domain: Software, SaaS, Fintech, AI/ML, etc.
    # Treat as consistent if ≥ 60% of roles are in the same broad domain
    tech_product_count = 0
    it_services_count = 0
    neutral_count = 0

    for role in career_history:
        industry = role.get("company_industry", "") or ""
        company = role.get("company", "") or ""

        if _is_negative_company(company) or industry in {"IT Services", "Consulting"}:
            it_services_count += 1
        elif industry in _PRODUCT_INDUSTRIES:
            tech_product_count += 1
        else:
            neutral_count += 1

    total_roles = max(len(career_history), 1)
    dominant_fraction = max(tech_product_count, it_services_count) / total_roles

    # Industry consistency: 1.0 if all roles in same domain, lower for mixed
    industry_consistency_score = min(dominant_fraction * 1.2, 1.0)

    # Boost for pure product, slight penalty for pure consulting
    if it_services_count == total_roles:
        industry_consistency_score *= 0.7  # consistent but in wrong direction

    # ---- Sub-signal 3: Timeline continuity (gap penalty) ----
    total_gap = career_gap_months(career_history, today)
    if total_gap == 0:
        continuity_score = 1.0
    elif total_gap <= 3:
        continuity_score = 0.90
    elif total_gap <= 6:
        continuity_score = 0.75
    elif total_gap <= 12:
        continuity_score = 0.55
    elif total_gap <= 18:
        continuity_score = 0.30
    else:
        continuity_score = 0.10

    # ---- Sub-signal 4: Company type trajectory ----
    # Positive: moved from services → product
    # Negative: moved from product → services
    trajectory_score = 0.6  # default neutral
    if len(career_history) >= 2:
        # Sort by start_date and check the first-half vs second-half industry mix
        sorted_roles = sorted(
            [r for r in career_history if parse_date(r.get("start_date"))],
            key=lambda r: parse_date(r.get("start_date")),
        )
        midpoint = len(sorted_roles) // 2
        early_roles = sorted_roles[:midpoint]
        late_roles = sorted_roles[midpoint:]

        def _is_product_role(r: dict) -> bool:
            return (
                r.get("company_industry", "") in _PRODUCT_INDUSTRIES
                and not _is_negative_company(r.get("company", ""))
            )

        early_product = sum(1 for r in early_roles if _is_product_role(r))
        late_product = sum(1 for r in late_roles if _is_product_role(r))

        early_product_frac = early_product / max(len(early_roles), 1)
        late_product_frac = late_product / max(len(late_roles), 1)

        if late_product_frac >= early_product_frac:
            # Moving toward or maintaining product companies (positive)
            trajectory_score = 0.5 + 0.5 * late_product_frac
        else:
            # Moving toward services (negative)
            trajectory_score = 0.5 * late_product_frac

    # ---- Aggregate ----
    consistency = (
        0.30 * progression_score
        + 0.30 * industry_consistency_score
        + 0.20 * continuity_score
        + 0.20 * trajectory_score
    )
    consistency = round(min(consistency, 1.0), 4)

    # Human-readable explanation
    if progression_score >= 0.7:
        prog_text = "Clear upward title progression."
    elif progression_score >= 0.4:
        prog_text = "Somewhat consistent title progression."
    else:
        prog_text = "Non-linear or declining title progression."

    gap_text = f"Total career gap: {total_gap} month(s)."

    expl = (
        f"{prog_text} "
        f"Industry consistency: {industry_consistency_score:.0%} dominant domain. "
        f"{gap_text} "
        f"Trajectory score: {trajectory_score:.2f}."
    )

    return consistency, expl


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def score_career(
    candidate: dict,
    title_taxonomy: dict,
    industry_taxonomy: dict,
    today: Optional[date] = None,
) -> CareerScoreResult:
    """
    Compute the full career relevance score for a single candidate.

    This is the single entry-point called by the feature extraction pipeline.
    All five sub-scorers run independently; results are aggregated into
    ``final_career_score`` and a single ``explanation`` string.

    Parameters
    ----------
    candidate : dict
        A single candidate record as returned by ``load_candidates()``.
        Expected keys: ``profile``, ``career_history``, ``skills``.
    title_taxonomy : dict
        Parsed contents of ``data/title_taxonomy.json``.
    industry_taxonomy : dict
        Parsed contents of ``data/industry_taxonomy.json``.
    today : date, optional
        Reference date for recency calculations.  Defaults to UTC today.
        Inject a fixed date in tests for determinism.

    Returns
    -------
    CareerScoreResult
        Frozen dataclass with individual sub-scores, final score, and explanation.

    Complexity
    ----------
    Time : O(C × D × K) per candidate
           C = career history length, D = avg description length, K = keyword count
           All bounded constants → effectively O(1) amortized per candidate.
    Memory : O(C) — proportional to career history length only.

    Notes
    -----
    This function is PURELY FUNCTIONAL — no side-effects, no global state writes,
    safe to call from multiple threads simultaneously.
    """
    ref_today: date = today or _get_today()

    # --- Run all five sub-scorers ---
    title_score, title_expl = _score_title_relevance(candidate, title_taxonomy, ref_today)
    history_score, history_expl = _score_career_history_relevance(candidate, ref_today)
    product_score, product_expl = _score_product_company(candidate, industry_taxonomy, ref_today)
    exp_score, exp_expl = _score_relevant_experience(candidate, ref_today)
    consistency_score, consistency_expl = _score_career_consistency(candidate, ref_today)

    # --- Final weighted aggregation ---
    final = (
        _CAREER_WEIGHTS["title_relevance"]          * title_score
        + _CAREER_WEIGHTS["career_history_relevance"] * history_score
        + _CAREER_WEIGHTS["product_company"]          * product_score
        + _CAREER_WEIGHTS["relevant_experience"]      * exp_score
        + _CAREER_WEIGHTS["career_consistency"]       * consistency_score
    )
    final = round(min(final, 1.0), 4)

    # --- Assemble explanation ---
    profile = candidate.get("profile") or {}
    candidate_name = profile.get("name", "Candidate")

    explanation = (
        f"{exp_expl} "
        f"{title_expl} "
        f"{product_expl} "
        f"{history_expl} "
        f"{consistency_expl} "
        f"Final career score: {final:.3f}."
    ).strip()

    return CareerScoreResult(
        title_relevance_score=title_score,
        career_history_relevance_score=history_score,
        product_company_score=product_score,
        relevant_experience_score=exp_score,
        career_consistency_score=consistency_score,
        final_career_score=final,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Convenience loader helpers (for standalone use or notebook exploration)
# ---------------------------------------------------------------------------

def load_taxonomies(
    title_taxonomy_path: Optional[str] = None,
    industry_taxonomy_path: Optional[str] = None,
) -> tuple[dict, dict]:
    """
    Load title and industry taxonomies from JSON files.

    Parameters
    ----------
    title_taxonomy_path : str, optional
        Path to title_taxonomy.json.  Defaults to data/title_taxonomy.json
        relative to project root.
    industry_taxonomy_path : str, optional
        Path to industry_taxonomy.json.

    Returns
    -------
    tuple[dict, dict]
        (title_taxonomy, industry_taxonomy)
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    data_dir = repo_root / "data"

    tp = Path(title_taxonomy_path) if title_taxonomy_path else data_dir / "title_taxonomy.json"
    ip = Path(industry_taxonomy_path) if industry_taxonomy_path else data_dir / "industry_taxonomy.json"

    with tp.open("r", encoding="utf-8") as f:
        title_taxonomy = json.load(f)

    with ip.open("r", encoding="utf-8") as f:
        industry_taxonomy = json.load(f)

    return title_taxonomy, industry_taxonomy
