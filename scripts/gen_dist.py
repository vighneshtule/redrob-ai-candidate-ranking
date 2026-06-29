import csv
import numpy as np
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def get_stats(scores):
    if not scores: return 0,0,0,0,0
    return np.min(scores), np.max(scores), np.mean(scores), np.median(scores), np.std(scores)

def main():
    post_path = Path("outputs/debug/debug_ranked.csv")
    pre_path = Path("outputs/debug/pre_calib_debug_ranked.csv")
    
    post_scores = []
    with open(post_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            post_scores.append(float(row["career_score"]))
            
    pre_scores = []
    with open(pre_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pre_scores.append(float(row["career_score"]))
            
    lines = [
        "# Distribution Comparison (Top 100 Career Scores)",
        "",
        "| Subset | Min | Max | Mean | Median | StdDev |",
        "|--------|-----|-----|------|--------|--------|"
    ]
    
    for name, scores in [("Pre-Calibration Top 100", pre_scores), ("Post-Calibration Top 100", post_scores)]:
        mn, mx, me, md, st = get_stats(scores)
        lines.append(f"| {name} | {mn:.4f} | {mx:.4f} | {me:.4f} | {md:.4f} | {st:.4f} |")
        
    Path("reports/distribution_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print("Done")

if __name__ == "__main__":
    main()
