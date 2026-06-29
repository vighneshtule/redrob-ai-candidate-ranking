from fastapi import APIRouter, HTTPException
from typing import List
from backend_api.schemas.models import CandidateResponse
from backend_api.services.pipeline_service import get_candidate, _ranked_candidates_cache

router = APIRouter(prefix="/api/candidate", tags=["Candidate"])

@router.get("/", response_model=List[CandidateResponse])
def get_all_candidates_endpoint():
    return list(_ranked_candidates_cache.values())

@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate_endpoint(candidate_id: str):
    cand = get_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found in recent ranking")
    return cand
