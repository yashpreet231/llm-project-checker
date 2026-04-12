"""
Planning router
───────────────
POST /planning/{session_id}/approach   → submit student's written plan,
                                          run analyzer + roadmap,
                                          return the full roadmap
GET  /planning/{session_id}/roadmap    → return the generated roadmap
GET  /planning/{session_id}/analysis   → return the analyzer output
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from app.agents.graph import compiled_graph
import app.api.store as store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── models ────────────────────────────────────────────────────────────────────

class SubmitApproachRequest(BaseModel):
    approach: str = Field(
        min_length=50,
        description="Student's free-text plan for building the project (min 50 chars).",
        example=(
            "I plan to build a React frontend with components for listing, "
            "adding, and deleting tasks. The backend will be FastAPI with "
            "SQLite. I'll use fetch() to connect the two. For AI I'll call "
            "the HuggingFace API to suggest task priorities."
        ),
    )


class WeekSummary(BaseModel):
    week_number: int
    start_date: str
    end_date: str
    theme: str
    goal: str
    topics: List[str]
    deliverable: str
    difficulty: str


class MilestoneSummary(BaseModel):
    week: int
    description: str


class RoadmapResponse(BaseModel):
    total_weeks: int
    weeks: List[WeekSummary]
    milestones: List[MilestoneSummary]


class AnalysisGap(BaseModel):
    point: str
    detail: str
    suggestion: str


class AnalysisPositive(BaseModel):
    point: str
    detail: str


class AnalysisResponse(BaseModel):
    overall_understanding: str
    positives: List[AnalysisPositive]
    gaps: List[AnalysisGap]
    recommended_focus_areas: List[str]


class SubmitApproachResponse(BaseModel):
    analysis: AnalysisResponse
    roadmap: RoadmapResponse


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/approach", response_model=SubmitApproachResponse)
def submit_approach(session_id: str, body: SubmitApproachRequest):
    """
    1. Write student_approach into state.
    2. Run the graph from wait_student_approach:
         analyzer → roadmap → task_generator (pause before completion_check)
    3. Return the analysis + full roadmap so the frontend can show
       the student their personalised plan before execution starts.
    """
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if state.get("roadmap"):
        raise HTTPException(
            status_code=409,
            detail="Roadmap already generated for this session.",
        )

    # inject student approach
    state = {**state, "student_approach": body.approach}

    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 50},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated
            # stop after roadmap is built — before entering the weekly loop
            if node_name == "roadmap":
                break

    except Exception as e:
        logger.error(f"submit_approach graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    return SubmitApproachResponse(
        analysis=AnalysisResponse(**state["analysis"]),
        roadmap=RoadmapResponse(**state["roadmap"]),
    )


@router.get("/{session_id}/roadmap", response_model=RoadmapResponse)
def get_roadmap(session_id: str):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if not state.get("roadmap"):
        raise HTTPException(status_code=404, detail="Roadmap not yet generated.")
    return RoadmapResponse(**state["roadmap"])


@router.get("/{session_id}/analysis", response_model=AnalysisResponse)
def get_analysis(session_id: str):
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if not state.get("analysis"):
        raise HTTPException(status_code=404, detail="Analysis not yet generated.")
    return AnalysisResponse(**state["analysis"])