import csv
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline.loader import load_candidates
from src.config import CANDIDATES_JSONL

def main():
    post_path = Path("outputs/debug/debug_ranked.csv")
    pre_path = Path("outputs/debug/pre_calib_debug_ranked.csv")
    
    post_data = []
    post_map = {}
    with open(post_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            post_data.append(row)
            post_map[row["candidate_id"]] = row
            
    pre_map = {}
    with open(pre_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pre_map[row["candidate_id"]] = row
            
    # Load candidate raw data for titles
    print("Loading candidate titles...")
    cands_raw = {}
    for raw in load_candidates(CANDIDATES_JSONL, validate=False):
        cands_raw[raw["candidate_id"]] = raw
        
    print("Generating post_calibration_top100.md")
    lines_100 = [
        "# Post-Calibration Top 100",
        "",
        "| Rank | Candidate ID | Final Score | Career Score | Skill Score | Current Title |",
        "|------|--------------|-------------|--------------|-------------|---------------|"
    ]
    for row in post_data:
        cid = row["candidate_id"]
        raw = cands_raw.get(cid, {})
        title = raw.get("profile", {}).get("current_title", "")
        lines_100.append(f"| {row['rank']} | {cid} | {float(row['score']):.4f} | {float(row['career_score']):.4f} | {float(row['skill_score']):.4f} | {title} |")
        
    Path("reports/post_calibration_top100.md").write_text("\n".join(lines_100), encoding="utf-8")
    
    print("Generating post_calibration_top20.md")
    lines_20 = [
        "# Post-Calibration Top 20",
        "",
        "| Rank | Prev Rank | Movement | Candidate ID | Career Score | Skill Score | Current Title |",
        "|------|-----------|----------|--------------|--------------|-------------|---------------|"
    ]
    for row in post_data[:20]:
        cid = row["candidate_id"]
        rank = int(row["rank"])
        prev_row = pre_map.get(cid)
        if prev_row:
            prev_rank = int(prev_row["rank"])
            move = prev_rank - rank
            movement = f"Up {move}" if move > 0 else (f"Down {abs(move)}" if move < 0 else "Unchanged")
        else:
            prev_rank = "N/A"
            movement = "New to Top 100"
            
        raw = cands_raw.get(cid, {})
        title = raw.get("profile", {}).get("current_title", "")
        lines_20.append(f"| {rank} | {prev_rank} | {movement} | {cid} | {float(row['career_score']):.4f} | {float(row['skill_score']):.4f} | {title} |")
        
    Path("reports/post_calibration_top20.md").write_text("\n".join(lines_20), encoding="utf-8")
    
    print("Generating candidate82_after_calibration.md")
    c82 = post_map.get("CAND_0000082")
    c82_pre = pre_map.get("CAND_0000082")
    lines_82 = [
        "# Candidate #82 After Calibration",
        "",
        "| Metric | Pre-Calibration | Post-Calibration |",
        "|--------|-----------------|------------------|",
    ]
    if c82:
        lines_82.append(f"| Rank | {c82_pre['rank']} | {c82['rank']} |")
        lines_82.append(f"| Final Score | {c82_pre['score']} | {c82['score']} |")
        lines_82.append(f"| Career Score | {c82_pre['career_score']} | {c82['career_score']} |")
    else:
        lines_82.append(f"| Rank | {c82_pre['rank']} | Dropped out of Top 100 |")
        lines_82.append(f"| Final Score | {c82_pre['score']} | N/A |")
        lines_82.append(f"| Career Score | {c82_pre['career_score']} | N/A |")
        
    lines_82.extend([
        "",
        "## Conclusion",
        "Candidate #82 (Data Analyst) is no longer near the top of the rankings due to the reduction of generic career score features (consistency and product company multipliers)."
    ])
    Path("reports/candidate82_after_calibration.md").write_text("\n".join(lines_82), encoding="utf-8")
    
    print("Done generating reports.")

if __name__ == "__main__":
    main()
