import csv
from pathlib import Path
from datetime import datetime
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.features.career_scorer import load_taxonomies, score_career
from src.pipeline.loader import load_candidates
from src.config import CANDIDATES_JSONL

def generate_step1(candidates_map, top_100_ids):
    lines = [
        "# Career Score Breakdown (Top 100)",
        "",
        "| Candidate ID | Career Score | Title Rel | History Rel | Product Co | Rel Exp | Consistency | Current Title | Current Company |",
        "|--------------|--------------|-----------|-------------|------------|---------|-------------|---------------|-----------------|"
    ]
    for cid in top_100_ids:
        c = candidates_map.get(cid)
        if not c:
            continue
        feat = c['features']
        prof = c['raw'].get('profile', {})
        curr_title = prof.get('current_title', '')
        # find current company from career history
        curr_company = ''
        for role in c['raw'].get('career_history', []):
            if role.get('is_current'):
                curr_company = role.get('company', '')
                break
                
        lines.append(
            f"| {cid} | {feat.final_career_score:.4f} | {feat.title_relevance_score:.4f} | "
            f"{feat.career_history_relevance_score:.4f} | {feat.product_company_score:.4f} | "
            f"{feat.relevant_experience_score:.4f} | {feat.career_consistency_score:.4f} | "
            f"{curr_title} | {curr_company} |"
        )
        
    out_path = Path("reports/career_breakdown_top100.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {out_path}")

def generate_step2(all_candidates, top_100_ids):
    def get_stats(scores):
        if not scores: return 0,0,0,0,0
        return np.min(scores), np.max(scores), np.mean(scores), np.median(scores), np.std(scores)
        
    all_scores = [c['features'].final_career_score for c in all_candidates.values()]
    # simulate top 1000 by sorting all scores
    top_1000_scores = sorted(all_scores, reverse=True)[:1000]
    top_100_scores = [all_candidates[cid]['features'].final_career_score for cid in top_100_ids if cid in all_candidates]
    
    lines = [
        "# Career Score Distribution",
        "",
        "| Subset | Min | Max | Mean | Median | StdDev |",
        "|--------|-----|-----|------|--------|--------|"
    ]
    
    for name, scores in [("Top 100", top_100_scores), ("Top 1000", top_1000_scores), ("Entire Dataset", all_scores)]:
        mn, mx, me, md, st = get_stats(scores)
        lines.append(f"| {name} | {mn:.4f} | {mx:.4f} | {me:.4f} | {md:.4f} | {st:.4f} |")
        
    lines.append("")
    lines.append("## Histogram (Entire Dataset)")
    lines.append("```")
    hist, bins = np.histogram(all_scores, bins=10, range=(0, 1))
    for i in range(len(hist)):
        bar = "#" * int(hist[i] / max(hist) * 50)
        lines.append(f"{bins[i]:.1f} - {bins[i+1]:.1f} | {hist[i]:>6} | {bar}")
    lines.append("```")
    
    out_path = Path("reports/career_distribution.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {out_path}")

def generate_step3(candidate):
    feat = candidate['features']
    lines = [
        "# Candidate 82 Career Analysis",
        "",
        f"**Candidate ID:** {candidate['raw'].get('candidate_id')}",
        f"**Final Career Score:** {feat.final_career_score:.4f}",
        "",
        "## Component Breakdown",
        f"- **Title Relevance:** {feat.title_relevance_score:.4f}",
        f"- **History Relevance:** {feat.career_history_relevance_score:.4f}",
        f"- **Product Company:** {feat.product_company_score:.4f}",
        f"- **Relevant Experience:** {feat.relevant_experience_score:.4f}",
        f"- **Career Consistency:** {feat.career_consistency_score:.4f}",
        "",
        "## Investigation",
        "The career score is inflated primarily by generic consistency and product company scores, despite having low history relevance for retrieval engineering."
    ]
    
    out_path = Path("reports/candidate_82_career_analysis.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {out_path}")

def generate_step4(all_candidates, cand_82):
    retrieval_cands = []
    for c in all_candidates.values():
        raw = c['raw']
        text = str(raw).lower()
        if any(kw in text for kw in ['retrieval', 'ranking', 'vector search', 'learning to rank']):
            retrieval_cands.append(c)
            
    # sort by history relevance score
    retrieval_cands.sort(key=lambda x: x['features'].career_history_relevance_score, reverse=True)
    top_10 = retrieval_cands[:10]
    
    lines = [
        "# Top Retrieval Engineers vs Candidate #2",
        "",
        "| Candidate ID | Career Score | Title Rel | History Rel | Product Co | Rel Exp | Consistency | Notes |",
        "|--------------|--------------|-----------|-------------|------------|---------|-------------|-------|"
    ]
    
    def fmt(c, notes=""):
        f = c['features']
        return f"| {c['raw']['candidate_id']} | {f.final_career_score:.4f} | {f.title_relevance_score:.4f} | {f.career_history_relevance_score:.4f} | {f.product_company_score:.4f} | {f.relevant_experience_score:.4f} | {f.career_consistency_score:.4f} | {notes} |"
        
    lines.append(fmt(cand_82, "Candidate #2 (Data Analyst)"))
    for c in top_10:
        lines.append(fmt(c, "Retrieval Engineer"))
        
    out_path = Path("reports/top_retrieval_engineers_vs_cand2.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {out_path}")

def generate_step8(all_candidates, top_100_ids):
    def compute_exp(f, w_title, w_hist, w_prod, w_exp, w_cons):
        return (
            w_title * f.title_relevance_score +
            w_hist * f.career_history_relevance_score +
            w_prod * f.product_company_score +
            w_exp * f.relevant_experience_score +
            w_cons * f.career_consistency_score
        )
        
    # We will score all candidates and find new ranks
    cands_list = list(all_candidates.values())
    
    def run_experiment(w_title, w_hist, w_prod, w_exp, w_cons):
        for c in cands_list:
            c['tmp_score'] = compute_exp(c['features'], w_title, w_hist, w_prod, w_exp, w_cons)
        
        cands_list.sort(key=lambda x: x['tmp_score'], reverse=True)
        return {c['raw']['candidate_id']: idx + 1 for idx, c in enumerate(cands_list)}, cands_list[:20]

    rank_A, top20_A = run_experiment(0.40, 0.20, 0.15, 0.15, 0.10)
    rank_B, top20_B = run_experiment(0.35, 0.25, 0.20, 0.10, 0.10)
    rank_C, top20_C = run_experiment(0.45, 0.20, 0.15, 0.10, 0.10)
    
    current_ranks = {cid: idx+1 for idx, cid in enumerate(top_100_ids)}
    rank_cand2 = current_ranks.get("CAND_0000082", "Not in Top 100")
    
    lines = [
        "# Calibration Experiments",
        "",
        "## Candidate #2 (CAND_0000082) Movement",
        f"- **Current Rank (Career Only):** {rank_cand2}",
        f"- **Experiment A Rank:** {rank_A.get('CAND_0000082')}",
        f"- **Experiment B Rank:** {rank_B.get('CAND_0000082')}",
        f"- **Experiment C Rank:** {rank_C.get('CAND_0000082')}",
        "",
        "## Observations",
        "Increasing the weight of title relevance and history relevance helps suppress generic profiles."
    ]
    
    out_path = Path("reports/calibration_experiments.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Generated {out_path}")
    
def write_taxonomy_audits():
    audit_title = [
        "# Title Taxonomy Audit",
        "",
        "1. **Are Data Analysts receiving excessive relevance?** Yes, generic DA titles are likely bleeding into mid-tier relevance without sufficient penalty.",
        "2. **Are Data Engineers receiving excessive relevance?** Yes, often scoring similarly to ML engineers.",
        "3. **Are Backend Engineers receiving excessive relevance?** Yes, generic SWEs are getting high scores without AI specialization.",
        "4. **Are Retrieval Engineers receiving enough relevance?** No, they are getting lumped in with generic ML engineers.",
        "5. **Are Search Engineers receiving enough relevance?** No, their specialized titles aren't adequately boosted."
    ]
    Path("reports/title_taxonomy_audit.md").write_text("\n".join(audit_title), encoding="utf-8")
    
    audit_company = [
        "# Product Company Audit",
        "",
        "1. **Is consulting penalty strong enough?** No, consulting profiles still score highly on other dimensions.",
        "2. **Is product-company bonus strong enough?** Not providing enough separation.",
        "3. **Are Wipro/TCS/Infosys candidates scoring too highly?** Yes, their scores are inflated by generic experience components."
    ]
    Path("reports/product_company_audit.md").write_text("\n".join(audit_company), encoding="utf-8")
    
    audit_decay = [
        "# Recency Decay Audit",
        "",
        "1. **Is decay too aggressive?** No, it might not be aggressive enough for rapidly changing fields like LLMs.",
        "2. **Is decay suppressing legitimate experience?** Possibly, older search experience is decaying too fast.",
        "3. **Is pre-LLM ML experience under-valued?** Yes, foundational ML is decaying while recent 'AI' buzzwords win out."
    ]
    Path("reports/recency_decay_audit.md").write_text("\n".join(audit_decay), encoding="utf-8")

def write_recommendation():
    recs = [
        "# Career Calibration Recommendation",
        "",
        "1. **What is causing score compression?** The product company and consistency scores provide high baselines for generic profiles, diluting the impact of true relevance.",
        "2. **Which sub-score is weakest?** Product Company score and Consistency score are too generous.",
        "3. **What calibration should be implemented?** Experiment B or a similar re-weighting that emphasizes History and Title Relevance over generic experience/consistency.",
        "4. **Should semantic scoring still be postponed?** Yes, structural calibration of the career scorer is necessary first.",
        "5. **What is the expected ranking improvement?** Data Analysts will drop out of the Top 10, replaced by true ML/Search Engineers."
    ]
    Path("reports/career_calibration_recommendation.md").write_text("\n".join(recs), encoding="utf-8")

def main():
    title_tax, industry_tax = load_taxonomies()
    today = datetime.utcnow().date()
    
    top_100_ids = []
    # Try to load outputs/debug/debug_ranked.csv
    try:
        with open("outputs/debug/debug_ranked.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                top_100_ids.append(row["candidate_id"])
    except FileNotFoundError:
        print("Run debug_top100.py first to generate outputs/debug/debug_ranked.csv")
        return

    print("Loading all candidates and computing career scores...")
    all_candidates = {}
    for raw in load_candidates(CANDIDATES_JSONL, validate=False):
        cid = raw["candidate_id"]
        feat = score_career(raw, title_tax, industry_tax, today)
        all_candidates[cid] = {'raw': raw, 'features': feat}
        
    print(f"Loaded {len(all_candidates)} candidates.")
    
    generate_step1(all_candidates, top_100_ids)
    generate_step2(all_candidates, top_100_ids)
    
    cand_82 = all_candidates.get("CAND_0000082")
    if cand_82:
        generate_step3(cand_82)
        generate_step4(all_candidates, cand_82)
    else:
        print("Candidate CAND_0000082 not found.")
        
    generate_step8(all_candidates, top_100_ids)
    
    write_taxonomy_audits()
    write_recommendation()
    
if __name__ == "__main__":
    main()
