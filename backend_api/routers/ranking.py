from fastapi import APIRouter
from backend_api.schemas.models import RankRequest, CandidateResponse
from backend_api.services.pipeline_service import run_pipeline
from typing import List

router = APIRouter(prefix="/api/rank", tags=["Ranking"])

@router.post("/", response_model=List[CandidateResponse])
def rank_candidates_endpoint(request: RankRequest):
    return run_pipeline(request.job_description, request.top_k)
