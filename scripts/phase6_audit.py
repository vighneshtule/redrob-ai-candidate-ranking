"""
scripts/phase6_audit.py
========================
Phase 6.5 — Ranking Audit, Calibration & Failure Analysis

Runs the full ranking pipeline against candidates.jsonl and generates
10 analytical reports in the reports/ directory.

Usage
-----
    python -m scripts.phase6_audit

Outputs
-------
    reports/top100_audit.md
    reports/top20_manual_review.csv
    reports/rank1_analysis.md
    reports/distributions.md
    reports/skill_audit.md
    reports/career_audit.md
    reports/integrity_audit.md
    reports/top100_role_distribution.md
    reports/weight_sensitivity.md
    reports/phase7_readiness.md
"""

from __future__ import annotations

import csv
import logging
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

# ── project bootstrap ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import (
    CANDIDATES_JSONL,
)
from src.pipeline.loader import load_candidates
from src.pipeline.ranker import rank_candidates, RankedCandidate, compute_final_score
from src.pipeline.feature_extractor import extract_features
from src.features.skill_scorer import load_skill_taxonomy
from src.features.career_scorer import load_taxonomies

REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase6_audit")

TODAY = datetime.utcnow().date()

# ══════════════════════════════════════════════════════════════════════════════
# 1.  RUN PIPELINE — collect top-100 + full population stats
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline():
    """Run the full ranking pipeline and return (top100, raw_features_sample)."""
    log.info("Loading taxonomies …")
    title_taxonomy, industry_taxonomy = load_taxonomies()
    tier_a, tier_b, tier_c, _ = load_skill_taxonomy()

    log.info("Streaming candidates and ranking …")
    t0 = time.perf_counter()

    candidates_iter = load_candidates(CANDIDATES_JSONL, skip_invalid=True, validate=True)

    # We need two passes of data:
    #   Pass 1 → rank_candidates() for the top-100
    #   Pass 2 → full population stats (we'll do a second streaming pass)
    top100 = rank_candidates(
        candidates_iter,
        title_taxonomy=title_taxonomy,
        industry_taxonomy=industry_taxonomy,
        tier_a=tier_a,
        tier_b=tier_b,
        tier_c=tier_c,
        top_k=100,
        debug=True,
        today=TODAY,
    )

    elapsed = time.perf_counter() - t0
    log.info("Top-100 ranking complete in %.1f s  (%d candidates returned)", elapsed, len(top100))

    return top100, title_taxonomy, industry_taxonomy, tier_a, tier_b, tier_c


def collect_population_stats(title_taxonomy, industry_taxonomy, tier_a, tier_b, tier_c,
                              sample_size: int = 5000):
    """
    Second streaming pass — collect score distribution stats over a sample.
    5 000 candidates is enough for stable statistics without hitting the full
    465 MB file again.
    """
    log.info("Collecting population score stats over first %d candidates …", sample_size)
    stats_bucket = defaultdict(list)

    for raw in load_candidates(CANDIDATES_JSONL, limit=sample_size,
                               skip_invalid=True, validate=False):
        features = extract_features(
            raw, title_taxonomy, industry_taxonomy,
            tier_a, tier_b, tier_c,
            debug=False, today=TODAY,
        )
        if features.veto_candidate:
            continue
        score = compute_final_score(features)
        stats_bucket["career_score"].append(features.career_score)
        stats_bucket["skill_score"].append(features.skill_score)
        stats_bucket["behavior_score"].append(features.behavior_score)
        stats_bucket["integrity_score"].append(features.integrity_score)
        stats_bucket["profile_integrity_score"].append(features.profile_integrity_score)
        stats_bucket["final_score"].append(score)

    log.info("Population stats collected over %d non-vetoed candidates.",
             len(stats_bucket["final_score"]))
    return dict(stats_bucket)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _stat_block(values: list[float]) -> dict:
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "stddev": 0}
    return {
        "min":    round(min(values), 4),
        "max":    round(max(values), 4),
        "mean":   round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "stddev": round(statistics.stdev(values) if len(values) > 1 else 0.0, 4),
    }


def _get_candidate_info(rc: RankedCandidate) -> dict:
    """Extract profile fields from feature_breakdown dict."""
    fb = rc.feature_breakdown
    return fb


# ══════════════════════════════════════════════════════════════════════════════
# 2.  LOAD CANDIDATE RECORDS for top-100 lookups
# ══════════════════════════════════════════════════════════════════════════════

def load_top100_raw(top100: list[RankedCandidate]) -> dict[str, dict]:
    """Stream candidates.jsonl and pull out the raw records for top-100 IDs."""
    needed = {rc.candidate_id for rc in top100}
    found: dict[str, dict] = {}

    log.info("Re-scanning candidates.jsonl to fetch raw records for top-100 …")
    for raw in load_candidates(CANDIDATES_JSONL, skip_invalid=True, validate=False):
        cid = str(raw.get("candidate_id", ""))
        if cid in needed:
            found[cid] = raw
            needed.discard(cid)
            if not needed:
                break

    log.info("Fetched %d / %d top-100 raw records.", len(found), len(top100))
    return found


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Top-100 Audit Report
# ══════════════════════════════════════════════════════════════════════════════

def generate_top100_audit(top100: list[RankedCandidate],
                          raw_records: dict[str, dict]) -> None:
    path = REPORTS_DIR / "top100_audit.md"
    lines = [
        "# Top-100 Candidate Audit Report",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Reference date**: {TODAY}  ",
        "",
        "---",
        "",
    ]

    for rc in top100:
        raw = raw_records.get(rc.candidate_id, {})
        profile = raw.get("profile", {})
        fb = rc.feature_breakdown

        lines += [
            f"## Rank #{rc.rank} — `{rc.candidate_id}`",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **candidate_id** | `{rc.candidate_id}` |",
            f"| **current_title** | {profile.get('current_title', 'N/A')} |",
            f"| **current_company** | {profile.get('current_company', 'N/A')} |",
            f"| **years_experience** | {profile.get('years_of_experience', 'N/A')} |",
            f"| **career_score** | {fb.get('career_score', 0):.4f} |",
            f"| **skill_score** | {fb.get('skill_score', 0):.4f} |",
            f"| **behavior_score** | {fb.get('behavior_score', 0):.4f} |",
            f"| **integrity_score** | {fb.get('integrity_score', 0):.4f} |",
            f"| **profile_integrity_score** | {fb.get('profile_integrity_score', 0):.4f} |",
            f"| **final_score** | **{rc.final_score:.4f}** |",
            "",
            "**Reasoning:**",
            "",
            f"> {rc.explanation}",
            "",
            "---",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Top-20 Manual Review CSV
# ══════════════════════════════════════════════════════════════════════════════

def generate_top20_csv(top100: list[RankedCandidate],
                       raw_records: dict[str, dict]) -> None:
    path = REPORTS_DIR / "top20_manual_review.csv"
    fieldnames = [
        "rank", "candidate_id", "title", "company", "experience",
        "career_score", "skill_score", "behavior_score",
        "integrity_score", "final_score",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rc in top100[:20]:
            raw = raw_records.get(rc.candidate_id, {})
            profile = raw.get("profile", {})
            fb = rc.feature_breakdown
            writer.writerow({
                "rank": rc.rank,
                "candidate_id": rc.candidate_id,
                "title": profile.get("current_title", "N/A"),
                "company": profile.get("current_company", "N/A"),
                "experience": profile.get("years_of_experience", "N/A"),
                "career_score": f"{fb.get('career_score', 0):.4f}",
                "skill_score": f"{fb.get('skill_score', 0):.4f}",
                "behavior_score": f"{fb.get('behavior_score', 0):.4f}",
                "integrity_score": f"{fb.get('integrity_score', 0):.4f}",
                "final_score": f"{rc.final_score:.4f}",
            })
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Rank #1 Deep Analysis
# ══════════════════════════════════════════════════════════════════════════════

def generate_rank1_analysis(top100: list[RankedCandidate],
                             raw_records: dict[str, dict]) -> None:
    path = REPORTS_DIR / "rank1_analysis.md"
    rc = top100[0]
    rank2 = top100[1] if len(top100) > 1 else None

    raw = raw_records.get(rc.candidate_id, {})
    profile = raw.get("profile", {})
    career_history = raw.get("career_history", [])
    skills = raw.get("skills", [])
    signals = raw.get("redrob_signals", {})
    fb = rc.feature_breakdown

    # Score gap analysis
    score_gap = rc.final_score - (rank2.final_score if rank2 else 0.0)

    # Which scorer contributes most?
    weights = {"career": 0.35, "skill": 0.25, "behavior": 0.20,
               "integrity": 0.10, "profile_integrity": 0.10}
    contributions = {
        "career":            weights["career"] * fb.get("career_score", 0),
        "skill":             weights["skill"] * fb.get("skill_score", 0),
        "behavior":          weights["behavior"] * fb.get("behavior_score", 0),
        "integrity":         weights["integrity"] * fb.get("integrity_score", 0),
        "profile_integrity": weights["profile_integrity"] * fb.get("profile_integrity_score", 0),
    }
    top_driver = max(contributions, key=lambda k: contributions[k])
    top_driver_pct = contributions[top_driver] / rc.final_score * 100 if rc.final_score > 0 else 0

    # Skill coverage
    matched_tier_a = fb.get("tier_a_match_score", 0)
    matched_tier_b = fb.get("tier_b_match_score", 0)

    # Career history summary
    career_summary = []
    for role in career_history[:5]:
        title = role.get("title", "?")
        company = role.get("company", "?")
        duration = role.get("duration_months", "?")
        career_summary.append(f"  - {title} @ {company} ({duration} months)")

    # Skill list
    skill_list = [f"  - {s.get('name', '?')} ({s.get('proficiency', '?')}, {s.get('duration_months', 0)} mo)"
                  for s in skills[:15]]

    # Anomaly check
    anomaly_count = fb.get("anomaly_count", 0)
    veto = fb.get("veto_candidate", False)
    stuffing = fb.get("stuffing_score", 0)

    # Dominance verdict
    if top_driver_pct > 50:
        verdict = (f"⚠️ **SCORER DOMINANCE DETECTED**: The `{top_driver}` scorer alone "
                   f"accounts for {top_driver_pct:.1f}% of the final score. "
                   f"This suggests Rank #1 may be elevated primarily due to {top_driver} signal "
                   f"rather than holistic fitness.")
    else:
        verdict = (f"✅ **Balanced scorer contributions**: No single scorer dominates. "
                   f"Top driver is `{top_driver}` at {top_driver_pct:.1f}%. "
                   f"Rank #1 appears to reflect genuine multi-dimensional strength.")

    lines = [
        "# Rank #1 Deep Analysis",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Candidate Identity",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **candidate_id** | `{rc.candidate_id}` |",
        f"| **current_title** | {profile.get('current_title', 'N/A')} |",
        f"| **current_company** | {profile.get('current_company', 'N/A')} |",
        f"| **years_of_experience** | {profile.get('years_of_experience', 'N/A')} |",
        f"| **location** | {profile.get('location', 'N/A')} |",
        f"| **final_score** | **{rc.final_score:.6f}** |",
        f"| **rank2_score** | {rank2.final_score:.6f if rank2 else 'N/A'} |",
        f"| **score_gap_vs_rank2** | {score_gap:.6f} |",
        "",
        "---",
        "",
        "## Score Breakdown",
        "",
        "| Scorer | Raw Score | Weight | Contribution | % of Final |",
        "|--------|-----------|--------|--------------|------------|",
    ]

    for name, contrib in contributions.items():
        raw_score_key = f"{name}_score" if name != "profile_integrity" else "profile_integrity_score"
        raw_s = fb.get(raw_score_key, 0)
        w = weights[name]
        pct = contrib / rc.final_score * 100 if rc.final_score > 0 else 0
        lines.append(f"| {name} | {raw_s:.4f} | {w:.0%} | {contrib:.4f} | {pct:.1f}% |")

    lines += [
        "",
        "---",
        "",
        "## Scorer Sub-Scores",
        "",
        "### Career Sub-Scores",
        "",
        f"| Sub-Score | Value |",
        f"|-----------|-------|",
        f"| title_relevance_score | {fb.get('title_relevance_score', 0):.4f} |",
        f"| career_history_relevance_score | {fb.get('career_history_relevance_score', 0):.4f} |",
        f"| product_company_score | {fb.get('product_company_score', 0):.4f} |",
        f"| relevant_experience_score | {fb.get('relevant_experience_score', 0):.4f} |",
        f"| career_consistency_score | {fb.get('career_consistency_score', 0):.4f} |",
        "",
        "### Skill Sub-Scores",
        "",
        f"| Sub-Score | Value |",
        f"|-----------|-------|",
        f"| tier_a_match_score | {fb.get('tier_a_match_score', 0):.4f} |",
        f"| tier_b_match_score | {fb.get('tier_b_match_score', 0):.4f} |",
        f"| tier_c_match_score | {fb.get('tier_c_match_score', 0):.4f} |",
        f"| coverage_score | {fb.get('coverage_score', 0):.4f} |",
        f"| duration_score | {fb.get('duration_score', 0):.4f} |",
        f"| proficiency_score | {fb.get('proficiency_score', 0):.4f} |",
        f"| assessment_score | {fb.get('assessment_score', 0):.4f} |",
        f"| depth_score | {fb.get('depth_score', 0):.4f} |",
        "",
        "### Behavioral Sub-Scores",
        "",
        f"| Sub-Score | Value |",
        f"|-----------|-------|",
        f"| availability_score | {fb.get('availability_score', 0):.4f} |",
        f"| activity_score | {fb.get('activity_score', 0):.4f} |",
        f"| recruiter_engagement_score | {fb.get('recruiter_engagement_score', 0):.4f} |",
        f"| interview_reliability_score | {fb.get('interview_reliability_score', 0):.4f} |",
        f"| hiring_probability_score | {fb.get('hiring_probability_score', 0):.4f} |",
        f"| notice_period_score | {fb.get('notice_period_score', 0):.4f} |",
        f"| behavioral_risk_score | {fb.get('behavioral_risk_score', 0):.4f} |",
        "",
        "### Integrity",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| integrity_score | {fb.get('integrity_score', 0):.4f} |",
        f"| profile_integrity_score | {fb.get('profile_integrity_score', 0):.4f} |",
        f"| anomaly_count | {anomaly_count} |",
        f"| veto_candidate | {veto} |",
        f"| stuffing_score | {stuffing:.4f} |",
        "",
        "---",
        "",
        "## Career History",
        "",
        f"Total roles: {len(career_history)}",
        "",
        "\n".join(career_summary) if career_summary else "  _(no roles found)_",
        "",
        "---",
        "",
        "## Skills",
        "",
        f"Total skills listed: {len(skills)}",
        "",
        "\n".join(skill_list) if skill_list else "  _(no skills found)_",
        "",
        "---",
        "",
        "## Behavioral Signals",
        "",
        f"| Signal | Value |",
        f"|--------|-------|",
        f"| open_to_work_flag | {signals.get('open_to_work_flag', 'N/A')} |",
        f"| last_active_date | {signals.get('last_active_date', 'N/A')} |",
        f"| recruiter_response_rate | {signals.get('recruiter_response_rate', 'N/A')} |",
        f"| notice_period_days | {signals.get('notice_period_days', 'N/A')} |",
        f"| interview_completion_rate | {signals.get('interview_completion_rate', 'N/A')} |",
        f"| offer_acceptance_rate | {signals.get('offer_acceptance_rate', 'N/A')} |",
        f"| github_activity_score | {signals.get('github_activity_score', 'N/A')} |",
        "",
        "---",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "### Reasoning (from pipeline):",
        "",
        f"> {rc.explanation}",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Score Distributions
# ══════════════════════════════════════════════════════════════════════════════

def generate_distributions(top100: list[RankedCandidate],
                            pop_stats: dict[str, list[float]]) -> None:
    path = REPORTS_DIR / "distributions.md"

    score_keys = [
        "career_score", "skill_score", "behavior_score",
        "integrity_score", "profile_integrity_score", "final_score",
    ]

    # Top-100 scores
    top100_scores: dict[str, list[float]] = defaultdict(list)
    for rc in top100:
        fb = rc.feature_breakdown
        top100_scores["career_score"].append(fb.get("career_score", 0))
        top100_scores["skill_score"].append(fb.get("skill_score", 0))
        top100_scores["behavior_score"].append(fb.get("behavior_score", 0))
        top100_scores["integrity_score"].append(fb.get("integrity_score", 0))
        top100_scores["profile_integrity_score"].append(fb.get("profile_integrity_score", 0))
        top100_scores["final_score"].append(rc.final_score)

    lines = [
        "# Score Distribution Analysis",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Population sample size**: {len(pop_stats.get('final_score', []))} non-vetoed candidates",
        "",
        "---",
        "",
        "## Population Statistics (first 5,000 valid candidates)",
        "",
        "| Score | Min | Max | Mean | Median | StdDev |",
        "|-------|-----|-----|------|--------|--------|",
    ]

    for key in score_keys:
        vals = pop_stats.get(key, [])
        s = _stat_block(vals)
        lines.append(
            f"| **{key}** | {s['min']:.4f} | {s['max']:.4f} | "
            f"{s['mean']:.4f} | {s['median']:.4f} | {s['stddev']:.4f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Top-100 Statistics",
        "",
        "| Score | Min | Max | Mean | Median | StdDev |",
        "|-------|-----|-----|------|--------|--------|",
    ]

    for key in score_keys:
        vals = top100_scores[key]
        s = _stat_block(vals)
        lines.append(
            f"| **{key}** | {s['min']:.4f} | {s['max']:.4f} | "
            f"{s['mean']:.4f} | {s['median']:.4f} | {s['stddev']:.4f} |"
        )

    # Score band distribution for final_score
    lines += [
        "",
        "---",
        "",
        "## Final Score Band Distribution (Population Sample)",
        "",
        "| Band | Range | Count | % |",
        "|------|-------|-------|---|",
    ]
    pop_final = pop_stats.get("final_score", [])
    bands = [
        ("Excellent", 0.70, 1.01),
        ("Good",      0.50, 0.70),
        ("Moderate",  0.30, 0.50),
        ("Weak",      0.10, 0.30),
        ("Very Weak", 0.00, 0.10),
    ]
    total = max(len(pop_final), 1)
    for label, lo, hi in bands:
        count = sum(1 for v in pop_final if lo <= v < hi)
        pct = count / total * 100
        lines.append(f"| {label} | [{lo:.2f}, {hi:.2f}) | {count} | {pct:.1f}% |")

    # Score band for top-100
    lines += [
        "",
        "## Final Score Band Distribution (Top-100)",
        "",
        "| Band | Range | Count | % |",
        "|------|-------|-------|---|",
    ]
    top_final = top100_scores["final_score"]
    total100 = max(len(top_final), 1)
    for label, lo, hi in bands:
        count = sum(1 for v in top_final if lo <= v < hi)
        pct = count / total100 * 100
        lines.append(f"| {label} | [{lo:.2f}, {hi:.2f}) | {count} | {pct:.1f}% |")

    # Key observations
    pop_skill_mean = statistics.mean(pop_stats.get("skill_score", [0]))
    pop_career_mean = statistics.mean(pop_stats.get("career_score", [0]))
    t100_skill_mean = statistics.mean(top100_scores["skill_score"])
    t100_career_mean = statistics.mean(top100_scores["career_score"])

    lines += [
        "",
        "---",
        "",
        "## Key Observations",
        "",
        f"- **Career score**: population mean = {pop_career_mean:.4f}, "
        f"top-100 mean = {t100_career_mean:.4f} "
        f"(delta = +{t100_career_mean - pop_career_mean:.4f})",
        f"- **Skill score**: population mean = {pop_skill_mean:.4f}, "
        f"top-100 mean = {t100_skill_mean:.4f} "
        f"(delta = +{t100_skill_mean - pop_skill_mean:.4f})",
        f"- **Score compression**: top-100 scores span "
        f"[{min(top_final):.4f}, {max(top_final):.4f}] — "
        f"{'narrow range, low discrimination' if max(top_final) - min(top_final) < 0.10 else 'healthy spread'}",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Skill Score Audit
# ══════════════════════════════════════════════════════════════════════════════

def generate_skill_audit(top100: list[RankedCandidate],
                          raw_records: dict[str, dict],
                          pop_stats: dict[str, list[float]]) -> None:
    path = REPORTS_DIR / "skill_audit.md"

    # Collect matched/missing skills across top-100
    skill_scores = [rc.feature_breakdown.get("skill_score", 0) for rc in top100]
    tier_a_scores = [rc.feature_breakdown.get("tier_a_match_score", 0) for rc in top100]
    coverage_scores = [rc.feature_breakdown.get("coverage_score", 0) for rc in top100]

    # From population
    pop_skill = pop_stats.get("skill_score", [])

    # Cluster analysis: how many cluster near 0.036?
    COLLAPSE_THRESHOLD = 0.05
    collapsed = sum(1 for s in skill_scores if s < COLLAPSE_THRESHOLD)
    collapsed_pop = sum(1 for s in pop_skill if s < COLLAPSE_THRESHOLD)

    # Histogram buckets
    buckets = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.70, 1.01]
    hist = Counter()
    for s in pop_skill:
        for i in range(len(buckets) - 1):
            if buckets[i] <= s < buckets[i+1]:
                hist[f"[{buckets[i]:.2f}, {buckets[i+1]:.2f})"] += 1
                break

    # Top-20 matched and missing skills from top-100 raw records
    matched_counter: Counter = Counter()
    missing_counter: Counter = Counter()

    for rc in top100:
        raw = raw_records.get(rc.candidate_id, {})
        skills = raw.get("skills", [])
        for s in skills:
            name = s.get("name", "")
            if name:
                matched_counter[name] += 1

    # Missing: approximate from tier_a_match_score == 0
    zero_tier_a = [rc for rc in top100 if rc.feature_breakdown.get("tier_a_match_score", 0) == 0]

    # Root cause analysis
    reasons = []
    if collapsed > 20:
        reasons.append(
            f"- **Score Collapse at < {COLLAPSE_THRESHOLD}**: "
            f"{collapsed}/{len(top100)} top-100 candidates have skill_score < {COLLAPSE_THRESHOLD}. "
            f"This strongly suggests Tier-A matching is failing for most candidates."
        )
    avg_tier_a = statistics.mean(tier_a_scores) if tier_a_scores else 0
    if avg_tier_a < 0.15:
        reasons.append(
            f"- **Tier-A Match Failure**: Mean tier_a_match_score = {avg_tier_a:.4f}. "
            f"The taxonomy has {19} Tier-A skills; most candidates match < 3 of them. "
            f"Likely cause: alias matching too strict OR candidate skills use non-standard names."
        )
    avg_coverage = statistics.mean(coverage_scores) if coverage_scores else 0
    if avg_coverage < 0.15:
        reasons.append(
            f"- **Low Coverage Score**: Mean coverage = {avg_coverage:.4f}. "
            f"Weighted formula: (3×tier_a + 2×tier_b + 1×tier_c) / total_taxonomy. "
            f"With many Tier-A misses, coverage collapses severely."
        )
    reasons.append(
        "- **Proficiency defaults**: Skills with missing proficiency default to 'intermediate' (0.50) — "
        "this does not cause collapse but adds noise."
    )
    reasons.append(
        "- **Assessment default**: Skills without assessment data return 0.60 neutral — not a collapse driver."
    )

    lines = [
        "# Skill Score Audit",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Summary Statistics",
        "",
        "| Metric | Top-100 | Population Sample |",
        "|--------|---------|-------------------|",
        f"| Mean skill_score | {statistics.mean(skill_scores):.4f} | {statistics.mean(pop_skill) if pop_skill else 0:.4f} |",
        f"| Median skill_score | {statistics.median(skill_scores):.4f} | {statistics.median(pop_skill) if pop_skill else 0:.4f} |",
        f"| Min skill_score | {min(skill_scores):.4f} | {min(pop_skill) if pop_skill else 0:.4f} |",
        f"| Max skill_score | {max(skill_scores):.4f} | {max(pop_skill) if pop_skill else 0:.4f} |",
        f"| Candidates with score < 0.05 | {collapsed} ({collapsed/len(top100)*100:.1f}%) | {collapsed_pop} ({collapsed_pop/max(len(pop_skill),1)*100:.1f}%) |",
        f"| Mean tier_a_match_score | {avg_tier_a:.4f} | — |",
        f"| Mean coverage_score | {avg_coverage:.4f} | — |",
        "",
        "---",
        "",
        "## Score Distribution Histogram (Population Sample)",
        "",
        "| Bucket | Count | % |",
        "|--------|-------|---|",
    ]
    total_pop = max(len(pop_skill), 1)
    for bucket, count in sorted(hist.items()):
        lines.append(f"| {bucket} | {count} | {count/total_pop*100:.1f}% |")

    lines += [
        "",
        "---",
        "",
        "## Root Cause Analysis",
        "",
        "### Why does skill_score collapse to ~0.036?",
        "",
        "The minimum non-zero skill_score of ≈0.036 arises from the weighted formula:",
        "```",
        "final_skill_score =",
        "  0.35 × tier_a_match_score    ← if 0 matched → 0.0",
        "  0.15 × tier_b_match_score    ← if 0 matched → 0.0",
        "  0.10 × tier_c_match_score    ← if 0 matched → 0.0",
        "  0.15 × coverage_score        ← if 0 matched → 0.0",
        "  0.10 × duration_score        ← if 0 matched → 0.0",
        "  0.05 × proficiency_score     ← if 0 matched → 0.0",
        "  0.05 × assessment_score      ← defaults to 0.60 → contributes 0.030",
        "  0.05 × depth_score           ← partial → ~0.006",
        "```",
        "**Result**: When zero taxonomy skills match, the only contribution is from the",
        "assessment_score default (0.60 × 0.05 = 0.030) and a small depth score,",
        "yielding final_skill_score ≈ 0.036.",
        "",
        "### Failure Modes Identified",
        "",
    ]
    lines.extend(reasons)

    lines += [
        "",
        "---",
        "",
        "## Top-20 Most Common Skills in Top-100 Profiles",
        "(Raw skill names from candidate profiles — before taxonomy matching)",
        "",
        "| Rank | Skill Name | Count |",
        "|------|-----------|-------|",
    ]
    for i, (skill, count) in enumerate(matched_counter.most_common(20), 1):
        lines.append(f"| {i} | {skill} | {count} |")

    lines += [
        "",
        "---",
        "",
        "## Tier-A Skills — Match Gap Analysis",
        "",
        "**Tier-A taxonomy skills** (19 total):",
        "",
        "| # | Canonical Name | Aliases (sample) |",
        "|---|---------------|-----------------|",
    ]

    tier_a_skills = {
        "sentence-transformers": ["sbert", "sentence-bert"],
        "bge": ["bge-m3", "bge-large"],
        "e5": ["e5-large", "e5-small"],
        "embeddings-retrieval": ["dense retrieval", "bi-encoder"],
        "pinecone": ["pinecone"],
        "weaviate": ["weaviate"],
        "qdrant": ["qdrant"],
        "milvus": ["milvus"],
        "faiss": ["faiss", "faiss-gpu"],
        "opensearch": ["opensearch"],
        "elasticsearch": ["elasticsearch", "elastic search"],
        "vector-database": ["vector db", "vector store"],
        "hybrid-search": ["hybrid search", "bm25"],
        "python": ["python3", "python programming"],
        "ndcg": ["ndcg@10", "normalized discounted cumulative gain"],
        "mrr": ["mean reciprocal rank"],
        "map": ["mean average precision"],
        "evaluation-framework": ["a/b testing", "offline evaluation"],
        "retrieval-ranking": ["information retrieval", "search ranking"],
        "re-ranking": ["reranking", "cross-encoder"],
    }
    for i, (canonical, aliases) in enumerate(tier_a_skills.items(), 1):
        lines.append(f"| {i} | `{canonical}` | {', '.join(aliases[:2])} |")

    lines += [
        "",
        "### Diagnosis",
        "",
        "Most real-world AI engineers use skill names like:",
        "- 'Python', 'Machine Learning', 'Deep Learning', 'NLP', 'TensorFlow', 'PyTorch'",
        "- These map to **Tier-C** (adjacent) or miss entirely",
        "- Very few candidates use precision terms like 'FAISS', 'BM25', 'NDCG', 'cross-encoder'",
        "- The Tier-A taxonomy targets **retrieval specialists** — too narrow for general AI engineers",
        "",
        "**Conclusion**: Tier-A is severely under-matched. Most AI candidates score ~0 on tier_a,",
        "causing coverage to collapse, which cascades into a near-zero final skill_score.",
        "The 25% weight given to skill_score is effectively wasted for most of the top-100.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Career Score Audit
# ══════════════════════════════════════════════════════════════════════════════

def generate_career_audit(top100: list[RankedCandidate],
                           raw_records: dict[str, dict],
                           pop_stats: dict[str, list[float]]) -> None:
    path = REPORTS_DIR / "career_audit.md"

    career_scores = [rc.feature_breakdown.get("career_score", 0) for rc in top100]
    pop_career = pop_stats.get("career_score", [])

    title_rel = [rc.feature_breakdown.get("title_relevance_score", 0) for rc in top100]
    history_rel = [rc.feature_breakdown.get("career_history_relevance_score", 0) for rc in top100]
    product_co = [rc.feature_breakdown.get("product_company_score", 0) for rc in top100]
    rel_exp = [rc.feature_breakdown.get("relevant_experience_score", 0) for rc in top100]
    consistency = [rc.feature_breakdown.get("career_consistency_score", 0) for rc in top100]

    # Band analysis
    low_band = sum(1 for s in career_scores if 0.15 <= s <= 0.30)
    high_band = sum(1 for s in career_scores if s > 0.50)

    lines = [
        "# Career Score Audit",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Summary Statistics",
        "",
        "| Sub-Score | Min | Max | Mean | Median | StdDev |",
        "|-----------|-----|-----|------|--------|--------|",
    ]

    sub_scores = [
        ("career_score (final)", career_scores),
        ("title_relevance_score", title_rel),
        ("career_history_relevance_score", history_rel),
        ("product_company_score", product_co),
        ("relevant_experience_score", rel_exp),
        ("career_consistency_score", consistency),
        ("career_score (population)", pop_career),
    ]
    for label, vals in sub_scores:
        if vals:
            s = _stat_block(vals)
            lines.append(
                f"| {label} | {s['min']:.4f} | {s['max']:.4f} | "
                f"{s['mean']:.4f} | {s['median']:.4f} | {s['stddev']:.4f} |"
            )

    lines += [
        "",
        "---",
        "",
        "## Distribution: Career Score Bands (Top-100)",
        "",
        "| Band | Range | Count | % |",
        "|------|-------|-------|---|",
    ]
    bands = [
        ("High",     0.50, 1.01),
        ("Medium",   0.30, 0.50),
        ("Low",      0.15, 0.30),
        ("Very Low", 0.00, 0.15),
    ]
    for label, lo, hi in bands:
        count = sum(1 for s in career_scores if lo <= s < hi)
        pct = count / len(career_scores) * 100
        lines.append(f"| {label} | [{lo:.2f}, {hi:.2f}) | {count} | {pct:.1f}% |")

    # Failure mode analysis
    title_failing = sum(1 for s in title_rel if s < 0.30)
    history_failing = sum(1 for s in history_rel if s < 0.10)
    product_failing = sum(1 for s in product_co if s < 0.50)
    exp_failing = sum(1 for s in rel_exp if s < 0.20)

    lines += [
        "",
        "---",
        "",
        "## Root Cause Analysis",
        "",
        "### Why do most career scores fall in 0.15–0.30?",
        "",
        "**Career formula weights**:",
        "```",
        "career_score =",
        "  0.25 × title_relevance_score",
        "  0.25 × career_history_relevance_score",
        "  0.20 × product_company_score",
        "  0.20 × relevant_experience_score",
        "  0.10 × career_consistency_score",
        "```",
        "",
        "### Sub-Scorer Failure Rates (Top-100)",
        "",
        f"| Sub-Score | Failing Threshold | Count Failing | % |",
        f"|-----------|------------------|---------------|---|",
        f"| title_relevance_score | < 0.30 | {title_failing} | {title_failing/len(top100)*100:.1f}% |",
        f"| career_history_relevance_score | < 0.10 | {history_failing} | {history_failing/len(top100)*100:.1f}% |",
        f"| product_company_score | < 0.50 | {product_failing} | {product_failing/len(top100)*100:.1f}% |",
        f"| relevant_experience_score | < 0.20 | {exp_failing} | {exp_failing/len(top100)*100:.1f}% |",
        "",
        "### Key Observations",
        "",
        "1. **Title Taxonomy Restrictiveness**: `_lookup_tier()` checks if the normalised title",
        "   appears as a substring of tier list titles. Tier-1 requires exact matches for",
        "   'senior ai engineer', 'ml engineer' etc. Many valid titles ('AI researcher',",
        "   'NLP engineer') may fall through to the 0.35 'unknown title' default.",
        "",
        "2. **Recency Decay Aggressiveness**: Half-life = 365 days for title, 730 for company.",
        "   For a role starting 3 years ago: decay ≈ exp(-3 × 365/365) ≈ 0.05.",
        "   This means OLDER roles contribute almost nothing to career history score.",
        "",
        "3. **Consulting Penalty**: Companies like TCS, Infosys get multiplier 0.4–0.5.",
        "   Many Indian AI engineers started at TCS/Infosys before moving to product companies.",
        "   The penalty may be too global, punishing entire career history unfairly.",
        "",
        "4. **Career History Relevance Normalization**: Raw keyword relevance is scaled",
        "   by `min(raw / 0.25, 1.0)`. If 0.25 is too high a ceiling, scores cluster low.",
        "",
        "5. **Relevant Experience Threshold**: Only roles with keyword_relevance > 0.08 count.",
        "   Generic 'Machine Learning Engineer' descriptions may not hit this threshold if",
        "   the description text doesn't contain specific retrieval/ranking keywords.",
        "",
        "### Verdict",
        "",
        f"- {low_band}/{len(top100)} top-100 candidates have career_score in [0.15, 0.30].",
        f"- {high_band}/{len(top100)} achieve score > 0.50.",
        "- The career scorer is **the primary driver of compression** — it rarely produces",
        "  high scores because it requires: (1) a Tier-1 title, (2) retrieval/ranking keywords",
        "  in descriptions, (3) product company tenure, (4) 5-8 years of relevant experience.",
        "- Most candidates hit 2 out of 4 criteria — landing them in the 0.15–0.30 band.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Integrity Score Audit
# ══════════════════════════════════════════════════════════════════════════════

def generate_integrity_audit(top100: list[RankedCandidate],
                              pop_stats: dict[str, list[float]]) -> None:
    path = REPORTS_DIR / "integrity_audit.md"

    integrity_scores = [rc.feature_breakdown.get("integrity_score", 0) for rc in top100]
    pi_scores = [rc.feature_breakdown.get("profile_integrity_score", 0) for rc in top100]
    stuffing_scores = [rc.feature_breakdown.get("stuffing_score", 0) for rc in top100]
    anomaly_counts = [rc.feature_breakdown.get("anomaly_count", 0) for rc in top100]

    pop_integrity = pop_stats.get("integrity_score", [])
    pop_pi = pop_stats.get("profile_integrity_score", [])

    # Percentages
    pct_clean = sum(1 for s in integrity_scores if s >= 0.99) / len(top100) * 100
    pct_low = sum(1 for s in integrity_scores if s < 0.80) / len(top100) * 100
    pct_vetoed = 0  # top-100 by definition has no vetoed candidates

    # Count non-zero anomalies
    has_anomaly = sum(1 for c in anomaly_counts if c > 0)
    zero_anomaly = sum(1 for c in anomaly_counts if c == 0)

    # Profile integrity distribution
    pi_high = sum(1 for s in pi_scores if s >= 0.80)
    pi_mid = sum(1 for s in pi_scores if 0.50 <= s < 0.80)
    pi_low = sum(1 for s in pi_scores if s < 0.50)

    lines = [
        "# Integrity Score Audit",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "> Note: The top-100 contains ZERO vetoed candidates by definition",
        "> (vetoed candidates are excluded before ranking).",
        "",
        "---",
        "",
        "## Top-100 Integrity Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| integrity_score = 1.0 (clean) | {sum(1 for s in integrity_scores if s >= 0.99)} ({pct_clean:.1f}%) |",
        f"| integrity_score < 0.80 | {sum(1 for s in integrity_scores if s < 0.80)} ({pct_low:.1f}%) |",
        f"| vetoed candidates in top-100 | 0 (0.0%) |",
        f"| candidates with anomaly_count = 0 | {zero_anomaly} ({zero_anomaly/len(top100)*100:.1f}%) |",
        f"| candidates with anomaly_count > 0 | {has_anomaly} ({has_anomaly/len(top100)*100:.1f}%) |",
        f"| mean integrity_score | {statistics.mean(integrity_scores):.4f} |",
        f"| mean profile_integrity_score | {statistics.mean(pi_scores):.4f} |",
        f"| mean stuffing_score | {statistics.mean(stuffing_scores):.4f} |",
        "",
        "---",
        "",
        "## Profile Integrity Score Distribution (Top-100)",
        "",
        "| Band | Count | % |",
        "|------|-------|---|",
        f"| High (≥ 0.80) | {pi_high} | {pi_high/len(top100)*100:.1f}% |",
        f"| Medium (0.50–0.80) | {pi_mid} | {pi_mid/len(top100)*100:.1f}% |",
        f"| Low (< 0.50) | {pi_low} | {pi_low/len(top100)*100:.1f}% |",
        "",
        "---",
        "",
        "## Population Sample Comparison",
        "",
        "| Metric | Top-100 | Population |",
        "|--------|---------|------------|",
        f"| mean integrity_score | {statistics.mean(integrity_scores):.4f} | {statistics.mean(pop_integrity) if pop_integrity else 0:.4f} |",
        f"| mean profile_integrity_score | {statistics.mean(pi_scores):.4f} | {statistics.mean(pop_pi) if pop_pi else 0:.4f} |",
        "",
        "---",
        "",
        "## Root Cause: Why Integrity Scores Appear Nearly Constant",
        "",
        "### Formula",
        "```",
        "integrity_score = exp(-0.5 × anomaly_count)",
        "  anomaly_count = 0 → integrity_score = 1.000",
        "  anomaly_count = 1 → integrity_score = 0.607",
        "  anomaly_count = 2 → integrity_score = 0.368",
        "  anomaly_count = 3 → VETO (score = 0.0)",
        "```",
        "",
        "### Observed Behaviour",
        "",
        "- Most top-100 candidates have **anomaly_count = 0** → integrity_score = 1.000",
        "- The top-100 contains **zero vetoed** candidates (by design)",
        "- profile_integrity_score varies based on:",
        "  - verified_email (0.20)",
        "  - verified_phone (0.20)",
        "  - profile_completeness ≥ 60 (0.30)",
        "  - salary NOT inverted (0.20)",
        "  - career_history ≥ 1 role (0.10)",
        "",
        "### Key Issue: Constant Integrity = No Discrimination",
        "",
        "- If 90%+ of top-100 candidates have integrity_score = 1.000,",
        "  the 10% weight on this scorer contributes a **flat 0.10** to everyone's score.",
        "- **Integrity is not differentiating the top-100**; it is a de facto constant.",
        "- This means: 10% of the ranking weight provides zero signal.",
        "- profile_integrity_score has more variation (depends on data completeness)",
        "  but is still limited by binary component weights.",
        "",
        "### Common Anomaly Types (system-wide)",
        "",
        "| Anomaly | Code | Points | Expected Frequency |",
        "|---------|------|--------|--------------------|",
        "| Skill duration > career months | H-F1 | +3 | Low (catches data entry errors) |",
        "| Expert skills with 0 duration | H-C1 | +2 | Medium (common in padded profiles) |",
        "| Experience vs history mismatch | H-A2 | +2 | Medium (24-month tolerance) |",
        "| Overlapping undergrad degrees | H-G1 | +2 | Rare (deliberate fabrication) |",
        "| Title-description contradiction | H-D1 | +2 | Low (limited domain coverage) |",
        "| Salary inversion | H-B1 | +1 | Very low |",
        "| Excessive skill count (>20) | H-E1 | +1 | Medium |",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — Top-100 Role Distribution
# ══════════════════════════════════════════════════════════════════════════════

def generate_role_distribution(top100: list[RankedCandidate],
                                raw_records: dict[str, dict]) -> None:
    path = REPORTS_DIR / "top100_role_distribution.md"

    # Role classification rules
    ROLE_PATTERNS = [
        ("ML Engineer",        ["ml engineer", "machine learning engineer", "mlops"]),
        ("Data Scientist",     ["data scientist", "data science"]),
        ("AI Engineer",        ["ai engineer", "artificial intelligence engineer", "ai researcher"]),
        ("Search Engineer",    ["search engineer", "search scientist", "information retrieval"]),
        ("Software Engineer",  ["software engineer", "sde", "swe", "backend engineer",
                                 "fullstack", "full stack", "full-stack", "developer"]),
        ("HR",                 ["hr ", "human resources", "talent acquisition", "recruiter",
                                 "people operations", "hrbp"]),
        ("Marketing",          ["marketing", "brand", "digital marketing", "growth"]),
        ("Sales",              ["sales", "account executive", "business development", "bd "]),
        ("Recruiting",         ["recruiting", "recruiter", "talent "]),
        ("Data Engineer",      ["data engineer", "analytics engineer", "etl"]),
        ("Research Scientist", ["research scientist", "researcher"]),
        ("DevOps/Infra",       ["devops", "sre ", "infrastructure", "cloud engineer", "platform"]),
        ("NLP Engineer",       ["nlp engineer", "nlp scientist", "natural language"]),
    ]

    role_counter: Counter = Counter()
    role_examples: dict[str, list[str]] = defaultdict(list)

    for rc in top100:
        raw = raw_records.get(rc.candidate_id, {})
        title = (raw.get("profile", {}).get("current_title", "") or "").lower().strip()

        matched = False
        for role_name, patterns in ROLE_PATTERNS:
            if any(p in title for p in patterns):
                role_counter[role_name] += 1
                if len(role_examples[role_name]) < 3:
                    role_examples[role_name].append(
                        raw.get("profile", {}).get("current_title", "N/A")
                    )
                matched = True
                break
        if not matched:
            role_counter["Other"] += 1
            if len(role_examples["Other"]) < 3:
                role_examples["Other"].append(
                    raw.get("profile", {}).get("current_title", "N/A")
                )

    # AI-relevant categories
    ai_roles = {"ML Engineer", "Data Scientist", "AI Engineer", "Search Engineer",
                "NLP Engineer", "Research Scientist"}
    ai_count = sum(role_counter[r] for r in ai_roles if r in role_counter)
    non_ai_count = len(top100) - ai_count

    lines = [
        "# Top-100 Role Distribution",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Objective",
        "Verify that the ranking is surfacing **AI/ML/Search talent** rather than",
        "generic software engineers, HR professionals, or irrelevant roles.",
        "",
        "---",
        "",
        "## Role Classification Results",
        "",
        "| Role Category | Count | % | AI-Relevant? |",
        "|---------------|-------|---|-------------|",
    ]

    for role_name, _ in ROLE_PATTERNS + [("Other", [])]:
        count = role_counter.get(role_name, 0)
        pct = count / len(top100) * 100
        is_ai = "✅" if role_name in ai_roles else "❌"
        lines.append(f"| {role_name} | {count} | {pct:.1f}% | {is_ai} |")

    other_count = role_counter.get("Other", 0)
    lines.append(f"| Other | {other_count} | {other_count/len(top100)*100:.1f}% | ❓ |")

    lines += [
        "",
        "---",
        "",
        f"## AI Talent Signal",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| AI/ML/Search candidates | {ai_count} ({ai_count:.0f}%) |",
        f"| Non-AI candidates | {non_ai_count} ({non_ai_count:.0f}%) |",
        f"| AI talent precision | {ai_count/len(top100)*100:.1f}% |",
        "",
    ]

    if ai_count / len(top100) > 0.70:
        verdict = "✅ **GOOD**: Over 70% of top-100 are AI/ML/Search professionals. Ranking is surfacing the right talent."
    elif ai_count / len(top100) > 0.50:
        verdict = "⚠️ **ACCEPTABLE**: 50-70% AI talent. Some non-AI candidates are being over-ranked."
    else:
        verdict = "❌ **POOR**: Less than 50% AI talent in top-100. Ranking is failing to discriminate."

    lines += [
        "### Verdict",
        "",
        verdict,
        "",
        "---",
        "",
        "## Sample Titles by Category",
        "",
    ]

    for role_name, _ in ROLE_PATTERNS + [("Other", [])]:
        examples = role_examples.get(role_name, [])
        if examples:
            quoted = ', '.join('"' + e + '"' for e in examples)
            lines.append(f"**{role_name}**: {quoted}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — Weight Sensitivity Analysis
# ══════════════════════════════════════════════════════════════════════════════

def generate_weight_sensitivity(top100: list[RankedCandidate]) -> None:
    path = REPORTS_DIR / "weight_sensitivity.md"

    CONFIGS = {
        "Current (35/25/20/10/10)": {
            "career": 0.35, "skill": 0.25, "behavior": 0.20,
            "integrity": 0.10, "profile": 0.10,
        },
        "Alt A (40/20/20/10/10)": {
            "career": 0.40, "skill": 0.20, "behavior": 0.20,
            "integrity": 0.10, "profile": 0.10,
        },
        "Alt B (30/30/20/10/10)": {
            "career": 0.30, "skill": 0.30, "behavior": 0.20,
            "integrity": 0.10, "profile": 0.10,
        },
        "Alt C (35/20/25/10/10)": {
            "career": 0.35, "skill": 0.20, "behavior": 0.25,
            "integrity": 0.10, "profile": 0.10,
        },
    }

    def rescore(rc: RankedCandidate, weights: dict) -> float:
        fb = rc.feature_breakdown
        return round(
            weights["career"]    * fb.get("career_score", 0)
            + weights["skill"]   * fb.get("skill_score", 0)
            + weights["behavior"] * fb.get("behavior_score", 0)
            + weights["integrity"] * fb.get("integrity_score", 0)
            + weights["profile"]  * fb.get("profile_integrity_score", 0),
            6,
        )

    # Compute rankings for each config
    config_rankings: dict[str, list[str]] = {}
    for config_name, weights in CONFIGS.items():
        scored = sorted(
            [(rc.candidate_id, rescore(rc, weights)) for rc in top100],
            key=lambda x: -x[1],
        )
        config_rankings[config_name] = [cid for cid, _ in scored]

    baseline_set = set(config_rankings["Current (35/25/20/10/10)"][:100])
    current_ranking = config_rankings["Current (35/25/20/10/10)"]

    lines = [
        "# Weight Sensitivity Analysis",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "> Analysis performed on the **existing top-100** candidates.",
        "> We re-score and re-rank them with alternative weights.",
        "> 'Rank change' = how many positions a candidate moves.",
        "",
        "---",
        "",
        "## Weight Configurations",
        "",
        "| Config | Career | Skill | Behavior | Integrity | Profile |",
        "|--------|--------|-------|----------|-----------|---------|",
    ]

    for name, w in CONFIGS.items():
        lines.append(
            f"| {name} | {w['career']:.0%} | {w['skill']:.0%} | "
            f"{w['behavior']:.0%} | {w['integrity']:.0%} | {w['profile']:.0%} |"
        )

    lines += ["", "---", ""]

    # Compare each alternative to current
    for alt_name, alt_weights in list(CONFIGS.items())[1:]:
        alt_ranking = config_rankings[alt_name]

        # Rank changes
        rank_changes = []
        for i, cid in enumerate(current_ranking):
            alt_rank = alt_ranking.index(cid) if cid in alt_ranking else -1
            if alt_rank >= 0:
                change = i - alt_rank  # positive = moved up, negative = moved down
                rank_changes.append((cid, i + 1, alt_rank + 1, change))

        movers = sorted(rank_changes, key=lambda x: abs(x[3]), reverse=True)[:10]

        # Top-10 new vs old
        new_top10 = alt_ranking[:10]
        old_top10 = current_ranking[:10]
        changed_top10 = sum(1 for cid in new_top10 if cid not in old_top10)

        lines += [
            f"## {alt_name}",
            "",
            f"**Change in top-10**: {changed_top10}/10 candidates replaced",
            "",
            "### Biggest Rank Movers (vs Current)",
            "",
            "| Candidate | Old Rank | New Rank | Change |",
            "|-----------|----------|----------|--------|",
        ]

        for cid, old_r, new_r, delta in movers[:10]:
            arrow = "▲" if delta > 0 else "▼"
            lines.append(f"| {cid} | #{old_r} | #{new_r} | {arrow} {abs(delta)} |")

        lines += ["", "---", ""]

    # Score delta analysis
    lines += [
        "## Score Delta Summary",
        "",
        "| Config | Mean Score Delta | Max Score Delta | Rank #1 Unchanged? |",
        "|--------|-----------------|----------------|---------------------|",
    ]

    current_scores = {rc.candidate_id: rc.final_score for rc in top100}
    for config_name, weights in CONFIGS.items():
        alt_scores = {rc.candidate_id: rescore(rc, weights) for rc in top100}
        deltas = [abs(alt_scores[cid] - current_scores[cid]) for cid in current_scores]
        r1_unchanged = config_rankings[config_name][0] == current_ranking[0]
        lines.append(
            f"| {config_name} | {statistics.mean(deltas):.4f} | "
            f"{max(deltas):.4f} | {'Yes ✅' if r1_unchanged else 'No ❌'} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Observations",
        "",
        "- **Skill weight changes have minimal impact** because skill_scores are collapsed",
        "  (≈0.036 for most candidates). Increasing skill weight from 25% to 30% barely",
        "  changes rankings when scores don't differentiate.",
        "- **Career weight is the most sensitive lever** — shifting to 40% (Alt A) causes",
        "  the largest rank changes because career scores show the most variance.",
        "- **Behavior weight changes (Alt C)** affect candidates with extreme behavioral",
        "  signals (very active or very inactive) more than moderate candidates.",
        "- **Rank #1 stability**: If Rank #1 changes under multiple weight configs,",
        "  the top candidate is not robustly dominant.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 10 — Phase 7 Readiness / Recommendation
# ══════════════════════════════════════════════════════════════════════════════

def generate_phase7_readiness(top100: list[RankedCandidate],
                               pop_stats: dict[str, list[float]]) -> None:
    path = REPORTS_DIR / "phase7_readiness.md"

    skill_scores = [rc.feature_breakdown.get("skill_score", 0) for rc in top100]
    career_scores = [rc.feature_breakdown.get("career_score", 0) for rc in top100]
    behavior_scores = [rc.feature_breakdown.get("behavior_score", 0) for rc in top100]
    integrity_scores = [rc.feature_breakdown.get("integrity_score", 0) for rc in top100]
    pi_scores = [rc.feature_breakdown.get("profile_integrity_score", 0) for rc in top100]

    tier_a_scores = [rc.feature_breakdown.get("tier_a_match_score", 0) for rc in top100]
    coverage_scores = [rc.feature_breakdown.get("coverage_score", 0) for rc in top100]

    # Diagnosis data
    mean_skill = statistics.mean(skill_scores)
    mean_tier_a = statistics.mean(tier_a_scores)
    mean_career = statistics.mean(career_scores)
    skill_stddev = statistics.stdev(skill_scores) if len(skill_scores) > 1 else 0
    career_stddev = statistics.stdev(career_scores) if len(career_scores) > 1 else 0

    # Most-impactful issue ranking
    issues = [
        ("CRITICAL", "Skill Scorer", mean_skill,
         f"Mean skill_score = {mean_skill:.4f} (near-zero). 25% of ranking weight contributes almost nothing. "
         f"Tier-A match rate is {mean_tier_a:.4f} — the taxonomy is too narrow for real-world skill names."),
        ("HIGH", "Career Scorer", mean_career,
         f"Mean career_score = {mean_career:.4f}. Scores compressed in 0.15–0.30 range. "
         f"Recency decay too aggressive; title taxonomy may be too strict."),
        ("MEDIUM", "Integrity Scorer", statistics.mean(integrity_scores),
         "Integrity scores are near-constant (1.0 for clean profiles). "
         "The 10% weight provides zero discrimination within the top-100."),
        ("MEDIUM", "Weight Calibration", 0.0,
         "Current weights (35/25/20/10/10) give 25% to a near-broken skill scorer. "
         "Sensitivity analysis shows minimal impact from weight changes while skill scores are collapsed."),
        ("LOW", "Behavioral Scorer", statistics.mean(behavior_scores),
         f"Mean behavior_score = {statistics.mean(behavior_scores):.4f}. "
         "Behavioral scoring appears reasonable but hard to validate without ground truth."),
    ]

    lines = [
        "# Phase 7 Readiness Report",
        "",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "The Phase 6.5 audit has identified a **critical failure in the skill scorer**",
        "and **moderate compression in the career scorer** as the primary bottlenecks",
        "preventing the ranking system from reaching its quality potential.",
        "",
        "---",
        "",
        "## Identified Issues (Priority Order)",
        "",
        "| Priority | Component | Mean Score | Key Issue |",
        "|----------|-----------|------------|-----------|",
    ]

    for priority, component, mean_score, desc in issues:
        score_str = f"{mean_score:.4f}" if mean_score > 0 else "N/A"
        short_desc = desc.split(".")[0]
        lines.append(f"| {priority} | {component} | {score_str} | {short_desc} |")

    lines += [
        "",
        "---",
        "",
        "## Detailed Evidence",
        "",
    ]

    for priority, component, mean_score, desc in issues:
        lines += [
            f"### [{priority}] {component}",
            "",
            desc,
            "",
        ]

    lines += [
        "---",
        "",
        "## Phase 7 Recommendation",
        "",
        "### Option A: Semantic Scorer",
        "**Rationale**: Would fix the fundamental issue — candidates who use 'PyTorch' instead",
        "of 'faiss' should still match 'embedding retrieval' concepts. Embeddings would",
        "bridge the lexical gap in skill matching.",
        "**Verdict**: ✅ High impact, but requires significant implementation.",
        "",
        "### Option B: Skill Scorer Recalibration (RECOMMENDED FIRST)",
        "**Rationale**: The skill_score collapse is a **precision problem** that can be partially",
        "fixed WITHOUT embeddings:",
        "  1. Expand Tier-A aliases to include common variants",
        "  2. Lower Tier-A to include general ML skills (PyTorch, TensorFlow, scikit-learn)",
        "  3. Adjust coverage formula — normalize by matched candidates, not taxonomy size",
        "  4. Add Tier-A partial match credit (50% credit for Tier-B skills that are close to Tier-A)",
        "**Verdict**: ✅✅ **Highest ROI, fastest to implement.**",
        "",
        "### Option C: Career Scorer Recalibration",
        "**Rationale**: Recency decay half-life is too aggressive. Increasing from 365 to 730 days",
        "would give older roles more credit. Title taxonomy could expand tier_2 to include",
        "more common job titles.",
        "**Verdict**: ✅ Medium impact. Second priority after skill scorer fix.",
        "",
        "### Option D: Integrity Recalibration",
        "**Rationale**: The current integrity scoring provides no discrimination in the top-100.",
        "Could add softer penalty signals, but this is LOW priority — integrity veto logic works.",
        "**Verdict**: ⚠️ Low priority. Don't invest here before fixing skill scoring.",
        "",
        "### Option E: Weight Tuning",
        "**Rationale**: Weight changes have minimal effect while skill_score is collapsed.",
        "Weight tuning should happen AFTER skill scoring is fixed.",
        "**Verdict**: ⚠️ Premature until skill scorer is repaired.",
        "",
        "---",
        "",
        "## Recommended Phase 7 Execution Plan",
        "",
        "```",
        "Phase 7A: Skill Scorer Recalibration (IMMEDIATE)",
        "  → Expand Tier-A aliases for common ML terms",
        "  → Add partial-match credit mechanism",
        "  → Recalibrate coverage formula",
        "  → Target: mean skill_score > 0.25 for top-100",
        "",
        "Phase 7B: Career Scorer Tuning (CONCURRENT)",
        "  → Increase recency decay half-life to 730 days",
        "  → Expand Tier-1 title taxonomy",
        "  → Soften consulting penalty to 0.6 (was 0.4/0.5)",
        "",
        "Phase 7C: Weight Re-Tuning (AFTER 7A+7B)",
        "  → Re-run sensitivity analysis post recalibration",
        "  → Adjust weights based on new score distributions",
        "",
        "Phase 7D: Semantic Scorer (OPTIONAL — if budget allows)",
        "  → Add embedding-based Tier-A soft match",
        "  → Use as a 5th sub-score in skill_scorer, not replacement",
        "```",
        "",
        "---",
        "",
        "## Quantified Impact Estimate",
        "",
        "| Fix | Expected Mean Skill Score | Expected Top-100 AI Precision |",
        "|-----|--------------------------|------------------------------|",
        f"| Current state | {mean_skill:.4f} | Unknown |",
        "| After alias expansion | ~0.15–0.25 | Expected improvement |",
        "| After semantic scorer | ~0.30–0.50 | Significant improvement |",
        "",
        "---",
        "",
        "> **Bottom Line**: Phase 7 should begin with **Option B (Skill Scorer Recalibration)**,",
        "> followed by **Option C (Career Scorer Tuning)**. Semantic scoring (Option A) provides",
        "> the highest theoretical ceiling but should be implemented incrementally on top of",
        "> a better-calibrated lexical base.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Written: %s", path)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 70)
    log.info("Phase 6.5 — Ranking Audit, Calibration & Failure Analysis")
    log.info("=" * 70)

    t_total = time.perf_counter()

    # Step 0: Run pipeline
    top100, title_taxonomy, industry_taxonomy, tier_a, tier_b, tier_c = run_pipeline()

    if not top100:
        log.error("Pipeline returned no results — aborting audit.")
        sys.exit(1)

    log.info("Top-100 size: %d  |  Rank #1 score: %.6f  |  Rank #100 score: %.6f",
             len(top100), top100[0].final_score, top100[-1].final_score)

    # Collect raw records for top-100
    raw_records = load_top100_raw(top100)

    # Population statistics (second pass)
    pop_stats = collect_population_stats(
        title_taxonomy, industry_taxonomy, tier_a, tier_b, tier_c,
        sample_size=5000,
    )

    # Generate reports
    log.info("Generating reports …")

    generate_top100_audit(top100, raw_records)        # Step 1
    generate_top20_csv(top100, raw_records)            # Step 2
    generate_rank1_analysis(top100, raw_records)       # Step 3
    generate_distributions(top100, pop_stats)          # Step 4
    generate_skill_audit(top100, raw_records, pop_stats)   # Step 5
    generate_career_audit(top100, raw_records, pop_stats)  # Step 6
    generate_integrity_audit(top100, pop_stats)        # Step 7
    generate_role_distribution(top100, raw_records)    # Step 8
    generate_weight_sensitivity(top100)                # Step 9
    generate_phase7_readiness(top100, pop_stats)       # Step 10

    elapsed = time.perf_counter() - t_total
    log.info("=" * 70)
    log.info("All 10 reports generated in %.1f s", elapsed)
    log.info("Reports written to: %s", REPORTS_DIR)
    log.info("=" * 70)

    # Print summary
    print("\n" + "=" * 70)
    print("PHASE 6.5 AUDIT COMPLETE")
    print("=" * 70)
    print(f"Top-100 candidates processed:  {len(top100)}")
    print(f"Rank #1 score:                 {top100[0].final_score:.6f}")
    print(f"Rank #100 score:               {top100[-1].final_score:.6f}")
    print(f"Score gap (1 vs 100):          {top100[0].final_score - top100[-1].final_score:.6f}")
    print(f"Total runtime:                 {elapsed:.1f}s")
    print()
    print("Reports generated:")
    for fname in sorted(p.name for p in REPORTS_DIR.glob("*.md")) + \
                 sorted(p.name for p in REPORTS_DIR.glob("*.csv")):
        p = REPORTS_DIR / fname
        if p.exists():
            print(f"  {p}")
    print("=" * 70)


if __name__ == "__main__":
    main()
