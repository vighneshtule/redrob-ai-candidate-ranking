"""
src/utils/text_utils.py
=======================
Title and skill normalisation, fuzzy matching, and keyword relevance
utilities for the Redrob career scoring engine.

Design goals
------------
* Handle real-world title messiness: abbreviations, punctuation, inconsistent
  capitalisation, common aliases (Sr. → Senior, ML → Machine Learning, etc.)
* Expose fuzzy-matching via rapidfuzz (WRatio algorithm) for taxonomy lookups
  where exact-match fails on minor variations.
* keyword_relevance() is a fast, interpretable heuristic — it measures what
  fraction of weighted keywords appear in a text, without needing embeddings.

All functions are:
- Pure (no side-effects, no I/O, no global mutable state)
- Fully typed (PEP 484)
- Unit-testable in isolation

Dependencies
------------
* rapidfuzz >= 3.6.1  — already in requirements.txt

Public API
----------
    normalize_title(title)                              -> str
    normalize_skill(skill)                              -> str
    fuzzy_match(query, candidates, threshold)           -> tuple[str, float] | None
    title_similarity(a, b)                              -> float
    keyword_relevance(text, keywords, weights)          -> float
"""

from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# Title alias expansions
# Sourced from title_taxonomy.json → alias_map.normalizations
# Additional common abbreviations added from domain knowledge.
# Applied left-to-right as whole-word substitutions (word-boundary regex).
# ---------------------------------------------------------------------------

# Each entry: (pattern, replacement) — applied in order
# Word-boundary matching prevents "mlops" from becoming "machine learningops"
_TITLE_ALIASES: list[tuple[re.Pattern[str], str]] = [
    # Degree prefixes — match 'Sr.', 'Sr', 'SNR.' etc. and consume the dot
    (re.compile(r"\bsr\.(?=\s|$)", re.IGNORECASE), "senior "),   # 'Sr. ' → 'senior '
    (re.compile(r"\bsr\b",         re.IGNORECASE), "senior"),    # 'Sr ' → 'senior '
    (re.compile(r"\bsnr\.(?=\s|$)",re.IGNORECASE), "senior "),
    (re.compile(r"\bsnr\b",        re.IGNORECASE), "senior"),
    (re.compile(r"\bjr\.(?=\s|$)", re.IGNORECASE), "junior "),
    (re.compile(r"\bjr\b",         re.IGNORECASE), "junior"),

    # Domain expansions  (order matters: longer first to avoid partial match)
    (re.compile(r"\bm\.?l\.?\b",            re.IGNORECASE), "machine learning"),
    (re.compile(r"\ba\.?i\.?\b",            re.IGNORECASE), "artificial intelligence"),
    (re.compile(r"\bnlp\b",                 re.IGNORECASE), "natural language processing"),
    (re.compile(r"\bir\b",                  re.IGNORECASE), "information retrieval"),
    (re.compile(r"\bllm\b",                 re.IGNORECASE), "large language model"),
    (re.compile(r"\brag\b",                 re.IGNORECASE), "retrieval augmented generation"),

    # Title abbreviations
    (re.compile(r"\beng\.?\b",              re.IGNORECASE), "engineer"),
    (re.compile(r"\bengr\.?\b",             re.IGNORECASE), "engineer"),
    (re.compile(r"\bdev\.?\b",              re.IGNORECASE), "developer"),
    (re.compile(r"\bmgr\.?\b",              re.IGNORECASE), "manager"),
    (re.compile(r"\bspl\.?\b",              re.IGNORECASE), "specialist"),
    (re.compile(r"\bscientist\b",           re.IGNORECASE), "scientist"),

    # SDE variants → software engineer
    (re.compile(r"\bsde[-\s]?[23iii]+\b",  re.IGNORECASE), "senior software engineer"),
    (re.compile(r"\bsde\b",                 re.IGNORECASE), "software engineer"),

    # SRE → site reliability engineer
    (re.compile(r"\bsre\b",                 re.IGNORECASE), "site reliability engineer"),
]

# ---------------------------------------------------------------------------
# Skill alias expansions (common shorthand → canonical form)
# ---------------------------------------------------------------------------
_SKILL_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsbert\b",               re.IGNORECASE), "sentence transformers"),
    (re.compile(r"\bsentence[\s-]?bert\b",  re.IGNORECASE), "sentence transformers"),
    (re.compile(r"\bfaiss[-\s]?gpu\b",      re.IGNORECASE), "faiss"),
    (re.compile(r"\bfaiss[-\s]?cpu\b",      re.IGNORECASE), "faiss"),
    (re.compile(r"\belastic[\s-]?search\b", re.IGNORECASE), "elasticsearch"),
    (re.compile(r"\bopen[\s-]?search\b",    re.IGNORECASE), "opensearch"),
    (re.compile(r"\bpytorch[\s-]?lightning\b", re.IGNORECASE), "pytorch"),
    (re.compile(r"\bhugging[\s-]?face\b",   re.IGNORECASE), "huggingface"),
    (re.compile(r"\bscikit[\s-]?learn\b",   re.IGNORECASE), "scikit learn"),
    (re.compile(r"\bsklearn\b",             re.IGNORECASE), "scikit learn"),
    (re.compile(r"\btensorflow\b",          re.IGNORECASE), "tensorflow"),
    (re.compile(r"\bxgboost\b",             re.IGNORECASE), "xgboost"),
    (re.compile(r"\bltr\b",                 re.IGNORECASE), "learning to rank"),
    (re.compile(r"\bland\b",                re.IGNORECASE), "learning to rank"),  # LambdaRank
    (re.compile(r"\bpeft\b",                re.IGNORECASE), "parameter efficient fine tuning"),
    (re.compile(r"\bqlora\b",               re.IGNORECASE), "quantized lora"),
    (re.compile(r"\bndcg\b",                re.IGNORECASE), "normalized discounted cumulative gain"),
    (re.compile(r"\bmrr\b",                 re.IGNORECASE), "mean reciprocal rank"),
]

# Punctuation normaliser — collapses runs of non-alphanumeric chars to a space
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_WHITESPACE_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Public normalisation functions
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """
    Normalise a job title string for consistent taxonomy lookup.

    Operations applied (in order)
    ------------------------------
    1. Lowercase + strip
    2. Expand common abbreviations (Sr. → senior, ML → machine learning, etc.)
    3. Collapse whitespace

    The output is suitable for direct substring lookup against
    ``title_taxonomy.json`` tier lists.

    Parameters
    ----------
    title : str
        Raw title string (may contain abbreviations, punctuation, mixed case).

    Returns
    -------
    str
        Normalised title (lowercase, expanded, single-space separated).

    Examples
    --------
    >>> normalize_title('Sr. ML Engineer')
    'senior machine learning engineer'
    >>> normalize_title('  SDE-2  ')
    'senior software engineer'
    >>> normalize_title('NLP Scientist')
    'natural language processing scientist'

    Complexity: O(A × T) where A = number of alias patterns, T = title length.
    """
    if not title:
        return ""

    s = title.lower().strip()

    for pattern, replacement in _TITLE_ALIASES:
        s = pattern.sub(replacement, s)

    # Collapse whitespace
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def normalize_skill(skill: str) -> str:
    """
    Normalise a skill name for consistent taxonomy lookup and matching.

    Operations applied (in order)
    ------------------------------
    1. Lowercase + strip
    2. Expand common aliases (SBERT → sentence transformers, etc.)
    3. Remove punctuation (except spaces)
    4. Collapse whitespace

    Parameters
    ----------
    skill : str
        Raw skill name string.

    Returns
    -------
    str
        Normalised skill (lowercase, expanded, punctuation-stripped).

    Examples
    --------
    >>> normalize_skill('Sentence-BERT')
    'sentence transformers'
    >>> normalize_skill('scikit-learn')
    'scikit learn'
    >>> normalize_skill('XGBoost')
    'xgboost'

    Complexity: O(A × S) where A = alias patterns, S = skill length.
    """
    if not skill:
        return ""

    s = skill.lower().strip()

    for pattern, replacement in _SKILL_ALIASES:
        s = pattern.sub(replacement, s)

    # Remove punctuation (keep spaces and alphanumeric)
    s = _PUNCT_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def fuzzy_match(
    query: str,
    candidates: list[str],
    threshold: float = 80.0,
) -> Optional[tuple[str, float]]:
    """
    Find the best fuzzy match for *query* in *candidates* using rapidfuzz.

    Uses ``WRatio`` (weighted ratio) which handles:
    - Token order differences  ("engineer senior" ↔ "senior engineer")
    - Partial containment      ("ML Engineer" in "Senior ML Engineer")
    - Minor typos

    The *query* and all *candidates* are normalised before matching.

    Parameters
    ----------
    query : str
        The string to search for.
    candidates : list[str]
        Pool of strings to match against.
    threshold : float
        Minimum similarity score (0–100) to accept a match.  Default 80.

    Returns
    -------
    tuple[str, float] or None
        ``(best_match_string, similarity_score)`` if a match ≥ threshold
        is found, else ``None``.

    Examples
    --------
    >>> fuzzy_match("senior ml engineer", ["senior machine learning engineer"])
    ('senior machine learning engineer', ...)  # score ≥ 80

    Complexity: O(K × T) where K = len(candidates), T = max(len(query), len(candidate)).
    """
    if not query or not candidates:
        return None

    norm_query = normalize_title(query)
    norm_candidates = [normalize_title(c) for c in candidates]

    result = process.extractOne(
        norm_query,
        norm_candidates,
        scorer=fuzz.WRatio,
        score_cutoff=threshold,
    )

    if result is None:
        return None

    # result is (match, score, index)
    matched_str, score, idx = result
    # Return the original (un-normalised) candidate string for traceability
    return (candidates[idx], float(score))


def title_similarity(a: str, b: str) -> float:
    """
    Compute a normalised [0, 1] similarity score between two job title strings.

    Uses rapidfuzz ``token_sort_ratio`` after normalising both strings.
    Token-sort is robust to word-order permutations (e.g. "Engineer Senior"
    vs "Senior Engineer").

    Parameters
    ----------
    a : str
        First title.
    b : str
        Second title.

    Returns
    -------
    float
        Similarity in [0.0, 1.0].  1.0 = identical, 0.0 = completely different.

    Examples
    --------
    >>> title_similarity("Senior ML Engineer", "Senior Machine Learning Engineer")  # doctest: +SKIP
    0.86...
    >>> title_similarity("HR Manager", "Senior ML Engineer")  # doctest: +SKIP
    0.15...

    Complexity: O(max(|a|, |b|))
    """
    if not a or not b:
        return 0.0

    na = normalize_title(a)
    nb = normalize_title(b)

    score = fuzz.token_sort_ratio(na, nb)
    return round(score / 100.0, 4)


def keyword_relevance(
    text: str,
    keywords: list[str],
    weights: Optional[dict[str, float]] = None,
) -> float:
    """
    Compute a weighted keyword-coverage score for a block of text.

    For each keyword that appears as a substring of *text* (case-insensitive),
    its weight is added to the total score.  The result is normalised by the
    sum of all weights (so a perfect match returns 1.0).

    If *weights* is not provided, all keywords are weighted equally.

    Parameters
    ----------
    text : str
        The text to search (e.g. a career description or role summary).
    keywords : list[str]
        List of keywords to look for.
    weights : dict[str, float], optional
        Per-keyword importance weights.  Keys must match entries in *keywords*.
        Missing keys default to 1.0.

    Returns
    -------
    float
        Weighted coverage ratio in [0.0, 1.0].

    Examples
    --------
    >>> keyword_relevance(
    ...     "Built a ranking and retrieval system using embeddings",
    ...     ["retrieval", "ranking", "embeddings", "NLP"],
    ... )
    0.75

    Complexity: O(K × T) where K = len(keywords), T = len(text).
    """
    if not text or not keywords:
        return 0.0

    text_lower = text.lower()
    w = weights or {}

    total_weight = 0.0
    matched_weight = 0.0

    for kw in keywords:
        kw_weight = w.get(kw, 1.0)
        total_weight += kw_weight
        if kw.lower() in text_lower:
            matched_weight += kw_weight

    if total_weight == 0.0:
        return 0.0

    return round(matched_weight / total_weight, 4)
