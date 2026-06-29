"""backend_api/schemas/models.py — Pydantic request/response models for the Redrob API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RankRequest(BaseModel):
    job_description: str
    top_k: int = 100


class SemanticEvidence(BaseModel):
    sentence: str
    keywords: List[str]


class JdMatch(BaseModel):
    required_skills_found: List[str] = []
    missing_skills: List[str] = []
    preferred_skills_found: List[str] = []
    experience_match: bool
    location_match: bool
    overall_match_percentage: int


class TimelineEvent(BaseModel):
    year: str
    title: str
    company: str
    is_relevant: bool


class CopilotData(BaseModel):
    why_ranked: List[str] = []
    potential_risks: List[str] = []
    semantic_evidence: List[SemanticEvidence] = []
    jd_match: JdMatch
    timeline: List[TimelineEvent] = []
    recommendation_status: str
    recommendation_reasoning: str
    interview_questions: List[str] = []


class CandidateScores(BaseModel):
    final_score: float
    career_score: float
    skill_score: float
    behavior_score: float
    integrity_score: float
    semantic_score: float
    consistency_score: float


class SkillDetails(BaseModel):
    supported: List[str] = []
    unsupported: List[str] = []


class CandidateResponse(BaseModel):
    id: str
    name: str
    avatar_url: Optional[str] = None
    headline: str
    current_title: str
    company: str
    location: str
    years_of_experience: int
    open_to_work: bool
    relocation: bool
    notice_period: Optional[str] = None

    scores: CandidateScores
    match_status: str

    skills: SkillDetails
    career_summary: str
    behavior_signals: List[str] = []
    integrity_flags: List[str] = []
    recruiter_explanation: str

    copilot: CopilotData


class BenchmarkResponse(BaseModel):
    candidatesProcessed: int
    runtimeSeconds: float
    heapSize: int
    cacheHits: int
    memoryMb: float
    averageCandidateTimeMs: float


class PipelineStatusResponse(BaseModel):
    currentStep: int
    isPlaying: bool
    metrics: Dict[str, Any]
