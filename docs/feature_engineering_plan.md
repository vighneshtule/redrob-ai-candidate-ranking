# Feature Engineering Plan
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Stage:** Design Only — NO implementation in this document  
> **Generated:** 2026-06-19

---

## Design Philosophy

The feature engineering strategy is guided by three principles from the JD and evaluation rules:

1. **Career > Keywords:** A candidate's *actual career history* in AI/ML outweighs their *skills list* by 3–5x. The skills list is too easily gamed.
2. **Availability Matters:** A technically perfect match who is inactive or unresponsive has zero practical hiring value. Behavioral signals must gate or discount the relevance score.
3. **Honeypot Resistance:** Every feature must be robust against profiles with inflated or fabricated signals. Trust signals (endorsements, assessment scores, duration_months) act as calibration.

---

## Feature Groups

| Group | Features | Weight Range |
|---|---|---|
| F1. Skill Match | 4 features | 25–30% of final score |
| F2. Career Relevance | 5 features | 30–35% of final score |
| F3. Behavioral / Availability | 6 features | 20–25% of final score |
| F4. Location & Logistics | 3 features | 5–8% of final score |
| F5. Education | 2 features | 3–5% of final score |
| F6. Honeypot / Fraud | 3 features | Hard gate (veto) |

---

## F1. Skill Match Features

### F1.1 — JD Core Skill Match Score

**Why it matters:**
The JD defines a clear technical stack (embeddings, vector DBs, evaluation frameworks, Python). Candidates who possess these skills in their profile are primary candidates for the role.

**How to calculate:**
1. Define a **JD Skills Taxonomy** with three tiers:
   - Tier-A (must-have): sentence-transformers, BGE, E5, Pinecone, Weaviate, Qdrant, Milvus, FAISS, OpenSearch, Elasticsearch, Python, NDCG, MRR, MAP, A/B testing, hybrid retrieval
   - Tier-B (nice-to-have): LoRA, QLoRA, PEFT, XGBoost LTR, LambdaMART, recommendation systems, NLP, LLM fine-tuning
   - Tier-C (adjacent): RAG, embeddings, transformers, Hugging Face, PyTorch, scikit-learn, search, ranking
2. For each skill in candidate's `skills` list:
   - Exact match to Tier-A → +3 points
   - Fuzzy match to Tier-A → +2 points
   - Match to Tier-B → +1.5 points
   - Match to Tier-C → +0.5 points
3. Normalize by total possible Tier-A score → [0, 1]

**Expected impact:** High — Primary discriminator for AI-relevant candidates.

**Anti-stuffing safeguards:**
- Weight by `skill.duration_months / max_duration` (longer use = more trusted)
- Cap per-skill contribution at `duration_months >= 6` threshold
- Apply proficiency multiplier: expert=1.0, advanced=0.85, intermediate=0.6, beginner=0.3

---

### F1.2 — Skill Trust Score

**Why it matters:**
Keyword stuffers list skills they've never actually used. `duration_months` and `endorsements` are authenticity signals.

**How to calculate:**
For each AI-relevant skill:
```
trust_score = (
    min(duration_months / 24, 1.0) * 0.6  +  # duration weight (capped at 2 years)
    min(endorsements / 20, 1.0) * 0.2      +  # social proof weight
    (assessment_score / 100) * 0.2            # platform assessment weight (if available)
)
```
Average across all JD-relevant skills claimed.

**Expected impact:** Medium — Reduces the score of keyword stuffers who claim skills with 0 duration.

---

### F1.3 — Assessment-Verified Skill Score

**Why it matters:**
`skill_assessment_scores` in `redrob_signals` is the **only objective, third-party verified** skill signal. A candidate with `NLP: 85` on a Redrob assessment is far more credible than one who just lists "NLP: expert" in their skills.

**How to calculate:**
1. Extract `skill_assessment_scores` dict from `redrob_signals`
2. Filter to keys that match JD-relevant skills (via fuzzy matching)
3. Mean score of all matching assessments, normalized to [0, 1]
4. If no assessments → 0.5 (neutral)

**Expected impact:** High — Strong differentiator. Beats keyword stuffing entirely.

---

### F1.4 — Skill Breadth vs Depth Balance

**Why it matters:**
The JD wants someone with *deep* expertise in specific areas (retrieval, ranking) not someone with surface-level exposure to 20 AI tools.

**How to calculate:**
```
depth_score = count(skills where proficiency in ['advanced', 'expert'] 
                    AND duration_months > 12) / count(JD_relevant_skills_listed)
```
High depth_score = quality depth. Low = broad but shallow.

**Expected impact:** Low-Medium — Tiebreaker between similarly skilled candidates.

---

## F2. Career Relevance Features

### F2.1 — Career Title Relevance Score

**Why it matters:**
This is the **single most important anti-stuffing feature**. A Marketing Manager who lists 9 AI skills must be ranked below a mid-level ML Engineer. The JD explicitly says "A candidate who has all the AI keywords listed as skills but whose title is 'Marketing Manager' is not a fit."

**How to calculate:**
1. Define a **Title Relevance Taxonomy** with four tiers:
   - Tier-1 (direct match): ML Engineer, AI Engineer, Senior ML Engineer, Research Engineer, NLP Engineer, Search Engineer, Ranking Engineer, Recommendation Systems Engineer, AI Specialist, Applied Scientist
   - Tier-2 (strong adjacent): Data Scientist, Senior Data Scientist, Backend Engineer (at AI company), Software Engineer (with ML focus)
   - Tier-3 (weak adjacent): Data Engineer, Analytics Engineer, Full Stack Developer, Cloud Engineer, DevOps Engineer, Software Engineer (general)
   - Tier-4 (negative signal): HR Manager, Marketing Manager, Sales Executive, Content Writer, Graphic Designer, Mechanical Engineer, Civil Engineer, Accountant, Customer Support, Project Manager, Business Analyst, Operations Manager
2. Score: Tier-1=1.0, Tier-2=0.6, Tier-3=0.3, Tier-4=0.0
3. Apply to BOTH `profile.current_title` AND each `career_history[].title`
4. Weight career history scores by recency (most recent = highest weight) and duration

**Expected impact:** **Very High** — This is the primary anti-keyword-stuffing mechanism.

---

### F2.2 — Career History Relevance Score

**Why it matters:**
Beyond title, the actual work described in each role gives deeper signal. A Data Engineer who built recommendation systems is more relevant than one who built ETL pipelines.

**How to calculate:**
For each `career_history` entry:
1. Apply TF-IDF or keyword matching against a JD keyword set to the `description` field
2. Score = weighted keyword match against JD terms: "retrieval", "ranking", "embedding", "recommendation", "search", "vector", "LLM", "production ML", "inference", "A/B test", "evaluation", "NDCG", etc.
3. Weight by `duration_months` (longer role = more relevant weight)
4. Sum across all career entries, normalize

**Expected impact:** High — Captures what candidates actually did vs just their title.

---

### F2.3 — Product Company Experience Score

**Why it matters:**
The JD explicitly excludes candidates from pure consulting firms (TCS, Infosys, Wipro, Accenture, Cognizant, Capgemini) and values product company experience. This is explicitly stated as a hiring filter.

**How to calculate:**
For each `career_history` entry:
1. Check `industry` field:
   - "IT Services" + large company size + known consulting firm name → penalty (-0.3)
   - "Software", "Fintech", "E-commerce", "AI/ML", "SaaS", "EdTech" + smaller company → bonus (+0.3)
2. Check `company_size`:
   - "1-10" to "201-500" at product company → startup bonus (+0.2)
   - "10001+" at IT Services → consulting penalty (-0.2)
3. Weight by recency

**Expected impact:** Medium-High — Important filter aligned with explicit JD requirement.

---

### F2.4 — Experience Relevance Score

**Why it matters:**
Raw `years_of_experience` is meaningless if those years were spent in Mechanical Engineering. Relevant experience years (in ML/AI/search/retrieval) is what matters.

**How to calculate:**
```
relevant_experience_months = sum(
    career_history[i].duration_months * career_title_relevance_score[i]
    for i in all career roles
)
relevant_years = relevant_experience_months / 12

# Map to JD fit (5-9 years ideal, with tolerance)
if 4 <= relevant_years <= 10:
    experience_score = 1.0 - abs(relevant_years - 7) / 7  # peak at 7 years
elif relevant_years < 2:
    experience_score = 0.2  # too junior
else:
    experience_score = max(0.3, 1.0 - abs(relevant_years - 7) / 10)
```

**Expected impact:** High — Directly measures years of relevant experience rather than total years.

---

### F2.5 — Career Consistency Score

**Why it matters:**
Honeypots and low-quality profiles often have inconsistent career histories (titles that don't progress logically, gaps, or contradictory descriptions). Consistent career arcs are a quality signal.

**How to calculate:**
1. **Timeline check:** Do career date ranges (start → end) sum to approximately `years_of_experience * 12` months? Penalize large gaps or overflows.
2. **Title progression:** Does the career show logical progression (Junior → Mid → Senior) rather than random jumps?
3. **Industry consistency:** Has the candidate stayed within related industries or made coherent transitions?
4. **Description-title match:** Semantic similarity between `career_history[i].title` and `career_history[i].description` content.

```
consistency_score = (
    timeline_consistency * 0.4 +
    progression_score * 0.3 +
    industry_coherence * 0.3
)
```

**Expected impact:** Medium — Strong honeypot detection mechanism. Lower consistency = likely fabricated or inconsistent profile.

---

## F3. Behavioral / Availability Features

### F3.1 — Recency / Activeness Score

**Why it matters:**
A candidate who hasn't logged in for 6 months is not actively looking and is unlikely to respond to outreach — regardless of how perfect their profile is.

**How to calculate:**
```
days_inactive = (today - last_active_date).days
recency_score = exp(-days_inactive / 90)  # 90-day half-life
# Scores: 0 days inactive → 1.0, 90 days → 0.37, 180 days → 0.14, 365 days → 0.02
```

**Expected impact:** High — This is a hard gate. Stale profiles should rank very low.

---

### F3.2 — Recruiter Responsiveness Score

**Why it matters:**
`recruiter_response_rate` and `avg_response_time_hours` together predict how likely a candidate is to engage with recruiters. Low responsiveness = wasted recruiting effort.

**How to calculate:**
```
response_score = (
    recruiter_response_rate * 0.7 +
    min(1.0, 24 / max(avg_response_time_hours, 1)) * 0.3
)
# Cap avg_response_time: 1h → 1.0, 24h → 0.5, 168h → 0.07
```

**Expected impact:** High — Predicts whether hiring pipeline can be completed.

---

### F3.3 — Availability Signal Score

**Why it matters:**
`open_to_work_flag` is the explicit availability declaration, but `applications_submitted_30d` and behavioral signals reveal actual job-seeking intent.

**How to calculate:**
```
availability_score = (
    open_to_work_flag * 0.6 +
    min(applications_submitted_30d / 5, 1.0) * 0.3 +
    (interview_completion_rate if interview_completion_rate > 0 else 0.5) * 0.1
)
```
Special case: if `open_to_work=False` but `applications_submitted_30d >= 5`, treat as 0.5 availability (hidden seeker).

**Expected impact:** Medium-High — Combines explicit and implicit availability signals.

---

### F3.4 — Notice Period Score

**Why it matters:**
The JD explicitly prefers sub-30-day notice. Long notice periods delay hiring — especially critical for a founding team role.

**How to calculate:**
```python
def notice_period_score(days):
    if days <= 15:   return 1.0
    elif days <= 30:  return 0.9
    elif days <= 60:  return 0.7
    elif days <= 90:  return 0.5
    elif days <= 120: return 0.3
    else:            return 0.1  # 120+ days = major penalty
```

**Expected impact:** Medium-High — Direct JD alignment. Sub-30 day notice is explicitly valued.

---

### F3.5 — Platform Engagement Score

**Why it matters:**
`github_activity_score`, `saved_by_recruiters_30d`, `profile_views_received_30d`, and `profile_completeness_score` together indicate how serious and engaged the candidate is.

**How to calculate:**
```
github_norm = max(github_activity_score, 0) / 100  # -1 → 0 (neutral, not negative)
engagement_score = (
    github_norm * 0.4 +
    min(saved_by_recruiters_30d / 5, 1.0) * 0.3 +
    profile_completeness_score / 100 * 0.3
)
```

**Expected impact:** Medium — Important for differentiating technically similar candidates. GitHub activity specifically aligns with JD's explicit OSS preference.

---

### F3.6 — Offer Reliability Score

**Why it matters:**
`interview_completion_rate` and `offer_acceptance_rate` predict whether a candidate will complete the hiring process and accept an offer — not just engage in early-stage outreach.

**How to calculate:**
```python
# -1 for offer_acceptance_rate means no history → neutral 0.5
offer_hist = 0.5 if offer_acceptance_rate == -1 else offer_acceptance_rate
interview_hist = interview_completion_rate if interview_completion_rate > 0 else 0.5

reliability_score = interview_hist * 0.6 + offer_hist * 0.4
```

**Expected impact:** Medium — Prevents wasting recruiter cycles on candidates who ghost.

---

## F4. Location & Logistics Features

### F4.1 — Location Fit Score

**Why it matters:**
The JD specifies Pune/Noida preferred, with Hyderabad/Mumbai/Delhi NCR acceptable, and non-India as case-by-case.

**How to calculate:**
```python
def location_score(location, country, willing_to_relocate):
    preferred_cities = ["pune", "noida", "delhi", "delhi ncr"]
    acceptable_cities = ["hyderabad", "mumbai", "bangalore", "bengaluru"]
    
    loc_lower = location.lower()
    
    if country != "India":
        return 0.2 if willing_to_relocate else 0.05
    
    for city in preferred_cities:
        if city in loc_lower:
            return 1.0
    for city in acceptable_cities:
        if city in loc_lower:
            return 0.75
    
    # Other Indian city
    return 0.5 if willing_to_relocate else 0.3
```

**Expected impact:** Medium — Location is a filter for the founding team role.

---

### F4.2 — Work Mode Compatibility Score

**Why it matters:**
The JD offers hybrid (Tue/Thu in office). Remote-only candidates are a moderate mismatch.

**How to calculate:**
```python
work_mode_scores = {
    "hybrid": 1.0,
    "flexible": 0.9,
    "onsite": 0.8,
    "remote": 0.4  # Moderate mismatch with hybrid requirement
}
```

**Expected impact:** Low — Secondary filter.

---

### F4.3 — Salary Fit Score

**Why it matters:**
If a candidate's salary expectations are wildly above what a Series A company typically offers, they may decline or not engage. Salary inversion is also a honeypot signal.

**How to calculate:**
```python
# Estimate Series A Senior AI Engineer range: 25–60 LPA
JD_SALARY_MIN = 25.0  # LPA
JD_SALARY_MAX = 60.0  # LPA

def salary_score(s_min, s_max):
    if s_min > s_max:  # inversion = data anomaly
        return 0.0  # honeypot flag — contributes to compound score
    
    overlap_min = max(s_min, JD_SALARY_MIN)
    overlap_max = min(s_max, JD_SALARY_MAX)
    
    if overlap_max < overlap_min:
        return 0.2  # no overlap
    
    overlap = overlap_max - overlap_min
    candidate_range = s_max - s_min
    return min(overlap / max(candidate_range, 5), 1.0)
```

**Expected impact:** Low-Medium — Mostly tiebreaker. Inversion flags contribute to honeypot scoring.

---

## F5. Education Features

### F5.1 — Education Tier Score

**Why it matters:**
The JD doesn't explicitly require tier-1 education, but it's a soft positive signal. The schema provides a pre-computed tier.

**How to calculate:**
```python
edu_tier_scores = {
    "tier_1": 1.0,
    "tier_2": 0.7,
    "tier_3": 0.4,
    "tier_4": 0.2,
    "unknown": 0.3
}
# Take max tier across all degrees
education_score = max(edu_tier_scores.get(e['tier'], 0.3) for e in education)
```

**Expected impact:** Low — Education tier is a secondary signal for this type of role.

---

### F5.2 — Education-Role Alignment Score

**Why it matters:**
A Computer Science or Data Science degree has more relevance to this role than a Civil Engineering degree.

**How to calculate:**
```python
relevant_fields = ["computer science", "data science", "mathematics", "statistics", 
                   "information technology", "machine learning", "artificial intelligence",
                   "software engineering", "engineering"]

def edu_field_score(field_of_study):
    fos = field_of_study.lower()
    for rf in relevant_fields:
        if rf in fos:
            return 1.0
    return 0.3

# Average across degrees
education_field_score = mean(edu_field_score(e['field_of_study']) for e in education)
```

**Expected impact:** Low — Secondary signal.

---

## F6. Honeypot / Data Integrity Features

### F6.1 — Honeypot Flag Score

**Why it matters:**
The challenge has ~80 honeypots. Any honeypot in the top 100 is penalized at evaluation. This is a **veto-level** feature — honeypot candidates must be eliminated, not just downweighted.

**How to calculate:**
Sum anomaly points from each detection hypothesis:

```python
def compute_honeypot_score(candidate):
    score = 0
    prof = candidate['profile']
    sig = candidate['redrob_signals']
    
    career_months = prof['years_of_experience'] * 12
    
    # H-F1: Skill duration exceeds career length
    for skill in candidate.get('skills', []):
        if skill.get('duration_months', 0) > career_months:
            score += 3
            break
    
    # H-B1: Salary inversion
    salary = sig['expected_salary_range_inr_lpa']
    if salary['min'] > salary['max']:
        score += 1
    
    # H-G1: Overlapping undergraduate degrees
    undergrad = [e for e in candidate.get('education', []) 
                 if 'B.' in e.get('degree', '')]
    if len(undergrad) >= 2:
        # Check for overlap
        for i in range(len(undergrad)):
            for j in range(i+1, len(undergrad)):
                if undergrad[i]['start_year'] < undergrad[j]['end_year'] and \
                   undergrad[j]['start_year'] < undergrad[i]['end_year']:
                    score += 2
    
    # H-C1: Expert/advanced skills with 0 duration
    zero_dur_expert = [s for s in candidate.get('skills', []) 
                       if s['proficiency'] in ['expert', 'advanced'] 
                       and s.get('duration_months', 1) == 0]
    if len(zero_dur_expert) >= 3:
        score += 2
    
    # H-A2: Experience vs career history mismatch
    total_hist_months = sum(h.get('duration_months', 0) 
                            for h in candidate.get('career_history', []))
    if abs(career_months - total_hist_months) > 24:
        score += 2
    
    return score

# Threshold: score >= 3 → suspected honeypot → exclude from top 100
```

**Expected impact:** **Critical (Veto)** — Must exclude honeypot candidates to avoid Stage 3 disqualification.

---

### F6.2 — Keyword Stuffing Score

**Why it matters:**
Non-honeypot but low-quality profiles that rank high via keyword matching must be penalized.

**How to calculate:**
```
stuffing_score = (
    count(AI_skills_listed) / count(all_skills_listed)  # AI skills ratio
    * (1 - career_title_relevance_score)                # Inverse of title match
)
# High stuffing_score = high ratio of AI skills on non-AI career = keyword stuffer
```

Candidates with `stuffing_score > 0.7` (many AI keywords, irrelevant career) get a penalty multiplier of 0.3 on their final score.

**Expected impact:** High — Primary protection against the most common attack vector.

---

### F6.3 — Profile Integrity Score

**Why it matters:**
Basic data consistency checks that flag unreliable profiles.

**How to calculate:**
Combine binary checks:
- Email verified (true/false)
- Phone verified (true/false)
- Profile completeness > 60%
- No salary inversion
- Career history has at least 1 role
- LinkedIn connected

```
integrity_score = sum([
    sig['verified_email'] * 0.2,
    sig['verified_phone'] * 0.2,
    (sig['profile_completeness_score'] > 60) * 0.3,
    (salary_min <= salary_max) * 0.2,
    (len(career_history) >= 1) * 0.1
])
```

**Expected impact:** Low — Tiebreaker and baseline data quality filter.

---

## Final Score Composition

```
final_score = (
    F1_skill_match          * 0.25  +  # Skill relevance + trust
    F2_career_relevance     * 0.35  +  # Title + history + product experience
    F3_behavioral           * 0.20  +  # Availability + responsiveness + notice
    F4_location_logistics   * 0.08  +  # Location + work mode + salary
    F5_education            * 0.05  +  # Tier + field
    F6_integrity            * 0.07     # Honeypot veto + stuffing penalty
)

# Veto: if honeypot_score >= 3: final_score = 0.0 (exclude from top 100)
# Penalty: if stuffing_score > 0.7: final_score *= 0.3
```

---

## Feature Implementation Priority

| Priority | Feature | Reason |
|---|---|---|
| P0 (Must) | F2.1 Career Title Relevance | Anti-stuffing core |
| P0 (Must) | F3.1 Recency Score | Anti-zombie core |
| P0 (Must) | F6.1 Honeypot Detection | Disqualification prevention |
| P1 (High) | F1.1 JD Core Skill Match | Primary skill signal |
| P1 (High) | F2.2 Career History Relevance | Career depth signal |
| P1 (High) | F3.2 Recruiter Responsiveness | Hiring pipeline signal |
| P1 (High) | F3.4 Notice Period Score | JD alignment |
| P2 (Medium) | F1.3 Assessment Verified Skills | Anti-stuffing enhancement |
| P2 (Medium) | F2.3 Product Company Score | JD explicit requirement |
| P2 (Medium) | F2.4 Relevant Experience Years | Experience quality |
| P2 (Medium) | F3.3 Availability Signal | Hiring readiness |
| P3 (Low) | F1.2 Skill Trust Score | Refinement |
| P3 (Low) | F2.5 Career Consistency | Honeypot detection |
| P3 (Low) | F3.5 Platform Engagement | Secondary signal |
| P4 (Tiebreaker) | F4-F5 all | Location/education/salary |
