import sys
import os
import time
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.loader import load_candidates
from src.features.career_scorer import load_taxonomies
from src.features.skill_scorer import load_skill_taxonomy
from src.pipeline.ranker import rank_candidates_parallel
from src.pipeline.exporter import export_submission_csv, validate_submission
from src.config import CANDIDATES_JSONL

TOP_K = 100

def generate_submission():
    print("Loading resources...")
    title_tax, industry_tax = load_taxonomies()
    tier_a, tier_b, tier_c, _ = load_skill_taxonomy()
    
    print("Loading all candidates...")
    candidates = list(load_candidates(CANDIDATES_JSONL, validate=False))
    print(f"Loaded {len(candidates)} candidates.")
    
    print("Running parallel ranking pipeline on all candidates...")
    t0 = time.perf_counter()
    ranked = rank_candidates_parallel(
        candidates, 
        title_tax, 
        industry_tax, 
        tier_a, tier_b, tier_c, 
        top_k=TOP_K
    )
    t1 = time.perf_counter()
    print(f"Ranking complete in {t1 - t0:.2f} seconds.")
    
    # Validation
    violations = validate_submission(ranked)
    if violations:
        print("Validation FAILED!")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    
    print("Validation passed. Exporting submission.csv...")
    out_path = ROOT / "outputs" / "submission.csv"
    export_submission_csv(ranked, out_path, overwrite=True)
    print(f"Successfully generated {out_path}")
    
    print("\n--- TOP 10 CANDIDATES ---")
    for r in ranked[:10]:
        print(f"Rank {r.rank}: {r.candidate_id} (Score: {r.final_score:.6f})")
    
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    generate_submission()
