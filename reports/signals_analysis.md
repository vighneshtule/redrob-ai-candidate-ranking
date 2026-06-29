# Redrob Behavioral Signals — Analysis Report
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Source:** redrob_signals_doc.docx + candidate_schema.json  
> **Generated:** 2026-06-19

---

## Overview

Each candidate record contains a `redrob_signals` object with **23 behavioral signals** derived from simulated platform engagement. These signals capture what a candidate *does* on the platform — not just what they *claim*. Per the challenge documentation:

> *"A perfect-on-paper candidate who hasn't logged in for 6 months and has a 5% response rate is, for hiring purposes, not actually available."*

The signals serve as a **multiplier or modifier** on top of skill-match scoring. They do NOT replace career/skill relevance — they amplify or dampen it.

---

## Signal Analysis Table

| # | Signal | Range / Type | Meaning | Sentiment | Suggested Weight | Notes |
|---|---|---|---|---|---|---|
| 1 | `profile_completeness_score` | 0–100 | % of profile filled in | Positive | Low–Medium (0.05) | High = serious candidate. Low = lazy or fake profile. |
| 2 | `signup_date` | date string | Platform join date | Neutral | Very Low (0.01) | Long tenure may indicate passive candidate who never converted. |
| 3 | `last_active_date` | date string | Last login date | **Critical Positive/Negative** | **High (0.15)** | >6 months inactive = functionally unavailable. |
| 4 | `open_to_work_flag` | bool | Explicitly available | **Critical Positive** | **High (0.15)** | True = strong availability signal. False = not necessarily unavailable (behavioral trap). |
| 5 | `profile_views_received_30d` | int ≥ 0 | Recruiter demand | Positive | Low (0.03) | High views = market-validated candidate. Indirect signal. |
| 6 | `applications_submitted_30d` | int ≥ 0 | Job-seeking intensity | Positive | Low (0.03) | High apps + not open_to_work = behavioral contradiction (potential trap). |
| 7 | `recruiter_response_rate` | 0.0–1.0 | % of recruiter messages replied to | **Critical Positive** | **High (0.15)** | Low (<0.2) = hard to hire even if skilled. High (>0.7) = easy to engage. |
| 8 | `avg_response_time_hours` | float ≥ 0 | Median hours to respond | Positive (lower=better) | Medium (0.05) | <24h = very responsive. >72h = slow. >168h = likely passive. |
| 9 | `skill_assessment_scores` | dict[str→0–100] | Platform-verified skill proficiency | **Critical Positive** | **High (0.20)** | Objective verification vs self-reported skills. Score on JD-relevant skills is the key signal. |
| 10 | `connection_count` | int ≥ 0 | Network size on Redrob | Neutral | Very Low (0.01) | Vanity metric. High count ≠ quality candidate. |
| 11 | `endorsements_received` | int ≥ 0 | Total skill endorsements | Positive | Low (0.03) | Weak social proof. Can be gamed. |
| 12 | `notice_period_days` | 0–180 | Stated notice period | **Critical Positive/Negative** | **High (0.12)** | 0–30 days = ideal. 31–60 = acceptable. 61–90 = borderline. >90 = penalize. |
| 13 | `expected_salary_range_inr_lpa` | {min, max} | Salary expectations in INR LPA | Mixed | Medium (0.05) | Inverted range (min > max) is a **honeypot signal**. Out-of-range salary expectations reduce fit. |
| 14 | `preferred_work_mode` | enum | Work arrangement preference | Neutral–Positive | Low (0.03) | JD is hybrid. remote-only is slight mismatch. flexible/hybrid/onsite are fine. |
| 15 | `willing_to_relocate` | bool | Relocation flexibility | Positive | Medium (0.05) | Critical for non-Pune/Noida candidates. True = +score for non-local candidates. |
| 16 | `github_activity_score` | -1–100 | GitHub engineering activity | Positive | Medium (0.08) | -1 = no GitHub (neutral). 0–30 = low. 30–70 = moderate. >70 = strong signal. JD explicitly values OSS. |
| 17 | `search_appearance_30d` | int ≥ 0 | Frequency in recruiter searches | Positive | Very Low (0.02) | High appearance = relevant-looking profile to recruiters (tautological but useful). |
| 18 | `saved_by_recruiters_30d` | int ≥ 0 | Bookmarked by recruiters | Positive | Low (0.03) | Social proof from recruiters. Indirect quality signal. |
| 19 | `interview_completion_rate` | 0.0–1.0 | Fraction of interviews attended | **Critical Positive** | **High (0.10)** | Low (<0.5) = unreliable. Ghost risk. High (>0.8) = dependable. |
| 20 | `offer_acceptance_rate` | -1 to 1.0 | Historical offer acceptance | Positive | Medium (0.05) | -1 = no history (neutral). Low (< 0.3) = offer ghost / high counter-offer risk. |
| 21 | `verified_email` | bool | Email verified | Positive | Very Low (0.01) | Basic authenticity check. |
| 22 | `verified_phone` | bool | Phone verified | Positive | Very Low (0.01) | Basic authenticity check. |
| 23 | `linkedin_connected` | bool | LinkedIn linked | Positive | Very Low (0.01) | Slight authenticity and network signal. |

---

## Signals by Category

### Tier 1 — Critical Signals (Must Use)

These signals directly determine whether a technically qualified candidate is **actually hireable**.

| Signal | Why It's Critical |
|---|---|
| `last_active_date` | Stale candidate = unreachable. 6+ month gap is a hard negative. |
| `open_to_work_flag` | Primary availability indicator. |
| `recruiter_response_rate` | Predicts engagement in hiring pipeline. Low rate = likely ghosting. |
| `notice_period_days` | Time-to-hire. JD explicitly prioritizes sub-30-day. |
| `interview_completion_rate` | Reliability signal. Candidates who ghost interviews are waste of hiring bandwidth. |
| `skill_assessment_scores` | Only **objective** skill verification. Cuts through self-reported skill inflation. |

### Tier 2 — High-Value Signals (Should Use)

| Signal | Use Case |
|---|---|
| `github_activity_score` | Technical engagement beyond resume. JD values OSS. -1 = neutral, not negative. |
| `offer_acceptance_rate` | Counter-offer risk. -1 = treat as neutral. |
| `avg_response_time_hours` | Operationalizes recruiter_response_rate — fast responders = good candidates. |
| `expected_salary_range_inr_lpa` | Feasibility check. Inverted min/max = honeypot flag. |
| `willing_to_relocate` | Location fit gating for non-local candidates. |

### Tier 3 — Moderate Signals (Can Use as Tiebreakers)

| Signal | Use Case |
|---|---|
| `profile_completeness_score` | Proxy for candidate seriousness. <50 = lazy/fake profile. |
| `applications_submitted_30d` | Active job seeker signal. Contradictions with open_to_work flag are meaningful. |
| `saved_by_recruiters_30d` | Market validation (recruiter consensus). |
| `profile_views_received_30d` | Demand signal. |
| `preferred_work_mode` | JD fit (hybrid = good). |
| `endorsements_received` | Weak social proof. Use as tiebreaker only. |

### Tier 4 — Noise Signals (Use with Caution or Skip)

| Signal | Concern |
|---|---|
| `connection_count` | Vanity metric — high network ≠ quality. |
| `signup_date` | Long tenure = passive candidate who never converted. Weak discriminator. |
| `search_appearance_30d` | Tautological with other signals. |
| `verified_email` / `verified_phone` / `linkedin_connected` | Too binary and widely available. Use only in deduplication. |

---

## Signal Interaction Patterns

### Pattern 1 — Behavioral Zombie
**Definition:** Candidate who appears active via `open_to_work_flag=True` but is actually disengaged.
- `last_active_date` > 180 days ago  
- `recruiter_response_rate` < 0.10  
- `applications_submitted_30d` = 0  
→ **Action:** Hard downweight regardless of skill score.

### Pattern 2 — Hidden Active Seeker
**Definition:** Candidate with `open_to_work_flag=False` but actively job-seeking.
- `applications_submitted_30d` > 5  
- `recruiter_response_rate` > 0.5  
- `last_active_date` < 14 days ago  
→ **Action:** Treat similarly to open_to_work=True.

### Pattern 3 — Perfect Paper, Unreachable
**Definition:** High skill match but practical hiring risk.
- Excellent career/skill match  
- `notice_period_days` > 90  
- `offer_acceptance_rate` < 0.2 (or -1 with low response rate)  
→ **Action:** Moderate downweight. Still include if top skills, but rank behind otherwise-equal candidates with shorter notice.

### Pattern 4 — Assessment-Validated Skill Match
**Definition:** Candidate has JD-relevant skills AND verified platform assessments confirming them.
- JD-relevant skills listed (e.g., NLP, Embeddings, Vector DB)  
- `skill_assessment_scores[skill]` > 60  
→ **Action:** Significant upweight. Assessment scores cut through keyword stuffing.

### Pattern 5 — Honeypot Behavioral Profile
**Definition:** Signals that suggest synthetic/impossible candidate.
- `expected_salary_range_inr_lpa.min` > `max` (salary inversion)  
- Career history duration inconsistent with stated `years_of_experience`  
- Skills listed as "expert" with `duration_months=0`  
→ **Action:** Assign honeypot score; exclude from top 100.

---

## Correlation Hypotheses with Hiring Success

| Signal | Expected Correlation | Reasoning |
|---|---|---|
| `recruiter_response_rate` | **Strong positive** | Fundamental to completing a hire |
| `interview_completion_rate` | **Strong positive** | Prevents wasted recruiter cycles |
| `last_active_date` (recency) | **Strong positive** | Active = engaged in job market |
| `open_to_work_flag` | **Moderate positive** | Explicit signal but can be stale |
| `notice_period_days` | **Negative** (higher = worse) | Delays time-to-hire |
| `skill_assessment_scores` | **Moderate-strong positive** | Objective vs self-reported |
| `github_activity_score` | **Moderate positive** (for technical roles) | Engineering engagement |
| `offer_acceptance_rate` | **Moderate positive** | Predicts conversion |
| `profile_completeness_score` | **Weak positive** | Completeness ≠ quality |
| `connection_count` | **Weak/noise** | Network ≠ fit |
| `signup_date` | **Noise** | Tenure alone meaningless |

---

## Recommended Signal Composite Formula

```
behavioral_score = (
    w1 * recency_score(last_active_date)          # 0.20
  + w2 * open_to_work_flag                         # 0.15 (binary)
  + w3 * recruiter_response_rate                   # 0.20
  + w4 * notice_period_score(notice_period_days)   # 0.15 (inverse, capped)
  + w5 * interview_completion_rate                 # 0.12
  + w6 * normalized(github_activity_score)         # 0.08 (-1 → 0)
  + w7 * offer_acceptance_rate_adjusted            # 0.05 (-1 → 0.5 neutral)
  + w8 * normalized(avg_response_time_hours, inv)  # 0.05 (inverted — lower = better)
)
```

**Where:**
- `recency_score(date)` = exponential decay from today, 90-day half-life
- `notice_period_score(days)` = 1.0 if ≤30d, linear decay to 0.0 at 180d
- `-1` values for github and offer_acceptance → map to neutral (0.5)

This composite (0.0–1.0) is then used as a **multiplicative modifier** applied to the base relevance score: `final_score = relevance_score × (0.6 + 0.4 × behavioral_score)`
