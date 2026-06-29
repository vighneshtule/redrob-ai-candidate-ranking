# Project Architecture
> **Challenge:** Redrob AI — Intelligent Candidate Discovery & Ranking  
> **Generated:** 2026-06-19

---

## Design Principles

1. **CPU-first, Memory-conscious:** All components must run within 5 minutes on a 16 GB CPU-only machine.
2. **Streaming over Bulk Loading:** Process `candidates.jsonl` line-by-line, not all-at-once in RAM.
3. **Interpretable by Design:** Every score must be traceable to specific candidate fields for the reasoning column and Stage 4 review.
4. **Modular and Testable:** Each scorer is an independent module with a consistent interface `(candidate_dict) → float`.
5. **Reproducible:** A single command `python rank.py --candidates ./candidates.jsonl --out ./submission.csv` reproduces the full output.

---

## Directory Structure

```
e:\Vighnesh\Redrob AI\
│
├── [PUB] India_runs_data_and_ai_challenge\     # Original challenge files (READ ONLY)
│   └── India_runs_data_and_ai_challenge\
│       ├── candidate_schema.json
│       ├── candidates.jsonl
│       ├── sample_candidates.json
│       ├── job_description.docx
│       ├── README.docx
│       ├── submission_spec.docx
│       ├── redrob_signals_doc.docx
│       ├── submission_metadata_template.yaml
│       ├── sample_submission.csv
│       └── validate_submission.py
│
├── src/                                         # Core source code
│   ├── __init__.py
│   ├── rank.py                                  # [ENTRY POINT] Main ranking script
│   ├── config.py                                # Centralized configuration + JD constants
│   │
│   ├── features/                                # Feature computation modules
│   │   ├── __init__.py
│   │   ├── skill_scorer.py                      # F1: Skill match features
│   │   ├── career_scorer.py                     # F2: Career relevance features
│   │   ├── behavioral_scorer.py                 # F3: Behavioral / availability features
│   │   ├── location_scorer.py                   # F4: Location & logistics features
│   │   ├── education_scorer.py                  # F5: Education features
│   │   └── integrity_scorer.py                  # F6: Honeypot + fraud detection
│   │
│   ├── pipeline/                                # Data processing pipeline
│   │   ├── __init__.py
│   │   ├── loader.py                            # Streaming JSONL reader + validator
│   │   ├── feature_extractor.py                 # Orchestrates all feature scorers
│   │   ├── ranker.py                            # Score aggregation + ranking
│   │   └── output_writer.py                     # CSV writer + reasoning generator
│   │
│   └── utils/                                   # Shared utilities
│       ├── __init__.py
│       ├── text_utils.py                        # Fuzzy matching, tokenization, NLP helpers
│       ├── date_utils.py                        # Date arithmetic, recency computation
│       └── validation.py                        # Schema validation helpers
│
├── data/                                        # Processed data and configuration
│   ├── jd_requirements.json                     # [GENERATED] Parsed JD into structured form
│   ├── skill_taxonomy.json                      # JD skill taxonomy (Tier-A/B/C)
│   ├── title_taxonomy.json                      # Career title taxonomy (Tier 1-4)
│   └── industry_taxonomy.json                   # Industry classification (product vs services)
│
├── docs/                                        # Documentation
│   ├── challenge_analysis.md                    # [THIS PROJECT] Complete challenge analysis
│   ├── feature_engineering_plan.md              # [THIS PROJECT] Feature design
│   ├── architecture.md                          # [THIS FILE] System architecture
│   └── roadmap.md                               # Implementation phases
│
├── reports/                                     # Analysis reports
│   ├── dataset_summary.md                       # [THIS PROJECT] Dataset statistics
│   ├── signals_analysis.md                      # [THIS PROJECT] Signal analysis table
│   └── honeypot_hypotheses.md                   # [THIS PROJECT] Honeypot patterns
│
├── notebooks/                                   # Jupyter notebooks for exploration
│   ├── 01_dataset_eda.ipynb                     # Exploratory data analysis
│   ├── 02_skill_taxonomy_builder.ipynb          # Build and test skill taxonomy
│   ├── 03_feature_calibration.ipynb             # Weight tuning on sample
│   └── 04_honeypot_analysis.ipynb               # Honeypot pattern investigation
│
├── outputs/                                     # Generated submission files
│   ├── submission.csv                           # Final submission
│   └── debug/                                   # Intermediate scoring outputs for debugging
│       ├── feature_scores.csv                   # Per-candidate per-feature scores
│       └── honeypot_flags.csv                   # Flagged candidates and reasons
│
├── tests/                                       # Unit tests
│   ├── test_skill_scorer.py
│   ├── test_career_scorer.py
│   ├── test_behavioral_scorer.py
│   ├── test_integrity_scorer.py
│   ├── test_pipeline.py
│   └── test_output_format.py
│
├── submission_metadata.yaml                     # Filled submission metadata (from template)
├── requirements.txt                             # Python dependencies
├── README.md                                    # Project README with reproduce command
└── Makefile                                     # Convenience commands
```

---

## Module Responsibilities

### `src/rank.py` — Entry Point

**Responsibility:** CLI entry point. Orchestrates the full pipeline from args to CSV output.

```
CLI: python rank.py --candidates ./path/to/candidates.jsonl --out ./submission.csv [--debug]
```

**Flow:**
1. Parse CLI arguments
2. Load JD requirements from `data/jd_requirements.json`
3. Load taxonomies from `data/`
4. Initialize all feature scorers
5. Stream candidates from JSONL via `pipeline/loader.py`
6. For each candidate: extract features → compute scores → aggregate
7. Sort by final_score descending
8. Apply tie-breaking (candidate_id ascending)
9. Select top 100
10. Generate reasoning strings
11. Write CSV via `pipeline/output_writer.py`
12. Validate output against submission spec

**Runtime target:** < 3 minutes for 100K candidates (leaving 2 min margin)

---

### `src/config.py` — Configuration

**Responsibility:** Single source of truth for all tuneable constants and JD-derived parameters.

```python
# JD-derived constants
JD_EXPERIENCE_TARGET_YEARS = 7.0
JD_EXPERIENCE_MIN_YEARS = 4.0
JD_EXPERIENCE_MAX_YEARS = 12.0
JD_PREFERRED_LOCATIONS = ["pune", "noida", "delhi ncr"]
JD_ACCEPTABLE_LOCATIONS = ["hyderabad", "mumbai", "bangalore", "bengaluru"]
JD_NOTICE_IDEAL_DAYS = 30
JD_NOTICE_ACCEPTABLE_DAYS = 90
JD_SALARY_ESTIMATED_MIN_LPA = 25.0
JD_SALARY_ESTIMATED_MAX_LPA = 60.0
NEGATIVE_COMPANIES = ["tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini"]
NEGATIVE_INDUSTRIES = ["IT Services"]

# Feature weights (must sum to 1.0)
WEIGHTS = {
    "skill_match": 0.25,
    "career_relevance": 0.35,
    "behavioral": 0.20,
    "location": 0.08,
    "education": 0.05,
    "integrity": 0.07,
}

# Honeypot threshold
HONEYPOT_VETO_THRESHOLD = 3

# Keyword stuffing penalty
STUFFING_PENALTY_THRESHOLD = 0.7
STUFFING_PENALTY_MULTIPLIER = 0.3
```

---

### `src/features/skill_scorer.py`

**Responsibility:** Compute all F1 skill-match features.

**Key Functions:**
- `compute_skill_match_score(candidate, jd_taxonomy)` → float [0, 1]
- `compute_skill_trust_score(candidate, jd_taxonomy)` → float [0, 1]
- `compute_assessment_score(candidate, jd_taxonomy)` → float [0, 1]
- `compute_skill_depth_score(candidate)` → float [0, 1]

**Dependencies:** `data/skill_taxonomy.json`, `src/utils/text_utils.py`

---

### `src/features/career_scorer.py`

**Responsibility:** Compute all F2 career relevance features.

**Key Functions:**
- `compute_title_relevance_score(candidate, title_taxonomy)` → float [0, 1]
- `compute_career_history_relevance(candidate, jd_keywords)` → float [0, 1]
- `compute_product_company_score(candidate, industry_taxonomy)` → float [0, 1]
- `compute_relevant_experience_score(candidate, title_taxonomy)` → float [0, 1]
- `compute_career_consistency_score(candidate)` → float [0, 1]

**Dependencies:** `data/title_taxonomy.json`, `data/industry_taxonomy.json`, `src/utils/text_utils.py`, `src/utils/date_utils.py`

---

### `src/features/behavioral_scorer.py`

**Responsibility:** Compute all F3 behavioral/availability features.

**Key Functions:**
- `compute_recency_score(candidate)` → float [0, 1]
- `compute_responsiveness_score(candidate)` → float [0, 1]
- `compute_availability_score(candidate)` → float [0, 1]
- `compute_notice_period_score(candidate)` → float [0, 1]
- `compute_platform_engagement_score(candidate)` → float [0, 1]
- `compute_offer_reliability_score(candidate)` → float [0, 1]

**Dependencies:** `src/utils/date_utils.py`

---

### `src/features/location_scorer.py`

**Responsibility:** Compute F4 location and logistics features.

**Key Functions:**
- `compute_location_score(candidate, config)` → float [0, 1]
- `compute_work_mode_score(candidate)` → float [0, 1]
- `compute_salary_fit_score(candidate, config)` → float [0, 1]

---

### `src/features/education_scorer.py`

**Responsibility:** Compute F5 education features.

**Key Functions:**
- `compute_education_tier_score(candidate)` → float [0, 1]
- `compute_education_field_score(candidate)` → float [0, 1]

---

### `src/features/integrity_scorer.py`

**Responsibility:** Compute F6 honeypot detection and keyword stuffing scores.

**Key Functions:**
- `compute_honeypot_score(candidate)` → int (anomaly points)
- `is_honeypot(candidate, threshold)` → bool
- `compute_stuffing_score(candidate, jd_taxonomy, title_taxonomy)` → float [0, 1]
- `compute_profile_integrity_score(candidate)` → float [0, 1]

**Critical:** This module is evaluated FIRST in the pipeline. Honeypots are immediately flagged and excluded before any expensive feature computation.

---

### `src/pipeline/loader.py`

**Responsibility:** Streaming JSONL reader with error handling and sampling support.

**Key Functions:**
- `stream_candidates(filepath, limit=None, sample_rate=None)` → generator
- `validate_candidate_schema(candidate)` → bool
- `count_lines_fast(filepath)` → int (uses wc or buffered read)

**Design note:** Must handle malformed lines gracefully (skip + log, not crash).

---

### `src/pipeline/feature_extractor.py`

**Responsibility:** Orchestrate all feature scorers for a single candidate. Returns a `FeatureVector` dataclass.

```python
@dataclass
class FeatureVector:
    candidate_id: str
    skill_match: float
    skill_trust: float
    assessment_score: float
    title_relevance: float
    career_history_relevance: float
    product_company_score: float
    relevant_experience: float
    career_consistency: float
    recency_score: float
    responsiveness_score: float
    availability_score: float
    notice_period_score: float
    engagement_score: float
    reliability_score: float
    location_score: float
    work_mode_score: float
    salary_score: float
    education_tier: float
    education_field: float
    honeypot_score: int
    stuffing_score: float
    integrity_score: float
    final_score: float
    is_excluded: bool
    exclusion_reason: str
```

---

### `src/pipeline/ranker.py`

**Responsibility:** Aggregate feature vectors into final scores, sort, and select top 100.

**Key Functions:**
- `aggregate_scores(feature_vector, weights)` → float
- `apply_veto_rules(feature_vector, config)` → float (applies honeypot/stuffing penalties)
- `rank_candidates(feature_vectors)` → List[FeatureVector] (sorted, top 100)
- `break_ties(candidates)` → List[FeatureVector] (tie-break by candidate_id ascending)

---

### `src/pipeline/output_writer.py`

**Responsibility:** Generate the submission CSV with reasoning strings.

**Key Functions:**
- `generate_reasoning(candidate, feature_vector)` → str
- `write_csv(ranked_candidates, candidates_raw, feature_vectors, output_path)` → None
- `validate_output(output_path)` → bool (calls validate_submission.py logic)

**Reasoning Template (Non-templated, Specific):**
```
f"{current_title} with {years:.1f}yrs relevant experience; 
  {n_matched} JD core skills including {top_skills}; 
  {behavioral_note}; located in {location}."
```

Where `behavioral_note` is contextual: 
- "active 3 days ago, 30d notice"
- "sub-30d notice, 0.82 recruiter response rate"
- "concern: 90-day notice period"

---

### `src/utils/text_utils.py`

**Responsibility:** Text processing for skill matching, career description relevance, title normalization.

**Key Functions:**
- `fuzzy_match_skill(skill_name, taxonomy, threshold=0.85)` → (match, score)
- `extract_jd_keywords(description_text)` → List[str]
- `compute_tfidf_relevance(text, keyword_list)` → float
- `normalize_title(title)` → str (lowercase, strip noise words)

**Design:** Use `rapidfuzz` for fuzzy matching (fast, CPU-efficient). Use `sklearn.feature_extraction.text.TfidfVectorizer` for TF-IDF relevance.

---

### `src/utils/date_utils.py`

**Responsibility:** Date arithmetic helpers.

**Key Functions:**
- `days_since(date_str)` → int
- `months_between(start_str, end_str)` → int
- `recency_decay(date_str, half_life_days=90)` → float [0, 1]
- `career_timeline_consistency(career_history)` → float [0, 1]

---

## Data Files

### `data/skill_taxonomy.json`

```json
{
  "tier_a": {
    "sentence-transformers": ["sentence transformers", "sbert", "sentence-bert"],
    "bge": ["bge", "bge-m3", "bge-large"],
    "e5": ["e5", "e5-large", "multilingual e5"],
    "pinecone": ["pinecone"],
    "weaviate": ["weaviate"],
    "qdrant": ["qdrant"],
    "milvus": ["milvus"],
    "faiss": ["faiss", "facebook ai similarity search"],
    "elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "hybrid-retrieval": ["hybrid search", "hybrid retrieval", "bm25", "dense retrieval"],
    "ndcg": ["ndcg", "normalized discounted cumulative gain"],
    "evaluation-frameworks": ["mrr", "map", "a/b testing", "offline evaluation", "retrieval evaluation"]
  },
  "tier_b": {
    "lora": ["lora", "qlora", "peft", "parameter efficient", "fine-tuning"],
    "learning-to-rank": ["ltr", "learning to rank", "lambdamart", "xgboost ranking"],
    "recommendation": ["recommendation systems", "recommender", "collaborative filtering"]
  },
  "tier_c": {
    "rag": ["rag", "retrieval augmented", "retrieval-augmented"],
    "embeddings": ["embeddings", "vector embeddings", "text embeddings"],
    "transformers": ["transformers", "hugging face", "bert", "roberta"],
    "pytorch": ["pytorch", "torch"],
    "nlp": ["nlp", "natural language processing", "text mining"]
  }
}
```

---

## Performance Budget

| Step | Estimated Time | Memory |
|---|---|---|
| Load JD + taxonomies | < 1s | ~50 MB |
| Stream + process 100K candidates | ~60–90s | ~500 MB peak |
| Score computation per candidate | ~0.3–0.5ms | negligible |
| Sort + rank | < 1s | ~100 MB |
| Generate reasoning + write CSV | < 5s | ~50 MB |
| **Total** | **~90–120 seconds** | **~700 MB peak** |

**Margin:** ~3 minutes remaining within the 5-minute budget.

---

## Technology Stack

| Component | Library | Reason |
|---|---|---|
| Fuzzy string matching | `rapidfuzz` | Fast, CPU-optimized, no GPU needed |
| TF-IDF / text relevance | `scikit-learn` | Mature, CPU-native |
| Data processing | `pandas` (light use) | Only for final sort/output |
| JSONL streaming | `json` (stdlib) | No overhead, memory-efficient |
| Date handling | `datetime` (stdlib) | No external deps |
| CSV output | `csv` (stdlib) | Matches validator expectations |
| Testing | `pytest` | Standard |

**Notable Exclusions:**
- No PyTorch / TensorFlow (too slow on CPU for 100K candidates)
- No LangChain (not needed for this architecture)
- No OpenAI/Anthropic APIs (prohibited)
- No Spark/Dask (overkill for 465 MB dataset)

---

## Testing Strategy

### Unit Tests
- Each feature scorer tested with synthetic candidate fixtures
- Edge cases: empty skills list, missing career history, all-null signals
- Honeypot detection tested against known-pattern fixtures

### Integration Tests
- Full pipeline run on `sample_candidates.json` (50 candidates)
- Output validation via `validate_submission.py`
- Performance benchmark: 2,000 candidates in < 10 seconds

### Local Validation
```bash
# Run full pipeline
python src/rank.py --candidates data/candidates.jsonl --out outputs/submission.csv

# Validate output
python validate_submission.py outputs/submission.csv

# Run tests
pytest tests/ -v
```
