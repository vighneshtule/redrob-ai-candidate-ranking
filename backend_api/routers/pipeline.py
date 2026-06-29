from fastapi import APIRouter
from backend_api.schemas.models import PipelineStatusResponse
from backend_api.services.pipeline_service import get_pipeline_status

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status_endpoint():
    return get_pipeline_status()
