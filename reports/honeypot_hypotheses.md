# Honeypot Hypotheses Report
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Source:** sample_candidates.json + candidates.jsonl (N=2,000 sample analysis)  
> **Generated:** 2026-06-19  

> **Disclaimer:** The patterns identified here are **hypotheses only**. We do NOT assume any specific candidate is a honeypot. These are suspicious indicators that warrant lower relevance scores. The ground truth is hidden and revealed only at evaluation time.

---

## Background

The challenge README explicitly states:
> *"The dataset contains a small number (~80) of honeypot candidates with subtly impossible profiles (e.g., 8 years of experience at a company founded 3 years ago; 'expert' proficiency in 10 skills with 0 years used). These are forced to relevance tier 0 in the ground truth. If your submission ranks honeypots in the top 10, this is a strong signal that your system isn't reading profiles — it's just doing keyword embedding."*
> 
> *"Submissions with honeypot rate > 10% in top 100 are disqualified."*

There are also **non-honeypot traps** — keyword stuffers, behavioral zombies, career-history contradictions — that should rank low but won't trigger disqualification the same way. Distinguishing honeypots from legitimate-but-poor candidates matters.

---

## Hypothesis Categories

### Category A — Timeline Impossibility Hypotheses

**Definition:** The candidate's career history contains dates that are chronologically impossible or internally inconsistent.

**Detection Method:** Calculate actual months from `start_date` to `end_date` and compare to stated `duration_months`. Significant mismatch (>3 months) is a flag.

**Observed in Sample:**

| Candidate | Anomaly | Detail |
|---|---|---|
| CAND_0000011 (QA Engineer) | Career description contradicts title | Title = "QA Engineer" but description says "Android mobile development using Java and Kotlin at a consumer-app company." |
| Multiple | Duration_months doesn't match date arithmetic | `start_date`=2024-03-08, `end_date`=null (current), `duration_months`=27 (plausible) vs cases where dates imply different math |

**Hypothesis H-A1:** Candidates where `(end_date - start_date)` in months differs from `duration_months` by >3 months are likely honeypots. The challenge document explicitly mentions "8 years of experience at a company founded 3 years ago" as an example.

**Hypothesis H-A2:** Candidates where `years_of_experience` at the profile level significantly exceeds the sum of all career history `duration_months` (>24 months gap) may have fabricated experience.

---

### Category B — Salary Inversion Hypotheses

**Definition:** `expected_salary_range_inr_lpa.min > expected_salary_range_inr_lpa.max`

**Observed Rate:** ~17.8% of first 2,000 records have inverted salary ranges.

**Examples Found:**
| Candidate | Min | Max |
|---|---|---|
| CAND_0000009 | 16.0 | 7.3 |
| CAND_0000011 | 15.5 | 13.9 |
| CAND_0000012 | 14.8 | 7.9 |
| CAND_0000013 | 11.6 | 8.1 |
| CAND_0000015 | 21.8 | 18.9 |
| CAND_0000017 | 13.8 | 8.4 |
| CAND_0000019 | 12.5 | 7.7 |
| CAND_0000022 | 12.3 | 8.5 |
| CAND_0000026 | 17.1 | 8.0 |
| ... | ... | ... |

**Important Caveat:** Rate of ~18% is far too high for only ~80 honeypots. This is likely a **data generation artifact** present in both honeypot and legitimate profiles. 

**Hypothesis H-B1:** Salary inversion is a necessary but not sufficient condition for honeypot classification. It should be combined with other anomaly flags.

**Hypothesis H-B2:** Salary inversion combined with timeline impossibility is a strong compound honeypot indicator.

---

### Category C — Skill Inflation Hypotheses

**Definition:** Candidates who list a large number of skills (>15) or claim high proficiency (advanced/expert) in skills with implausibly low usage duration.

**Challenge Document Quote:** *"'expert' proficiency in 10 skills with 0 years used"*

**Patterns to Check:**
1. Skill listed as `proficiency: "expert"` with `duration_months: 0`
2. Skill listed as `proficiency: "advanced"` with `duration_months: 0`
3. Total unique skills > 20 (above natural maximum)
4. Skills span incompatible domains simultaneously (e.g., both "Accounting" and "Fine-tuning LLMs" at advanced level)

**Observed in Sample:**

Candidate CAND_0000001 (Backend Engineer, Mindtree):
- Lists `Fine-tuning LLMs` (advanced, 36 months) + `Milvus` (advanced, 35 months) + `Speech Recognition` (advanced, 33 months) + `TTS` (advanced, 60 months)
- But career history is: "Backend Engineer → Analytics Engineer" in data pipelines
- **Pattern:** AI skill stuffing on a data engineering career history

Candidate CAND_0000011 (QA Engineer):
- Claims `Recommendation Systems: advanced, 40 months` and `Kubeflow: advanced, 59 months`
- But career: "QA Engineer → QA Engineer" for 2 years total
- Kubeflow for 59 months > total career length of 23 months → **impossible timeline**
- `skill_assessment_scores['Recommendation Systems'] = 29.8` (low score vs claimed "advanced")

**Hypothesis H-C1:** Candidates whose `skill.duration_months` for any single skill exceeds their `years_of_experience * 12` (total career months) are likely honeypots or keyword stuffers.

**Hypothesis H-C2:** Candidates with assessment scores < 40 on skills they claim as "advanced" or "expert" are likely keyword stuffers (not honeypots necessarily, but should rank lower).

**Hypothesis H-C3:** Candidates who claim >15 skills spanning incompatible domains (e.g., Graphic Design + Kubernetes + Fine-tuning LLMs + SAP + Accounting) are likely synthetic profiles.

---

### Category D — Career Description Contradiction Hypotheses

**Definition:** The `career_history[].description` field describes work fundamentally different from the stated `title` for that role.

**Observed Examples:**

**CAND_0000011 (QA Engineer):**
- `title: "QA Engineer"` at Pied Piper
- `description: "Android mobile development using Java and (more recently) Kotlin at a consumer-app company. Built and maintained multiple production features including the main shopping flow, push notification system, and the offline-first sync layer."`
- **Hypothesis:** Either the title is wrong, the description is wrong, or this is a deliberately injected inconsistency (honeypot/trap).

**General Pattern:** Candidates whose `profile.current_title` does not match the nature of work described in `career_history[0].description` (the most recent role).

**Hypothesis H-D1:** Candidates where the current role title is semantically unrelated to the current role description (e.g., "QA Engineer" doing mobile development) are likely honeypots or test cases for keyword robustness.

**Hypothesis H-D2:** Candidates where the `profile.current_industry` is significantly different from the industry that matches their title/description (e.g., an "ML Engineer" listed in "Paper Products" industry) are likely synthetic profiles.

---

### Category E — Behavioral Contradiction Hypotheses

**Definition:** Behavioral signals that contradict each other in ways that real candidates wouldn't exhibit.

**Observed Pattern — Not Open, Still Applying:**
In the 50-candidate sample, ~40% of candidates had `open_to_work_flag: false` but `applications_submitted_30d: 6+`. This is:
- Common enough to be a real pattern (stealth job-seeking = realistic)
- But extreme values (13+ applications while not marked open) are suspicious

**Candidates with Extreme Contradiction:**
| Candidate | Title | Open to Work | Applications 30d |
|---|---|---|---|
| CAND_0000010 | Data Engineer | False | 13 |
| CAND_0000018 | Frontend Engineer | False | 11 |
| CAND_0000003 | Customer Support | False | 9 |

**Hypothesis H-E1:** `open_to_work_flag=False` with `applications_submitted_30d > 10` is a behavioral trap or honeypot signal. Treat as neutral (not upweight open_to_work) but do not use applications count to elevate these candidates.

**Hypothesis H-E2:** Candidates with `recruiter_response_rate` very close to 0.0 (< 0.05) combined with `applications_submitted_30d > 5` exhibit contradictory hiring pipeline behavior and may be synthetic.

---

### Category F — Impossible Skill Duration Hypotheses

**Definition:** A skill's claimed `duration_months` is greater than what's possible given the candidate's total career or experience timeline.

**CAND_0000011 Example:**
- `years_of_experience: 2.0` (total: ~24 months)
- `Kubeflow: advanced, duration_months: 59` (**59 > 24 — impossible**)
- `Recommendation Systems: advanced, duration_months: 40` (**40 > 24 — impossible**)

**Hypothesis H-F1:** Any candidate where `skill.duration_months > years_of_experience * 12` for any skill is a **strong honeypot candidate**. This is mathematically impossible for self-consistent profiles.

**Hypothesis H-F2:** Candidates with multiple skills exceeding career length are more likely honeypots than those with just one (data entry error vs systematic fabrication).

---

### Category G — Education Inconsistency Hypotheses

**Definition:** Education dates that overlap impossibly or degrees that conflict with each other.

**CAND_0000011 Example:**
- Degree 1: Chandigarh University, B.Tech, 2014–2019 (5 years)
- Degree 2: Anna University, B.Sc, 2015–2020 (5 years, overlapping with Degree 1)
- **Both are full-time undergraduate degrees overlapping by 4 years**

**Hypothesis H-G1:** Candidates with two simultaneous full-time undergraduate degrees (overlapping start–end years) are likely honeypots with fabricated education histories.

**Hypothesis H-G2:** Candidates whose education `end_year` is later than 2026 (the current year) for non-ongoing programs are likely synthetic.

---

### Category H — AI Profile Over-Optimization Hypotheses

**Definition:** Candidates who appear to be "perfect AI Engineer profiles" but their career history doesn't support it — likely designed to fool keyword-based rankers.

**Pattern Observed:**
Candidates across non-AI roles (HR Manager, Marketing Manager, Content Writer) who list 8–10 AI-specific skills with high proficiency:
- "NLP: expert, 60 months"
- "Vector Databases: advanced, 48 months"
- "Fine-tuning LLMs: advanced, 36 months"

...but their entire career history describes non-AI work.

**Hypothesis H-H1:** Candidates whose `profile.current_title` AND entire `career_history[].title` show non-AI roles, but whose `skills` list contains >5 AI-specific skills (from a defined AI skills taxonomy), are **keyword stuffers** (not necessarily honeypots but should rank very low).

**Hypothesis H-H2:** The most dangerous version of this pattern (for the system) is a candidate with ALL of: correct AI skills listed, reasonable experience, good behavioral signals — but a career history in a completely unrelated field. These are the "Tier 5" behavioral twins mentioned in the README.

---

## Compound Honeypot Scoring System (Hypothesis)

A candidate's honeypot probability can be estimated by summing anomaly flags:

| Flag | Points |
|---|---|
| `skill.duration_months > profile.years_of_experience * 12` (any skill) | +3 |
| `expected_salary_range_inr_lpa.min > max` | +1 |
| Two overlapping full-time undergraduate degrees | +2 |
| Career description contradicts job title | +2 |
| `years_of_experience` vs career history sum mismatch > 24 months | +2 |
| 3+ skills with `proficiency=expert/advanced` AND `duration_months=0` | +2 |
| Total skills > 20 | +1 |
| `open_to_work=False` AND `applications_30d > 10` | +1 |

**Thresholds:**
- Score ≥ 3: Treat as suspected honeypot → exclude from top 100
- Score 1–2: Treat as keyword stuffer → significant downweight
- Score 0: No anomaly flags

---

## Summary of Suspicious Pattern Frequencies

| Hypothesis | Estimated Frequency in 100K |
|---|---|
| H-B1 (Salary inversion) | ~17,800 candidates |
| H-F1 (Skill duration > career months) | ~3,000–5,000 candidates (estimate) |
| H-H1 (Non-AI career + many AI skills) | ~30,000–40,000 candidates |
| H-G1 (Overlapping full degrees) | ~500–2,000 candidates (estimate) |
| H-C1 (>15 skills) | ~1,000–3,000 candidates (estimate) |
| True honeypots (per challenge) | ~80 candidates |

**Key Takeaway:** Most anomalies are keyword stuffers or data artifacts — not true honeypots. The compound scoring approach (requiring multiple flags) is the most reliable honeypot detection strategy without over-excluding legitimate candidates.
