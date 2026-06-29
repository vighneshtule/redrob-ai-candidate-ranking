from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend_api.routers import ranking, candidate, benchmark, pipeline

app = FastAPI(
    title="Redrob AI Candidate Ranking API",
    description="Backend API for the Redrob AI Candidate Ranking System",
    version="1.0.0",
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for development/hackathon
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ranking.router)
app.include_router(candidate.router)
app.include_router(benchmark.router)
app.include_router(pipeline.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Redrob AI Ranking API"}
