"""src/pipeline — feature extraction, ranking, reasoning and export pipeline."""

from src.pipeline.feature_extractor import CandidateFeatures, extract_features
from src.pipeline.ranker import RankedCandidate, rank_candidates, compute_final_score
from src.pipeline.reasoning_generator import generate_explanation
from src.pipeline.exporter import export_submission_csv, export_debug_csv, validate_submission

__all__ = [
    # Feature extraction
    "CandidateFeatures",
    "extract_features",
    # Ranking
    "RankedCandidate",
    "rank_candidates",
    "compute_final_score",
    # Reasoning
    "generate_explanation",
    # Export
    "export_submission_csv",
    "export_debug_csv",
    "validate_submission",
]
