# Redrob Hackathon — Complete Challenge Analysis
> Generated: 2026-06-19 | Analyst: Senior ML/IR Engineer

---

## Executive Overview

This is the **Intelligent Candidate Discovery & Ranking Challenge** hosted by Redrob AI.
The task: given a fixed Job Description (Senior AI Engineer, Founding Team), rank the **best 100 candidates** from a pool of **100,000 synthetic-but-realistic profiles** using a scoring system that runs on CPU-only, within 5 minutes, ≤16 GB RAM, with **no external API calls**.

The challenge is deceptively hard because:
- 80+ "honeypot" profiles are injected to trap keyword-based systems.
- Keyword stuffers list all the right AI skills but have irrelevant career histories.
- Behavioral signals must be used to filter for *actually available* candidates.
- The evaluation is multi-stage including code reproduction and a live interview.

---

## File-by-File Analysis

---

### 1. `candidate_schema.json`

**Purpose:** JSON Schema (Draft-07) defining the exact structure of every candidate record in `candidates.jsonl`.

**Structure:**
```
candidate_id        → CAND_XXXXXXX (7-digit format, required)
profile             → Core biographical + employment info (required)
career_history      → 1–10 role objects (required)
education           → 0–5 degree objects (required)
skills              → List of {name, proficiency, endorsements, duration_months}
certifications      → Optional list of {name, issuer, year}
languages           → Optional list of {language, proficiency}
redrob_signals      → 23 behavioral engagement signals (required)
```

**Key Schema Constraints:**
| Field | Constraint |
|---|---|
| `candidate_id` | Pattern: `^CAND_[0-9]{7}$` |
| `years_of_experience` | 0–50 (float) |
| `current_company_size` | Enum: 8 tiers from "1-10" to "10001+" |
| `skill.proficiency` | Enum: beginner / intermediate / advanced / expert |
| `education.tier` | Enum: tier_1 / tier_2 / tier_3 / tier_4 / unknown |
| `notice_period_days` | 0–180 |
| `github_activity_score` | -1 to 100 (-1 means no GitHub) |
| `offer_acceptance_rate` | -1 to 1.0 (-1 means no prior offers) |

**Contribution to Challenge:**
- Defines every feature available for scoring.
- `redrob_signals` is a first-class object — explicitly modeled for behavioral scoring.
- `skill.duration_months` is a **trust signal** for skill authenticity (critical for anti-stuffing).
- `education.tier` is a pre-computed prestige tier (use carefully — not deterministic for this JD).

**Pitfalls:**
- `career_history` can have up to 10 roles — some may have `duration_months` inconsistent with `start_date`/`end_date` (honeypot signal).
- `years_of_experience` is a self-reported field and may not match actual career history dates.
- `skills` list has no maximum length enforced — keyword stuffers can list 20+ skills.

---

### 2. `candidates.jsonl`

**Purpose:** The full 100,000-candidate pool to be ranked. Line-delimited JSON (one record per line). ~465 MB uncompressed.

**Confirmed Stats (from full line count):**
- **Total records: 100,000**
- **File size: ~465 MB uncompressed**
- **Format: UTF-8 JSONL**

**From sampling (N=2,000):**

| Metric | Value |
|---|---|
| Mean experience | 7.0 years |
| Experience range | 1.0–15.0 years |
| Most common country | India (75.6% of sample) |
| Most common industry | IT Services |
| Most common title | Mechanical Engineer |
| Mean skills per candidate | 9.6 |
| Mean certs per candidate | ~0.5 |
| Open to work | 35.8% |

**Pitfalls:**
- Do NOT load all 100K records into memory at once — use streaming (line-by-line).
- At 465 MB, loading all into RAM is feasible (<2 GB) but parsing all at once takes ~20s. Streaming is safer and faster for feature extraction.
- Approximately ~18% of records in the sample had `salary_min > salary_max` — this is a **structural data anomaly** that may indicate honeypot candidates or data generation errors.

---

### 3. `sample_candidates.json`

**Purpose:** First 50 candidates from the pool, pretty-printed as a JSON array. Used for rapid schema inspection and honeypot hypothesis development.

**Key Observations from Sample:**
- Diverse titles including: Operations Manager, Business Analyst, Mechanical Engineer, Graphic Designer, HR Manager, Sales Executive, Content Writer, QA Engineer, Data Engineer, etc.
- Many candidates list highly AI-relevant skills (NLP, Fine-tuning LLMs, Milvus, Recommendation Systems) despite having **completely non-AI career histories** (e.g., QA Engineer with 2 years experience claiming "advanced" Recommendation Systems + 40 months usage).
- `open_to_work_flag=False` combined with high `applications_submitted_30d` (6–13 apps) appears in ~40% of sample — behavioral contradiction.
- **Found salary inversion** (min > max) in CAND_0000011 (min=15.5, max=13.9) — explicit honeypot signal.
- Career descriptions sometimes **internally contradict** the stated job title (e.g., candidate titled "QA Engineer" whose description describes "Android mobile development using Java/Kotlin").

**Contribution to Challenge:**
- Essential for building honeypot detection heuristics.
- Confirms that keyword stuffing is widespread — almost every non-AI candidate has some AI skills listed.
- Validates schema structure against real data.

---

### 4. `job_description.docx`

**Purpose:** The single Job Description against which all 100,000 candidates are ranked.

**Role:** Senior AI Engineer — Founding Team, Redrob AI (Series A)

**Key JD Metadata:**
| Field | Value |
|---|---|
| Company | Redrob AI |
| Location | Pune / Noida, India (Hybrid) |
| Experience | 5–9 years (range, not hard requirement) |
| Type | Full-time |

**Critical Hiring Philosophy (Explicit in JD):**
- Wants someone who can be both a **deep technical expert** AND a **scrappy shipper**.
- Tilts toward "shipper" over "researcher".
- **Disqualifiers explicitly stated:**
  1. Pure research background with no production deployment.
  2. AI experience is only LangChain/API wrapping from last 12 months.
  3. Senior engineer who hasn't written production code in 18+ months.
  4. Career entirely at consulting firms (TCS, Infosys, Wipro, Accenture, Cognizant, Capgemini).
  5. Primary expertise in CV/Speech/Robotics without NLP/IR exposure.
  6. 5+ years entirely on closed proprietary systems with no external validation.

**Technical Signals:**
- Must-have: Embeddings retrieval (sentence-transformers, BGE, E5), Vector DBs (Pinecone, Weaviate, Qdrant, Milvus, FAISS, OpenSearch), Strong Python, Ranking evaluation (NDCG, MRR, MAP).
- Nice-to-have: LLM fine-tuning (LoRA/QLoRA/PEFT), L2R models, HR-tech background, OSS contributions.
- Location: Pune/Noida preferred. Hyderabad, Mumbai, Delhi NCR acceptable. Non-India case-by-case (no visa sponsorship).
- Notice period: Sub-30 days ideal, ≤30 days can be bought out, >30 days reduces priority.

**The Explicit Hackathon Trap Warning (in JD itself):**
> *"The 'right answer' to this JD is not 'find candidates whose skills section contains the most AI keywords.' That's a trap we've explicitly built into the dataset."*

---

### 5. `README.docx`

**Purpose:** Participant onboarding guide explaining what's in the bundle and how to get started.

**Key Information Extracted:**
- The candidates file is `candidates.jsonl` (uncompressed ~465 MB) — **no `.gz` file present** in this bundle.
- Reading order recommended: JD → submission_spec → signals_doc → schema → sample candidates.
- Dataset explicitly contains traps: keyword stuffers, plain-language Tier 5s, behavioral twins, ~80 honeypots.
- **Submissions with honeypot rate > 10% in top 100 are disqualified.**
- **Three submissions maximum** — no live leaderboard.
- AI tools are permitted and must be declared honestly.

**Pitfall:**
- README references `.jsonl.gz` format but the actual file in the bundle is `.jsonl` (uncompressed). The Python loading code uses `gzip.open()` — this needs to be adjusted for the actual file format.

---

### 6. `submission_spec.docx`

**Purpose:** Complete rules for submission format, evaluation pipeline, compute constraints, and what to submit.

**Critical Rules:**

**Format:**
- File: `<participant_id>.csv` (UTF-8)
- Columns: `candidate_id, rank, score, reasoning`
- Exactly 100 data rows + 1 header
- Ranks 1–100, each used exactly once
- Scores must be **non-increasing** with rank
- Tie-break by `candidate_id` ascending

**Compute Constraints:**
| Constraint | Limit |
|---|---|
| Runtime | ≤ 5 minutes wall-clock |
| RAM | ≤ 16 GB |
| Compute | CPU only, no GPU |
| Network | Off — no external API calls |
| Disk | ≤ 5 GB intermediate state |

**Evaluation Metrics:**
| Metric | Weight | Description |
|---|---|---|
| NDCG@10 | 0.50 | Quality of top-10 picks |
| NDCG@50 | 0.30 | Quality of top-50 picks |
| MAP | 0.15 | Precision across all levels |
| P@10 | 0.05 | Fraction of top-10 that are relevant (tier 3+) |

**Final Score Formula:**
```
composite = 0.50 × NDCG@10 + 0.30 × NDCG@50 + 0.15 × MAP + 0.05 × P@10
```

> **Critical Insight:** NDCG@10 carries 50% of the score. Getting the **top 10 right** is the single most important optimization target.

**Stage Evaluation Pipeline:**
1. Format validation (auto)
2. Composite scoring (hidden ground truth)
3. Code reproduction + honeypot check (top-N submissions)
4. Manual review (reasoning quality, git history authenticity)
5. Defend-your-work interview (top finalists)

**What Gets You Eliminated:**
- Honeypot rate > 10% in top 100 → Stage 3 disqualification
- Cannot reproduce within 5min/16GB/no-GPU/no-network → Stage 3 disqualification
- Flat git history (single dump) → Stage 4 rejection
- Empty or templated reasoning → Stage 4 rejection
- Cannot explain architecture in interview → Stage 5 failure

**Reasoning Quality Checks (Stage 4):**
1. Specific facts from candidate profile
2. JD connection (not generic praise)
3. Honest concerns acknowledged
4. No hallucination (only claims in profile)
5. Variation (not templated)
6. Rank consistency (tone matches rank)

---

### 7. `redrob_signals_doc.docx`

**Purpose:** Reference document explaining all 23 behavioral signals in `redrob_signals`.

**Key Signals Summary:**

| # | Signal | Range | Key Insight |
|---|---|---|---|
| 1 | profile_completeness_score | 0–100 | Proxy for how serious the candidate is |
| 2 | signup_date | date | Platform tenure — long-term vs recent |
| 3 | last_active_date | date | **Critical** — stale candidates are functionally unavailable |
| 4 | open_to_work_flag | bool | **Critical** — explicit availability signal |
| 5 | profile_views_received_30d | int≥0 | Market demand for this candidate |
| 6 | applications_submitted_30d | int≥0 | Job-seeking intensity |
| 7 | recruiter_response_rate | 0–1 | **Critical** — responsiveness to hiring pipeline |
| 8 | avg_response_time_hours | float≥0 | Latency to respond — low = better |
| 9 | skill_assessment_scores | dict[str→0-100] | Platform-verified skill proficiency |
| 10 | connection_count | int≥0 | Network size — weak signal |
| 11 | endorsements_received | int≥0 | Social proof for skills |
| 12 | notice_period_days | 0–180 | Time-to-join — critical for urgency |
| 13 | expected_salary_range_inr_lpa | {min, max} | Salary fit — watch for inversions |
| 14 | preferred_work_mode | enum | Work arrangement fit |
| 15 | willing_to_relocate | bool | Location flexibility |
| 16 | github_activity_score | -1–100 | Technical activity (-1 = no GitHub) |
| 17 | search_appearance_30d | int≥0 | How often recruiters find them |
| 18 | saved_by_recruiters_30d | int≥0 | Market validation signal |
| 19 | interview_completion_rate | 0–1 | Reliability — shows up when scheduled |
| 20 | offer_acceptance_rate | -1–1 | Conversion reliability (-1 = no history) |
| 21 | verified_email | bool | Profile authenticity |
| 22 | verified_phone | bool | Profile authenticity |
| 23 | linkedin_connected | bool | External profile linkage |

**Key Explicit Warning (from doc):**
> *"A perfect-on-paper candidate who hasn't logged in for 6 months and has a 5% response rate is, for hiring purposes, not actually available."*

---

### 8. `submission_metadata_template.yaml`

**Purpose:** Template for the metadata YAML file that must accompany the code repository submission.

**Required Fields:**
- `team_name`, `primary_contact`, `team_members`
- `github_repo` (must be reachable)
- `sandbox_link` (HuggingFace Spaces, Streamlit Cloud, etc.)
- `reproduce_command` (single command that produces CSV from JSONL)
- `compute` (environment specs)
- `ai_tools_used` (honesty declaration)
- `methodology_summary` (≤200 words, strongly recommended)

**Notable Constraints:**
- `uses_gpu_for_inference: false` — mandatory
- `has_network_during_ranking: false` — mandatory
- `pre_computation_required` — allowed (e.g., embedding precompute outside the 5-min window)

**Pitfall:**
- `pre_computation_required` can be `true` — meaning you CAN pre-compute embeddings/indexes outside the 5-minute ranking window. The 5-minute limit applies only to the **ranking step** that produces the CSV.

---

### 9. `sample_submission.csv`

**Purpose:** Format reference only. Not a quality ranking — deliberately mixed titles to show CSV structure.

**Format Confirmed:**
```
candidate_id,rank,score,reasoning
CAND_XXXXXXX,1,0.9920,"<1-2 sentence reasoning>"
```

**Observations from Sample:**
- Reasoning format: `"<Title> with <X> yrs; <N> AI core skills; response rate <X>"`
- Score range in sample: 0.20–0.9920
- Top-ranked includes HR Managers, Content Writers, Graphic Designers — confirming the sample is NOT a quality ranking.
- Score is uniform-stepping (0.0080 per rank) — clearly algorithmic, not model-output scores.

**Critical Insight:** The sample submission is a **trap reference** — it ranks HR Managers and Content Writers at the top purely on skill count ("9 AI core skills") without any career-fit consideration. Do NOT use this as ranking inspiration.

---

### 10. `validate_submission.py`

**Purpose:** Local format validator to run before submission. Replicates server-side Stage 1 checks.

**Checks Performed:**
1. File extension must be `.csv`
2. Header row: exactly `candidate_id,rank,score,reasoning`
3. Exactly 100 data rows (non-empty)
4. Each `candidate_id` matches `CAND_[0-9]{7}` pattern
5. No duplicate `candidate_id`
6. `rank` is integer 1–100, no duplicates
7. All ranks 1–100 present exactly once
8. `score` is a valid float
9. Scores are **non-increasing** by rank
10. Tie-break: equal scores → `candidate_id` ascending

**Usage:**
```bash
python validate_submission.py my_team.csv
```

**Pitfall:** The validator does NOT check whether `candidate_id` values exist in `candidates.jsonl`. Typos in IDs will pass the validator but fail scoring.

---

## Cross-File Observations

### Hidden Architecture of the Challenge

Based on all files together, the challenge is structured around three layers:

**Layer 1 — Skill/Career Match (Primary Signal)**
The JD wants: embeddings retrieval, vector DBs, evaluation frameworks, product-company background. Most candidates in the pool are non-AI professionals with AI skill keywords bolted on. Skill match must be weighted by career history consistency.

**Layer 2 — Behavioral Availability (Multiplier)**
Even a perfect skill match is worthless if the candidate hasn't logged in for 6 months or has a 5% response rate. Behavioral signals should act as a **gate or multiplicative downweighter** on top of skill scores.

**Layer 3 — Honeypot Filtering (Elimination)**
~80 candidates have subtly impossible profiles. These must be caught and excluded from the top 100. A >10% honeypot rate in top 100 triggers disqualification.

### Scoring Priority Restatement

Given the 50% weight on NDCG@10:
- **Getting top 10 candidates right is worth more than anything else.**
- Optimization strategy should start with precision@10, then extend to @50.

### Key Anti-Patterns to Avoid

| Pattern | Why It Fails |
|---|---|
| Rank by AI skill count alone | HR Managers with 9 AI skills will dominate |
| Ignore career history | Marketing Managers with "Python" in skills will rank high |
| Ignore behavioral signals | Inactive candidates will appear available |
| Trust self-reported experience | Honeypots exploit this |
| Use only `years_of_experience` field | Doesn't capture relevance of experience |
| Call external APIs during ranking | Disqualified at Stage 3 |

---

## Constraints Summary Table

| Constraint | Source | Impact |
|---|---|---|
| CPU only, no GPU | submission_spec §3 | Forces lightweight models (BM25, TF-IDF, compact sentence-transformers) |
| ≤5 min runtime | submission_spec §3 | No per-candidate LLM inference |
| ≤16 GB RAM | submission_spec §3 | Must stream/batch process 465 MB JSONL |
| No external API calls | submission_spec §3 | All models must be local |
| 100 rows exactly | submission_spec §3 | Precisely 100 |
| Ranks 1–100 | submission_spec §3 | No 0-indexed ranks |
| Score non-increasing | submission_spec §3 | Must sort + deduplicate ties by candidate_id |
| Honeypot rate ≤10% | submission_spec §7 | Need honeypot detection |
| Reasoning must be specific | submission_spec §4 | Template reasoning will fail Stage 4 |
| GitHub repo required | submission_spec §10.3 | Real git history needed |
| Sandbox link required | submission_spec §10.5 | HuggingFace Spaces / Streamlit |
| ≤3 submissions | submission_spec §3 | Cannot iterate via submission |
