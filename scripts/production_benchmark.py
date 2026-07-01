import time
import tracemalloc
import os
from pathlib import Path
import sys

# Ensure matplotlib and psutil are installed
try:
    import matplotlib.pyplot as plt
    import psutil
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib", "psutil"])
    import matplotlib.pyplot as plt
    import psutil


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.loader import load_candidates
from src.features.career_scorer import load_taxonomies, score_career
from src.features.skill_scorer import load_skill_taxonomy, score_skills
from src.features.behavioral_scorer import score_behavior
from src.features.integrity_scorer import score_integrity
from src.features.semantic_scorer import score_semantic
from src.pipeline.feature_extractor import extract_features
from src.pipeline.ranker import rank_candidates, rank_candidates_parallel, _heap_key, compute_final_score
from src.pipeline.reasoning_generator import generate_explanation
from backend_api.schemas.models import CandidateResponse, CandidateScores, SkillDetails, CopilotData, JdMatch
from src.config import CANDIDATES_JSONL
import heapq

LIMIT = 5000
TOP_K = 100

def get_process_memory():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

def run_benchmarks():
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    print("Preloading taxonomies...")
    title_tax, industry_tax = load_taxonomies()
    tier_a, tier_b, tier_c, _ = load_skill_taxonomy()
    
    metrics = {}
    
    # 1. Candidate Loading
    t0 = time.perf_counter()
    candidates = list(load_candidates(CANDIDATES_JSONL, limit=LIMIT, validate=False))
    t1 = time.perf_counter()
    metrics['Candidate Loading'] = t1 - t0
    
    # 2. Individual Scorers (measure over all candidates)
    t_integrity = 0
    t_career = 0
    t_skill = 0
    t_behavior = 0
    t_semantic = 0
    t_extract = 0
    
    print(f"Scoring {LIMIT} candidates sequentially to measure component timings...")
    features_list = []
    
    for c in candidates:
        t0 = time.perf_counter()
        ir = score_integrity(c)
        t_integrity += time.perf_counter() - t0
        
        t0 = time.perf_counter()
        cr = score_career(c, title_tax, industry_tax)
        t_career += time.perf_counter() - t0
        
        t0 = time.perf_counter()
        sr = score_skills(c, tier_a, tier_b, tier_c)
        t_skill += time.perf_counter() - t0
        
        t0 = time.perf_counter()
        br = score_behavior(c)
        t_behavior += time.perf_counter() - t0
        
        t0 = time.perf_counter()
        sem = score_semantic(c, None, None)
        t_semantic += time.perf_counter() - t0
        
        t0 = time.perf_counter()
        feat = extract_features(c, title_tax, industry_tax, tier_a, tier_b, tier_c)
        t_extract += time.perf_counter() - t0
        features_list.append(feat)

    metrics['Integrity Scorer'] = t_integrity
    metrics['Career Scorer'] = t_career
    metrics['Skill Scorer'] = t_skill
    metrics['Behavioral Scorer'] = t_behavior
    metrics['Semantic Scorer'] = t_semantic
    metrics['Feature Extraction (Total)'] = t_extract
    
    # Calculate scores for Top-K heap
    scored_features = [(compute_final_score(f), f) for f in features_list]
    
    # 3. Top-K Heap
    t0 = time.perf_counter()
    heap = []
    for score, features in scored_features:
        if features.veto_candidate: continue
        key = _heap_key(score, features)
        if len(heap) < TOP_K:
            heapq.heappush(heap, (key, features, score))
        elif key > heap[0][0]:
            heapq.heapreplace(heap, (key, features, score))
    sorted_entries = sorted(heap, key=lambda entry: entry[0], reverse=True)
    t1 = time.perf_counter()
    metrics['Top-K Heap'] = t1 - t0
    
    # 4. Explanation generation
    t0 = time.perf_counter()
    explanations = []
    for rank_idx, (_, features, score) in enumerate(sorted_entries, start=1):
        explanations.append((generate_explanation(features, score), features, score))
    t1 = time.perf_counter()
    metrics['Explanation Generation'] = t1 - t0
    
    # 5. API Serialization
    t0 = time.perf_counter()
    api_responses = []
    for expl, features, score in explanations:
        fv = features.final_feature_vector
        api_responses.append(CandidateResponse(
            id=features.candidate_id,
            name=fv.get("name", "Unknown"),
            avatar_url=None,
            headline=fv.get("current_title", ""),
            current_title=fv.get("current_title", ""),
            company=fv.get("company", ""),
            location=fv.get("location", ""),
            years_of_experience=int(fv.get("career_years_exp", 0)),
            open_to_work=fv.get("open_to_work", True),
            relocation=fv.get("relocation", False),
            scores=CandidateScores(
                final_score=score,
                career_score=fv.get("career_score", 0.0),
                skill_score=fv.get("skill_score", 0.0),
                behavior_score=fv.get("behavior_score", 0.0),
                integrity_score=fv.get("integrity_score", 0.0),
                semantic_score=fv.get("semantic_score", 0.0),
                consistency_score=fv.get("consistency_score", 0.0),
            ),
            match_status="Good Match",
            skills=SkillDetails(supported=[], unsupported=[]),
            career_summary=expl,
            behavior_signals=[],
            integrity_flags=[],
            recruiter_explanation=expl,
            copilot=CopilotData(
                why_ranked=[expl],
                potential_risks=[],
                semantic_evidence=[],
                jd_match=JdMatch(
                    required_skills_found=[],
                    missing_skills=[],
                    preferred_skills_found=[],
                    experience_match=True,
                    location_match=True,
                    overall_match_percentage=int(score * 100),
                ),
                timeline=[],
                recommendation_status="Interview",
                recommendation_reasoning=expl,
                interview_questions=[],
            )
        ).model_dump())
    t1 = time.perf_counter()
    metrics['API Serialization'] = t1 - t0
    
    # Run Serial vs Parallel Comparison
    print("Running Serial vs Parallel Comparison...")
    tracemalloc.start()
    t0 = time.perf_counter()
    serial_res = rank_candidates(iter(candidates), title_tax, industry_tax, tier_a, tier_b, tier_c, top_k=TOP_K)
    t_serial = time.perf_counter() - t0
    _, peak_mem_serial = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    tracemalloc.start()
    t0 = time.perf_counter()
    parallel_res = rank_candidates_parallel(candidates, title_tax, industry_tax, tier_a, tier_b, tier_c, top_k=TOP_K)
    t_parallel = time.perf_counter() - t0
    _, peak_mem_parallel = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    mem_mb = get_process_memory()
    cpu_cores = os.cpu_count() or 1
    
    total_pipeline_time_serial = t_serial + metrics['Candidate Loading']
    total_pipeline_time_parallel = t_parallel + metrics['Candidate Loading']
    
    # Generate Chart
    plt.figure(figsize=(10, 6))
    components = ['Candidate Loading', 'Career Scorer', 'Skill Scorer', 'Behavioral Scorer', 'Integrity Scorer', 'Semantic Scorer', 'Top-K Heap', 'Explanation Generation', 'API Serialization']
    times = [metrics[c] for c in components]
    plt.barh(components, times, color='skyblue')
    plt.xlabel('Time (seconds)')
    plt.title(f'Pipeline Component Runtime Distribution ({LIMIT} Candidates)')
    plt.gca().invert_yaxis()
    plt.tight_layout()
    chart_path = reports_dir / 'performance_chart.png'
    plt.savefig(chart_path)
    plt.close()
    
    # Generate Report
    report_path = reports_dir / 'performance_report.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# Redrob AI Ranking Engine — Production Performance Report\n\n")
        
        f.write("## 1. System Metrics\n")
        f.write(f"- **CPU Cores:** {cpu_cores}\n")
        f.write(f"- **Process Memory:** {mem_mb:.1f} MB\n")
        f.write(f"- **Test Corpus:** {LIMIT:,} candidates\n\n")
        
        f.write("## 2. Before vs After Comparison (Pipeline Execution)\n")
        f.write("| Metric | Serial (Before) | Parallel (After) | Improvement |\n")
        f.write("|---|---|---|---|\n")
        speedup = t_serial / max(t_parallel, 1e-9)
        f.write(f"| **Runtime ({LIMIT:,})** | {t_serial:.2f}s | {t_parallel:.2f}s | **{speedup:.2f}x faster** |\n")
        f.write(f"| **Candidates/sec** | {LIMIT/t_serial:,.0f} | {LIMIT/t_parallel:,.0f} | |\n")
        f.write(f"| **Avg. candidate time** | {(t_serial/LIMIT)*1000:.2f} ms | {(t_parallel/LIMIT)*1000:.2f} ms | |\n")
        f.write(f"| **Peak Memory Usage** | {peak_mem_serial/(1024*1024):.1f} MB | {peak_mem_parallel/(1024*1024):.1f} MB | |\n")
        f.write(f"| **Proj. 100k Runtime** | {(t_serial/LIMIT)*100000/60:.1f} mins | {(t_parallel/LIMIT)*100000/60:.1f} mins | |\n\n")
        
        f.write("## 3. Component Runtime Distribution\n")
        f.write("Measured sequentially to isolate component latency:\n\n")
        f.write("| Component | Total Time (s) | % of Total |\n")
        f.write("|---|---|---|\n")
        total_time = sum(times)
        for c, t in zip(components, times):
            pct = (t / total_time) * 100
            f.write(f"| {c} | {t:.3f} | {pct:.1f}% |\n")
            
        f.write(f"\n*Note: Feature Extraction (wrapping all scorers) took {metrics['Feature Extraction (Total)']:.3f}s.*\n\n")
        
        f.write("## 4. Top Bottlenecks\n")
        sorted_components = sorted(zip(components, times), key=lambda x: x[1], reverse=True)
        for i, (c, t) in enumerate(sorted_components[:3]):
            f.write(f"{i+1}. **{c}** ({t:.3f}s)\n")
        f.write("\n")
        f.write("![Performance Distribution](./performance_chart.png)\n")
        
    print(f"Benchmark complete. Report generated at: {report_path}")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    run_benchmarks()
