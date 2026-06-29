"""
src/features/semantic_scorer.py
================================
Implements Phase 7 semantic skill extraction using lightweight embeddings.
"""

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np

@dataclass(frozen=True)
class SemanticScoreResult:
    semantic_score: float
    jd_similarity: float
    evidence_chunks: tuple[str, ...]
    explanation: str

def score_semantic(candidate: Dict[str, Any], candidate_embedding: Any, jd_embedding: Any) -> SemanticScoreResult:
    """
    Compute semantic score based on precomputed candidate_embedding and jd_embedding.
    """
    if candidate_embedding is None or jd_embedding is None:
        return SemanticScoreResult(
            semantic_score=0.0,
            jd_similarity=0.0,
            evidence_chunks=(),
            explanation="Skipped — semantic embeddings not found in cache."
        )
    
    norm_c = np.linalg.norm(candidate_embedding)
    norm_j = np.linalg.norm(jd_embedding)
    
    if norm_c == 0 or norm_j == 0:
        sim = 0.0
    else:
        sim = np.dot(candidate_embedding, jd_embedding) / (norm_c * norm_j)
        
    sim = max(0.0, min(float(sim), 1.0))
    
    return SemanticScoreResult(
        semantic_score=sim,
        jd_similarity=sim,
        evidence_chunks=(),
        explanation=f"Semantic similarity: {sim:.3f}"
    )
