# Redrob AI — Intelligent Candidate Ranking Engine

End-to-end candidate discovery and ranking system built for the **Redrob India Runs Data & AI Challenge**. Given a job description, the engine scores and ranks up to 100,000 candidates using a hybrid pipeline of career trajectory analysis, skill taxonomy matching, behavioural signals, integrity detection, and semantic similarity.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the ranking pipeline (CLI — generates `outputs/submission.csv`)

```bash
python -m src.pipeline.ranker
```

Or use the exporter directly from Python:

```python
from src.pipeline.loader import load_candidates
from src.pipeline.ranker import rank_candidates
from src.pipeline.exporter import export_submission_csv
from src.features.career_scorer import load_taxonomies
from src.features.skill_scorer import load_skill_taxonomy
from src.config import CANDIDATES_JSONL

title_taxonomy, industry_taxonomy = load_taxonomies()
tier_a, tier_b, tier_c, _ = load_skill_taxonomy()

ranked = rank_candidates(
    load_candidates(CANDIDATES_JSONL),
    title_taxonomy=title_taxonomy,
    industry_taxonomy=industry_taxonomy,
    tier_a=tier_a, tier_b=tier_b, tier_c=tier_c,
    top_k=100,
)
export_submission_csv(ranked, "outputs/submission.csv", overwrite=True)
```

### 3. Start the FastAPI backend

```bash
uvicorn backend_api.app:app --reload
```

API available at `http://127.0.0.1:8000` — interactive docs at `/docs`.

### 4. Start the React frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at `http://localhost:5173`.

---

## Project Structure

```
src/                  Core ranking engine
  pipeline/           Loader, feature extractor, ranker, exporter, reasoning
  features/           Career, skill, behavioral, integrity, semantic scorers
  utils/              Date and text utilities
  config.py           Paths and constants

backend_api/          FastAPI service
  app.py              Application entrypoint
  routers/            Ranking, candidate, benchmark, pipeline endpoints
  schemas/            Pydantic request/response models
  services/           Pipeline orchestration and in-memory cache

frontend/             React + TypeScript dashboard
  src/pages/          Dashboard, PipelineVisualization, Candidates
  src/components/     Candidate table, preview, compare, layout
  src/api/            Typed API client

data/                 JD requirements and skill/title/industry taxonomies
outputs/              Generated submission.csv
tests/                Unit tests (pytest)
scripts/              Development and benchmarking utilities
docs/                 Architecture, feature engineering plan, roadmap
reports/              Dataset analysis and audit reports
```

---

## Validate Submission

```python
from src.pipeline.exporter import validate_submission, export_submission_csv
# validate_submission(ranked) returns a list of violations (empty = valid)
```

---

## Architecture

The ranking formula uses a weighted hybrid score:

```
final_score = 0.30 × career_score
            + 0.20 × skill_score
            + 0.15 × behavior_score
            + 0.10 × integrity_score
            + 0.10 × profile_integrity_score
            + 0.15 × semantic_score
```

Vetoed candidates (honeypot / fraud signals) are excluded before scoring. Keyword stuffing is penalised as a soft score multiplier. The top-K heap runs in O(N log K) time and O(K) memory.

See [`docs/architecture.md`](docs/architecture.md) for full design documentation.

---

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
```
