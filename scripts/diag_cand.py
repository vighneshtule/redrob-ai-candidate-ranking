import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.loader import load_candidates
from src.config import CANDIDATES_JSONL
from src.pipeline.feature_extractor import extract_features
from src.features.career_scorer import load_taxonomies
from src.pipeline.ranker import rank_candidates
from datetime import datetime

def main():
    title_tax, industry_tax = load_taxonomies()
    today = datetime.utcnow().date()
    
    target_cands = []
    for raw in load_candidates(CANDIDATES_JSONL, validate=False):
        cid = raw["candidate_id"]
        if cid in ["CAND_0018499", "CAND_0041611", "CAND_0081846", "CAND_0000082"]:
            target_cands.append(raw)
            if len(target_cands) == 4:
                break
                
    from src.features.skill_scorer import load_taxonomies as load_skill_tax
    tier_a, tier_b, tier_c = load_skill_tax()
    features = [extract_features(c, title_tax, industry_tax, today, tier_b, tier_c) for c in target_cands]
    ranked = rank_candidates(features)
    
    for r in ranked:
        print(f"--- {r.candidate_id} ---")
        print(f"Final Score: {r.final_score}")
        print(f"Veto: {r.veto_candidate}")
        for k, v in r.feature_breakdown.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
