from fastapi import APIRouter
from backend_api.schemas.models import BenchmarkResponse
from backend_api.services.pipeline_service import global_status

router = APIRouter(prefix="/api/benchmarks", tags=["Benchmarks"])

@router.get("/", response_model=BenchmarkResponse)
def get_benchmarks_endpoint():
    m = global_status.metrics
    return BenchmarkResponse(
        candidatesProcessed=m["candidatesProcessed"],
        runtimeSeconds=m["runtimeSeconds"],
        heapSize=m["heapSize"],
        cacheHits=m["cacheHits"],
        memoryMb=m["memoryMb"],
        averageCandidateTimeMs=m["averageCandidateTimeMs"]
    )
