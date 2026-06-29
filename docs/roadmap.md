# Implementation Roadmap
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Generated:** 2026-06-19

---

## Overview

This roadmap breaks the implementation into 7 sequential phases. Each phase has a clear deliverable, success criteria, and estimated time budget. The philosophy is **working system first, optimizations second** — matching the JD's "ship a working ranker in a week" ethos.

---

## Phase 1 — Analysis & Foundation (COMPLETE)

> **Status:** ✅ Completed in this session

### Deliverables
- [x] `docs/challenge_analysis.md` — Complete file-by-file analysis
- [x] `data/jd_requirements.json` — Structured JD extraction
- [x] `reports/dataset_summary.md` — Dataset statistics (N=2,000 sample)
- [x] `reports/signals_analysis.md` — All 23 signals analyzed with weights
- [x] `reports/honeypot_hypotheses.md` — Suspicious patterns catalogued
- [x] `docs/feature_engineering_plan.md` — All features designed with formulas
- [x] `docs/architecture.md` — System architecture designed
- [x] `docs/roadmap.md` — This file

### Success Criteria
- All challenge files understood
- All constraints captured
- No implementation started before foundation is complete

---

## Phase 2 — Data Layer & Configuration

> **Goal:** Build the streaming pipeline and all configuration/taxonomy files

### Tasks

#### 2.1 — Build Data Taxonomies
- Create `data/skill_taxonomy.json` with Tier-A/B/C JD skills and their aliases
- Create `data/title_taxonomy.json` mapping 200+ job titles to Tier 1–4 relevance
- Create `data/industry_taxonomy.json` — product vs services classification
- Review against `sample_candidates.json` — ensure major skill names are covered

#### 2.2 — Build Configuration Module
- Implement `src/config.py` with all JD constants, weights, thresholds
- Make all weights tunable via a single dict (for later calibration)

#### 2.3 — Build Streaming Loader
- Implement `src/pipeline/loader.py`
- Stream candidates line-by-line from JSONL
- Handle malformed lines gracefully (skip + log)
- Test on `sample_candidates.json` (50 candidates)
- Test on `candidates.jsonl` (100K candidates) — measure streaming speed

#### 2.4 — Build Utility Modules
- `src/utils/date_utils.py` — date arithmetic, recency decay
- `src/utils/text_utils.py` — fuzzy matching, TF-IDF relevance, title normalization

### Estimated Time: 3–4 hours

### Success Criteria
- Can stream all 100K candidates in < 30 seconds
- Taxonomy files cover all skill names seen in sample
- Fuzzy matching handles common aliases (e.g., "sentence-transformers" ↔ "SBERT")

---

## Phase 3 — Feature Extraction Engine

> **Goal:** Implement all 6 feature groups as independent, testable modules

### Tasks

#### 3.1 — Implement Integrity Scorer (FIRST — Critical)
- `src/features/integrity_scorer.py`
- Honeypot detection (compound anomaly scoring)
- Keyword stuffing detection
- Profile integrity baseline
- **Test with:** Manually confirmed honeypot patterns from `reports/honeypot_hypotheses.md`
- **Acceptance criteria:** Correctly flags CAND_0000011 (impossible skill duration) and salary-inverted candidates

#### 3.2 — Implement Career Scorer (HIGHEST IMPACT)
- `src/features/career_scorer.py`
- Title relevance: map all unique titles in sample to taxonomy tiers
- Career history relevance: TF-IDF keyword match against JD terms
- Product company detection: industry + company name checks
- Relevant experience years calculation
- **Test with:** Compare ML Engineer vs HR Manager vs QA Engineer — confirm ML Engineer scores highest

#### 3.3 — Implement Skill Scorer
- `src/features/skill_scorer.py`
- JD skill match with trust weighting
- Assessment score integration
- Skill depth score
- **Test with:** Candidate with many AI skills but 0 duration_months — confirm trust score is low

#### 3.4 — Implement Behavioral Scorer
- `src/features/behavioral_scorer.py`
- Recency decay
- Recruiter responsiveness
- Availability composite
- Notice period scoring
- Platform engagement
- Offer reliability
- **Test with:** Candidate with last_active = 365 days ago — confirm near-zero recency score

#### 3.5 — Implement Location Scorer
- `src/features/location_scorer.py`
- Location string matching to preferred/acceptable/other cities
- Work mode compatibility
- Salary fit check

#### 3.6 — Implement Education Scorer
- `src/features/education_scorer.py`
- Education tier extraction
- Field of study alignment

#### 3.7 — Build Feature Extractor Orchestrator
- `src/pipeline/feature_extractor.py`
- Call all scorers in order (integrity first)
- Return `FeatureVector` dataclass
- Performance test: process 2,000 candidates in < 10 seconds

### Estimated Time: 6–8 hours

### Success Criteria
- All feature scorers produce scores in [0, 1]
- Integrity scorer correctly identifies honeypots with compound flags
- Career scorer ranks ML Engineer > QA Engineer > HR Manager
- Feature extraction of 100K candidates in < 120 seconds

---

## Phase 4 — Scoring Engine & Ranking

> **Goal:** Assemble features into final scores and produce a sorted ranked list

### Tasks

#### 4.1 — Build Ranker
- `src/pipeline/ranker.py`
- Weighted aggregation of all feature scores
- Apply veto rules (honeypots → score = 0)
- Apply penalty rules (keyword stuffers → score *= 0.3)
- Sort descending by final_score
- Tie-break by candidate_id ascending (as per spec)
- Select top 100

#### 4.2 — Build Entry Point
- `src/rank.py`
- CLI with argparse: `--candidates`, `--out`, `--debug`
- End-to-end pipeline: load → stream → extract → rank → write

#### 4.3 — Initial Ranking on Sample
- Run on `sample_candidates.json` (50 candidates)
- Manually inspect top 10 — do they make sense?
- Verify: ML Engineer ranks higher than HR Manager with same AI skills
- Verify: Inactive candidates rank below active ones

#### 4.4 — Weight Calibration Pass 1
- Inspect bottom-ranked candidates — are they sensibly bad?
- Inspect top-ranked candidates — are they genuinely good?
- Adjust weights in `config.py` based on observed ranking quality
- Document weight changes and reasoning

### Estimated Time: 4–5 hours

### Success Criteria
- Running on 50-candidate sample produces sensible top 10
- Running on 2,000-candidate sample in < 20 seconds
- Running on full 100K candidates in < 3 minutes (leaves margin for CSV write + validation)
- No honeypot candidates in top 10 of sample

---

## Phase 5 — Semantic Matching Enhancement (Optional, Time Permitting)

> **Goal:** Add lightweight semantic matching to capture "Tier-5" candidates — those who built relevant systems without using exact JD keywords

### Design Constraint
- Must use CPU-only local models
- Must not exceed 5-minute total runtime
- Semantic step should be **pre-computed** (not at ranking time)

### Tasks

#### 5.1 — Evaluate Lightweight Models
- Test `all-MiniLM-L6-v2` (sentence-transformers) — ~80MB, fast on CPU
- Test `paraphrase-MiniLM-L3-v2` — ~60MB, even faster
- Measure: time to encode 100K candidate summaries on CPU

#### 5.2 — Pre-compute Candidate Embeddings (Optional Offline Step)
- If within time budget: encode `profile.summary` + `career_history[].description` for each candidate
- Store as numpy array (~100K × 384 = ~150 MB)
- This step CAN exceed 5 minutes (pre-computation is allowed per submission spec)
- Query embedding = JD text embedding

#### 5.3 — Integrate Semantic Score
- Load pre-computed embeddings at ranking time (fast)
- Compute cosine similarity to JD embedding
- Add as a feature: `semantic_relevance_score` with weight ~0.15
- Reduce career_history relevance weight proportionally

#### 5.4 — Hybrid Ranking
- Combine BM25/keyword relevance (Phase 3) with semantic similarity (Phase 5)
- This is the "hybrid retrieval" pattern the JD specifically mentions as valuable

### Estimated Time: 4–6 hours (plus overnight embedding generation)

### Success Criteria
- Semantic step identifies candidates who describe "built a recommendation system at product company" without using exact keywords
- Runtime for semantic score computation at inference: < 30 seconds (just dot products on pre-computed embeddings)

> **Note:** If pre-computation time is too high for the 5-minute ranking window, this phase is a "nice to have" and the Phase 3 keyword-based system is sufficient for submission.

---

## Phase 6 — Reasoning Generation

> **Goal:** Generate high-quality, specific reasoning strings for each of the top 100 candidates

### Design Principles (from Stage 4 requirements)
1. Reference specific facts from the candidate profile
2. Connect explicitly to JD requirements
3. Acknowledge honest concerns (notice period, location, etc.)
4. Vary meaningfully across candidates (no templates)
5. Tone must match rank (rank 5 ≠ same enthusiasm as rank 95)

### Tasks

#### 6.1 — Design Reasoning Template System
- Create structured reasoning builder in `src/pipeline/output_writer.py`
- Each component is conditionally included based on candidate features:

```python
def generate_reasoning(candidate, fv: FeatureVector) -> str:
    parts = []
    
    # Opening: Title + experience
    parts.append(f"{current_title} with {relevant_years:.1f}yrs relevant AI/ML experience")
    
    # Skill evidence
    if top_jd_skills:
        parts.append(f"skilled in {', '.join(top_jd_skills[:3])}")
    
    # Career quality signal
    if product_company_flag:
        parts.append(f"product-company background ({best_company})")
    if consulting_penalty:
        parts.append(f"concern: primarily services-company background")
    
    # Behavioral signal (specific values)
    if recency_good:
        parts.append(f"active {days_inactive}d ago, {notice_days}d notice")
    if recency_bad:
        parts.append(f"concern: inactive {days_inactive}d")
    
    # Location
    parts.append(f"based in {location}")
    
    return "; ".join(parts) + "."
```

#### 6.2 — Review Reasoning Quality
- Manually review top 20 reasonings
- Ensure no two are identical
- Ensure rank-95 reasoning sounds less enthusiastic than rank-5
- Ensure all claims are sourced from actual profile fields (no hallucination)

#### 6.3 — Calibrate Tone by Rank Band
- Rank 1–10: Strong positive language, specific strengths, minor concerns noted
- Rank 11–50: Positive with qualifications, balanced assessment
- Rank 51–100: Mixed or marginal fit, specific gap identified

### Estimated Time: 2–3 hours

### Success Criteria
- 10 randomly sampled reasonings all pass Stage 4 checklist (specific, connected to JD, honest, no hallucination, varied)
- No two consecutive reasonings are identical
- Every claim is verifiable from the candidate record

---

## Phase 7 — Submission Pipeline & Validation

> **Goal:** Package everything for submission — CSV, metadata, code repository, sandbox

### Tasks

#### 7.1 — Final CSV Generation
- Run full pipeline on `candidates.jsonl`
- Generate `outputs/submission.csv`
- Run `validate_submission.py` — confirm zero errors

#### 7.2 — Final Validation Checklist
```bash
# Format validation
python validate_submission.py outputs/submission.csv

# Verify counts
python -c "import csv; rows = list(csv.reader(open('outputs/submission.csv'))); print(f'Rows: {len(rows)-1}')"

# Check no honeypot candidates in top 10 (manual review)
head -11 outputs/submission.csv
```

#### 7.3 — Performance Benchmark
- Time the full ranking run: `time python src/rank.py --candidates ...`
- Confirm: < 5 minutes
- Confirm: < 16 GB RAM (use `memory_profiler` or `psutil`)

#### 7.4 — Code Repository Preparation
- Clean, documented code
- `requirements.txt` with pinned versions
- `README.md` with:
  - Setup instructions
  - Reproduce command: `python src/rank.py --candidates ./candidates.jsonl --out ./submission.csv`
  - Pre-computation instructions (if Phase 5 implemented)
- `submission_metadata.yaml` filled in

#### 7.5 — Sandbox Deployment
- Deploy to HuggingFace Spaces or Streamlit Cloud
- Accept small candidate sample (≤100) as JSON input
- Run ranking pipeline on sample
- Return ranked CSV
- Test end-to-end in sandbox environment

#### 7.6 — Git History Authenticity
- Ensure meaningful commit history showing iterative development
- Commits should reflect real phases: analysis → features → calibration → testing
- Avoid single-dump commits — evaluators will check git log at Stage 4

### Estimated Time: 3–4 hours

### Success Criteria
- `validate_submission.py` returns "Submission is valid."
- Full pipeline runtime < 5 minutes on CPU
- GitHub repo has meaningful commit history
- Sandbox link works on sample input
- `submission_metadata.yaml` complete and accurate

---

## Timeline Summary

| Phase | Description | Estimated Hours |
|---|---|---|
| Phase 1 | Analysis & Foundation | 4–5 hrs ✅ |
| Phase 2 | Data Layer & Configuration | 3–4 hrs |
| Phase 3 | Feature Extraction Engine | 6–8 hrs |
| Phase 4 | Scoring Engine & Ranking | 4–5 hrs |
| Phase 5 | Semantic Matching (Optional) | 4–6 hrs |
| Phase 6 | Reasoning Generation | 2–3 hrs |
| Phase 7 | Submission Pipeline | 3–4 hrs |
| **Total** | | **26–35 hrs** |

---

## Risk Registry

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Full dataset too slow to stream | Medium | High | Benchmark early in Phase 2; add progress logging |
| Honeypot false-positive rate > 10% | Medium | Critical | Test compound scoring carefully; bias toward conservative thresholds |
| Keyword stuffers dominate top 10 | High | High | P0 priority for career title relevance score |
| Semantic model too slow on CPU | Medium | Medium | Make Phase 5 optional; test with mini model first |
| Reasoning fails Stage 4 review | Low | High | Manual review of 20 reasonings before submission |
| Git history looks single-dump | Medium | Medium | Commit after each phase; use meaningful messages |
| Sandbox environment fails | Low | Medium | Test sandbox before final submission |
| Score not monotonically decreasing | Low | Critical | Explicit sort + validation step in output_writer |

---

## Recommended Next Step

**Start Phase 2 immediately.** The taxonomy files (`skill_taxonomy.json`, `title_taxonomy.json`) are the most critical dependency for Phases 3–4. Build those first, validate against the sample, then implement the scorers in P0 priority order:

1. `integrity_scorer.py` (honeypot veto — must work correctly)
2. `career_scorer.py` (title relevance — primary anti-stuffing)
3. `behavioral_scorer.py` (recency + responsiveness — availability gating)
4. `skill_scorer.py` (JD skill match)
5. Everything else
