# Dataset Summary Report
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Generated:** 2026-06-19 | **Analysis basis:** Full 100K line count + 2,000-record sample

---

## 1. Dataset Overview

| Metric | Value |
|---|---|
| Total candidates | **100,000** |
| File format | JSONL (UTF-8, one record per line) |
| File size | ~465 MB uncompressed |
| Sample analyzed | First 2,000 records |
| Sample candidates (pretty-printed) | 50 (sample_candidates.json) |

---

## 2. Experience Distribution

### Histogram (from N=2,000 sample)

| Experience Bracket | Count | % of Sample |
|---|---|---|
| 0–2 years | 148 | 7.4% |
| 2–4 years | 364 | 18.2% |
| 4–6 years | 365 | 18.3% |
| 6–8 years | 363 | 18.2% |
| 8–10 years | 291 | 14.6% |
| 10–12 years | 203 | 10.2% |
| 12–14 years | 175 | 8.8% |
| 14–16 years | 91 | 4.6% |

**Statistics:**
- **Min:** 1.0 years
- **Max:** 15.0 years
- **Mean:** 7.0 years
- **Median (estimated):** ~6.5 years

**Insight:** Experience is broadly distributed. The JD target of 5–9 years covers roughly **50% of the pool**. This means raw experience alone is not a useful discriminator — career quality and role relevance are the real signals.

---

## 3. Country Distribution (N=2,000 sample)

| Country | Count | % |
|---|---|---|
| **India** | 1,512 | **75.6%** |
| USA | 183 | 9.2% |
| Australia | 59 | 3.0% |
| Singapore | 52 | 2.6% |
| Canada | 49 | 2.5% |
| UK | 49 | 2.5% |
| UAE | 48 | 2.4% |
| Germany | 48 | 2.4% |

**Insight:**
- 75.6% of candidates are India-based — highly relevant for this role (Pune/Noida preferred).
- Non-India candidates (24.4%) need relocation signal check (`willing_to_relocate`).
- No visa sponsorship offered → non-India candidates should be down-weighted significantly unless they have strong alternative signals.

---

## 4. Industry Distribution (N=2,000 sample)

| Industry | Count | % |
|---|---|---|
| IT Services | 591 | 29.6% |
| Manufacturing | 447 | 22.4% |
| Software (Product) | 440 | 22.0% |
| Paper Products | 152 | 7.6% |
| Conglomerate | 140 | 7.0% |
| Fintech | 67 | 3.4% |
| Food Delivery | 55 | 2.8% |
| Consulting | 33 | 1.7% |
| E-commerce | 31 | 1.6% |
| EdTech | 15 | 0.8% |
| Gaming | 6 | 0.3% |
| AI/ML | 4 | 0.2% |
| HealthTech | 4 | 0.2% |
| SaaS | 3 | 0.2% |

**Insight:**
- ~30% of candidates are in IT Services (TCS, Infosys-type companies) — **explicitly negatively flagged** in the JD.
- Only ~22% are in product software companies — the preferred background.
- "Paper Products" and "Conglomerate" are clearly filler/synthetic industries injected into the dataset (likely from using Dunder Mifflin, Hooli, etc. as fake company names).
- `AI/ML` industry has only 4 candidates in sample — extremely rare but highest signal-value.

---

## 5. Current Title Distribution (Top 30, N=2,000 sample)

| Title | Count | Relevant to JD? |
|---|---|---|
| Mechanical Engineer | 124 | ❌ No |
| Graphic Designer | 121 | ❌ No |
| Business Analyst | 119 | ❌ No |
| Customer Support | 118 | ❌ No |
| HR Manager | 117 | ❌ No |
| Marketing Manager | 115 | ❌ No |
| Sales Executive | 113 | ❌ No |
| Civil Engineer | 111 | ❌ No |
| Project Manager | 107 | ❌ No |
| Operations Manager | 106 | ❌ No |
| Content Writer | 104 | ❌ No |
| Accountant | 99 | ❌ No |
| Software Engineer | 70 | ⚠️ Maybe (context needed) |
| QA Engineer | 67 | ⚠️ Maybe |
| Frontend Engineer | 64 | ⚠️ Weak |
| DevOps Engineer | 64 | ⚠️ Weak |
| Java Developer | 60 | ⚠️ Weak |
| Mobile Developer | 56 | ❌ No (per JD — CV/mobile not relevant) |
| Full Stack Developer | 55 | ⚠️ Weak |
| Cloud Engineer | 45 | ⚠️ Weak |
| .NET Developer | 39 | ❌ No |
| Analytics Engineer | 19 | ⚠️ Maybe (data adjacent) |
| Data Analyst | 18 | ⚠️ Weak |
| Data Engineer | 17 | ⚠️ Data adjacent |
| Backend Engineer | 16 | ⚠️ Maybe |
| Senior Software Engineer | 15 | ⚠️ Maybe |
| Senior Data Engineer | 13 | ⚠️ Weak |
| ML Engineer | 6 | ✅ Strong |
| AI Specialist | 5 | ✅ Strong |
| Data Scientist | 5 | ⚠️ Maybe |

**Critical Observation:**
- The vast majority of title types (~80% of the pool) are **non-AI professionals**.
- True AI/ML titles (ML Engineer, AI Engineer, AI Specialist, Senior ML Engineer) appear in only ~1% of sample.
- The pool is designed to challenge keyword-based ranking — a Marketing Manager can list 9 AI skills and fool a naive ranker.

---

## 6. Top 50 Most Common Skills (N=2,000 sample)

| Rank | Skill | Count | AI-Relevant? |
|---|---|---|---|
| 1 | Data Pipelines | 275 | ⚠️ Adjacent |
| 2 | JavaScript | 270 | ❌ No |
| 3 | Databricks | 265 | ⚠️ Data |
| 4 | Content Writing | 264 | ❌ No |
| 5 | Illustrator | 259 | ❌ No |
| 6 | SEO | 258 | ❌ No |
| 7 | Terraform | 258 | ❌ No |
| 8 | Java | 258 | ❌ No |
| 9 | Salesforce CRM | 258 | ❌ No |
| 10 | HTML | 257 | ❌ No |
| 11 | Agile | 257 | ❌ No |
| 12 | Docker | 257 | ⚠️ Infra |
| 13 | Apache Flink | 256 | ⚠️ Data |
| 14 | gRPC | 256 | ⚠️ Infra |
| 15 | Snowflake | 255 | ⚠️ Data |
| 16 | Redis | 254 | ⚠️ Infra |
| 17 | SAP | 251 | ❌ No |
| 18 | AWS | 249 | ⚠️ Cloud |
| 19 | TypeScript | 248 | ❌ No |
| 20 | PostgreSQL | 248 | ❌ No |
| 21 | Flask | 247 | ⚠️ Backend |
| 22 | Accounting | 246 | ❌ No |
| 23 | Kubernetes | 246 | ⚠️ Infra |
| 24 | Spark | 246 | ⚠️ Data |
| 25 | Kafka | 245 | ⚠️ Data |
| 26 | SQL | 245 | ❌ No (too generic) |
| 27 | Rust | 245 | ❌ No |
| 28 | Azure | 244 | ⚠️ Cloud |
| 29 | Sales | 243 | ❌ No |
| 30 | Django | 242 | ❌ No |
| 31 | React | 241 | ❌ No |
| 32 | Scrum | 241 | ❌ No |
| 33 | dbt | 239 | ⚠️ Data |
| 34 | Excel | 237 | ❌ No |
| 35 | REST APIs | 237 | ⚠️ Backend |
| 36 | Spring Boot | 236 | ❌ No |
| 37 | Webpack | 235 | ❌ No |
| 38 | Next.js | 235 | ❌ No |
| 39 | Vue.js | 234 | ❌ No |
| 40 | Tailwind | 233 | ❌ No |
| 41 | Redux | 233 | ❌ No |
| 42 | GraphQL | 232 | ❌ No |
| 43 | ETL | 232 | ⚠️ Data |
| 44 | Apache Beam | 231 | ⚠️ Data |
| 45 | Node.js | 231 | ❌ No |
| 46 | CSS | 231 | ❌ No |
| 47 | GCP | 230 | ⚠️ Cloud |
| 48 | Airflow | 230 | ⚠️ Data |
| 49 | Project Management | 229 | ❌ No |
| 50 | MongoDB | 227 | ❌ No |

**Key Observation:** The top 50 skills are dominated by general software engineering and non-AI skills. Skills like NLP, embeddings, vector databases, and fine-tuning appear rarely in the top list but are the critical discriminators. This confirms the keyword-stuffing problem: AI skills appear across many profiles but are secondary skills listed by non-AI professionals.

---

## 7. Education Tier Distribution (N=2,000 sample)

| Tier | Count | % | Description |
|---|---|---|---|
| tier_1 | 137 | 6.6% | Premier institutions (IITs, IISc, top global) |
| tier_2 | 584 | 28.2% | Good regional universities (NITs, well-known private) |
| tier_3 | 1,056 | 51.0% | Mid-tier institutions |
| tier_4 | 1,056 | 51.0% | Lower-tier institutions |
| unknown | 0 | 0% | — |

**Note:** Multiple degrees per candidate — totals exceed 2,000.

**Insight:**
- Only ~7% have tier_1 education. The JD does not explicitly require it — education tier is a soft signal.
- Tier_3/4 candidates with strong product-company career history should still rank above tier_1 candidates in non-AI roles.
- Education tier should be a **secondary tiebreaker**, not a primary discriminator.

---

## 8. Skills Per Candidate

| Metric | Value |
|---|---|
| Minimum skills | 5 |
| Maximum skills | 23 |
| Mean skills | 9.6 |

**Insight:** High skill count (>15) is a potential keyword-stuffing signal. The distribution suggests a natural range of 5–12 skills per authentic profile. Skills beyond 15 warrant additional scrutiny of `duration_months` values.

---

## 9. Certifications Per Candidate (N=2,000)

| Cert Count | Candidates | % |
|---|---|---|
| 0 | 1,477 | 73.9% |
| 1 | 252 | 12.6% |
| 2 | 271 | 13.6% |

**Insight:** Most candidates have no certifications. Certifications are present in ~26% of profiles and can serve as a signal for specific technical domains when issuer is relevant (e.g., AWS ML Specialty, Google Professional ML Engineer).

---

## 10. Work Mode Preferences (N=2,000)

| Mode | Count | % |
|---|---|---|
| Remote | 505 | 25.3% |
| Onsite | 499 | 25.0% |
| Flexible | 498 | 24.9% |
| Hybrid | 498 | 24.9% |

**Insight:** Near-uniform distribution across work modes — likely synthetically generated. The JD offers Hybrid (Tue/Thu offices) with flexibility. Candidates preferring `onsite` or `flexible` or `hybrid` are all compatible. `remote`-only candidates may be a slight mismatch.

---

## 11. Candidate Availability Signals (N=2,000)

| Signal | Value |
|---|---|
| Open to work = Yes | 35.8% |
| Open to work = No | 64.2% |
| Notice period (mean) | ~78.6 days (from 50-sample) |
| Notice period range | 30–150 days (from 50-sample) |

**Insight:**
- Only 36% explicitly flagged as open to work — but platform engagement (last_active_date, applications, response_rate) is more predictive of actual availability.
- Mean notice of ~78 days is above the JD's preferred sub-30-day threshold. Short notice (0–30 days) is a differentiator.

---

## 12. Data Quality Anomalies (N=2,000)

| Anomaly Type | Count | Rate |
|---|---|---|
| Salary min > max (inverted range) | ~356 | ~17.8% |
| Career description contradicts title | Multiple | Qualitative |
| Not open to work + submitting 6+ applications | ~40% of sample-50 | Common |
| Skill proficiency mismatch with duration | To be quantified | Honeypot signal |

**Critical Finding:** ~18% of candidates have inverted salary ranges (min > max). This is too frequent to be purely honeypots (~80 known honeypots). It likely represents a **data generation artifact** present in both real and honeypot profiles. Use this signal as a **partial honeypot indicator** combined with other flags, not in isolation.

---

## 13. Projected Extrapolation to Full 100K

Based on 2% sample (N=2,000):

| Category | Estimated Count in 100K |
|---|---|
| India-based candidates | ~75,600 |
| IT Services industry | ~29,600 |
| Product software industry | ~22,000 |
| True ML/AI titles | ~500–1,000 |
| Open to work | ~35,800 |
| Tier-1 education | ~6,600 |
| Candidates with honeypot-like flags | ~8,000–15,000 |

**The target pool of genuinely qualified candidates (matching JD):** Estimated 200–800 truly strong matches out of 100K. The ranking task is to surface the top 100 from this small group.
