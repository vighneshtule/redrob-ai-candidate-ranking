"""
src/features/skill_career_consistency.py
========================================
Skill-Career Consistency Layer for the Redrob candidate ranking system.

Checks if claimed critical skills (like Retrieval, Vector DBs) are actually supported
by evidence in the candidate's career history (headline, summary, job titles, and descriptions).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillCareerConsistencyResult:
    consistency_score: float
    claimed_critical_skills: list[str]
    supported_skills: list[str]
    unsupported_skills: list[str]
    evidence_matches: dict[str, list[str]]
    explanation: str


# Critical skills and their synonyms/evidence groups
_CRITICAL_EVIDENCE_GROUPS = {
    "retrieval": [
        "retrieval", "semantic search", "dense retrieval", "hybrid retrieval", "keyword search", "bm25",
        "search relevance"
    ],
    "ranking": [
        "ranking", "learning to rank", "ltr", "xgboost ranker", "reranking", "re-ranking", "ranker"
    ],
    "embeddings": [
        "embeddings", "embedding generation", "dense vectors", "sentence transformers", "sentence-transformers"
    ],
    "vector_database": [
        "vector database", "pinecone", "faiss", "pgvector", "vector index", "ann search", "milvus", "qdrant",
        "weaviate", "chroma"
    ],
    "recommendation_systems": [
        "recommendation systems", "recommender systems", "recsys", "collaborative filtering", "content-based filtering"
    ],
    "llms": [
        "llms", "large language models", "gpt", "llama", "anthropic", "prompt engineering", "fine-tuning", "lora",
        "rag", "retrieval augmented generation"
    ],
    "nlp": [
        "nlp", "natural language processing", "text classification", "ner", "named entity recognition",
        "spacy", "huggingface", "transformers"
    ],
}

# The keys above map to these normalized claimed skills. 
# We'll map exact strings that candidates claim to these categories.
_CLAIM_TO_CATEGORY = {
    # Retrieval
    "retrieval": "retrieval",
    "bm25": "retrieval",
    "semantic search": "retrieval",
    
    # Ranking
    "ranking": "ranking",
    "learning to rank": "ranking",
    
    # Embeddings
    "embeddings": "embeddings",
    
    # Vector Database
    "vector search": "vector_database",
    "vector database": "vector_database",
    "pinecone": "vector_database",
    "faiss": "vector_database",
    "pgvector": "vector_database",
    "elasticsearch": "vector_database",
    
    # Recommendation Systems
    "recommendation systems": "recommendation_systems",
    
    # LLMs
    "llms": "llms",
    "rag": "llms",
    
    # NLP
    "nlp": "nlp",
}

def _extract_evidence_text(candidate: dict) -> str:
    """Extract all text from profile and career history that might contain evidence."""
    profile = candidate.get("profile") or {}
    evidence_parts = []
    
    headline = profile.get("headline") or ""
    if headline:
        evidence_parts.append(headline)
        
    summary = profile.get("summary") or ""
    if summary:
        evidence_parts.append(summary)
        
    career_history = candidate.get("career_history") or []
    for job in career_history:
        title = job.get("title") or ""
        if title:
            evidence_parts.append(title)
        desc = job.get("description") or ""
        if desc:
            evidence_parts.append(desc)
            
    return " ".join(evidence_parts).lower()


def score_skill_consistency(candidate: dict) -> SkillCareerConsistencyResult:
    """
    Evaluate if claimed critical skills are supported by career history evidence.
    """
    candidate_skills = candidate.get("skills") or []
    claimed_skills = set()
    
    # 1. Identify which critical skills the candidate claims
    claimed_categories = set()
    for skill_dict in candidate_skills:
        name = (skill_dict.get("name") or "").lower().strip()
        # Find which category this skill belongs to (if any)
        for claim_key, category in _CLAIM_TO_CATEGORY.items():
            if claim_key in name:
                claimed_categories.add(category)
                claimed_skills.add(claim_key)

    claimed_categories = sorted(list(claimed_categories))
    claimed_skills = sorted(list(claimed_skills))
    
    if not claimed_categories:
        # Candidate doesn't claim any critical AI/retrieval skills.
        # Neutral consistency.
        return SkillCareerConsistencyResult(
            consistency_score=0.5,
            claimed_critical_skills=[],
            supported_skills=[],
            unsupported_skills=[],
            evidence_matches={},
            explanation="No critical AI/retrieval skills claimed; neutral consistency."
        )
        
    # 2. Search for evidence
    evidence_text = _extract_evidence_text(candidate)
    
    supported_skills = []
    unsupported_skills = []
    evidence_matches = {}
    
    for category in claimed_categories:
        synonyms = _CRITICAL_EVIDENCE_GROUPS.get(category, [])
        matches = []
        for syn in synonyms:
            if syn in evidence_text:
                matches.append(syn)
                
        if matches:
            supported_skills.append(category)
            evidence_matches[category] = matches
        else:
            unsupported_skills.append(category)
            
    # 3. Calculate score
    total_claimed = len(claimed_categories)
    total_supported = len(supported_skills)
    
    consistency_score = round(total_supported / total_claimed, 4)
    
    # 4. Generate explanation
    if total_claimed == total_supported:
        explanation = f"Strong consistency. {total_supported}/{total_claimed} claimed critical skill categories ({', '.join(supported_skills)}) are supported by career evidence."
    elif total_supported == 0:
        explanation = f"Weak consistency. Candidate claims {', '.join(claimed_skills)} but career history contains little to no related evidence."
    else:
        explanation = f"Partial consistency. {total_supported}/{total_claimed} claimed critical skill categories are supported by career evidence. Unsupported: {', '.join(unsupported_skills)}."
        
    return SkillCareerConsistencyResult(
        consistency_score=consistency_score,
        claimed_critical_skills=claimed_categories,
        supported_skills=supported_skills,
        unsupported_skills=unsupported_skills,
        evidence_matches=evidence_matches,
        explanation=explanation
    )
