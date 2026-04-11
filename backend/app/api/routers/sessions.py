"""
Sessions router
───────────────
POST /sessions/start   → create a new session, run PrerequisiteNode,
                          return the first quiz (concept 1)
GET  /sessions/{id}    → inspect full state (debug / frontend polling)
DELETE /sessions/{id}  → clean up
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import logging

from app.agents.graph import (
    compiled_graph,
    get_initial_state,
    _quiz_generator_node,
)
import app.api.store as store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── request / response models ─────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    user_id: str
    project: dict = Field(
        example={"name": "AI Task Manager", "description": "A web app for tasks with AI priority."}
    )
    known_stack: List[str]   = Field(example=["HTML", "CSS", "basic Python"])
    unknown_stack: List[str] = Field(example=["React", "FastAPI", "React hooks"])
    start_date: str          = Field(example="2025-06-01")
    end_date: str            = Field(example="2025-07-27")
    repo_url: str            = Field(example="https://github.com/student/my-project")
    github_branch: str       = Field(default="main")
    blackout_dates: Optional[List[str]] = Field(default=None, example=["2025-06-20"])


class QuizQuestionOut(BaseModel):
    type: str
    question: str
    options: Optional[List[str]]


class StartSessionResponse(BaseModel):
    session_id: str
    concept: str
    concept_index: int
    total_concepts: int
    estimated_time: str
    quiz: List[QuizQuestionOut]


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
def start_session(body: StartSessionRequest):
    """
    1. Build zero-state from the request.
    2. Run the graph up to the first pause point (wait_quiz_answers).
       This executes: prerequisite → quiz_generator → wait_quiz_answers
    3. Return the first concept's quiz to the frontend.
    """
    session_id = str(uuid.uuid4())
    state = get_initial_state(
        user_id=body.user_id,
        project=body.project,
        known_stack=body.known_stack,
        unknown_stack=body.unknown_stack,
        start_date=body.start_date,
        end_date=body.end_date,
        repo_url=body.repo_url,
        github_branch=body.github_branch,
        blackout_dates=body.blackout_dates,
    )

    try:
        # Stream until the first pause node.
        # compiled_graph.stream() yields one dict per node executed.
        # We consume all events so state is fully updated after prerequisite
        # and quiz_generator have run.
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 5},    # prerequisite + quiz_generator only
        ):
            # Each event is {node_name: updated_state}
            node_name, updated = next(iter(event.items()))
            state = updated
            if node_name == "wait_quiz_answers":
                break

    except Exception as e:
        logger.error(f"start_session graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    quiz = state["quiz_results"][-1]
    index = state["current_concept_index"]
    prereq = state["prerequisites"][index]

    return StartSessionResponse(
        session_id=session_id,
        concept=prereq["concept"],
        concept_index=index,
        total_concepts=len(state["prerequisites"]),
        estimated_time=prereq["estimated_time"],
        quiz=[
            QuizQuestionOut(
                type=q["type"],
                question=q["question"],
                options=q.get("options"),
            )
            for q in quiz["questions"]
        ],
    )


@router.get("/{session_id}")
def get_session(session_id: str):
    """Return the full state for a session (useful for debugging / frontend polling)."""
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


@router.delete("/{session_id}")
def delete_session(session_id: str):
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete(session_id)
    return {"deleted": session_id}