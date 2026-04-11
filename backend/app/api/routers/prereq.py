"""
Prereq router (MCQ-only version)
───────────────────────────────
- Works ONLY with MCQ quizzes
- Supports TEST_MODE bypass
- Enforces mastery learning in production
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import logging
import os

from app.agents.graph import compiled_graph, _quiz_generator_node
from app.agents.nodes.quiz_generator_node import prereq_loop_router
import app.api.store as store

logger = logging.getLogger(__name__)
router = APIRouter()

# 🔥 TEST MODE FLAG
ALLOW_FAIL_ADVANCE = os.getenv("TEST_MODE", "true").lower() == "true"


# ── models ─────────────────────────────────────────────

class SubmitQuizRequest(BaseModel):
    answers: List[str] = Field(
        description="MCQ answers only (A/B/C/D)",
        example=["A", "B", "C", "D", "A"],
    )


class QuizQuestionOut(BaseModel):
    type: str
    question: str
    options: List[str]  # ✅ always present for MCQ


class SubmitQuizResponse(BaseModel):
    graded_score: int
    passed: bool
    prereqs_complete: bool

    next_concept: Optional[str] = None
    next_concept_index: Optional[int] = None
    total_concepts: Optional[int] = None
    estimated_time: Optional[str] = None
    next_quiz: Optional[List[QuizQuestionOut]] = None

    message: Optional[str] = None


class PrereqStatusResponse(BaseModel):
    current_concept_index: int
    total_concepts: int
    quiz_results: list


# ── routes ─────────────────────────────────────────────

@router.post("/{session_id}/submit", response_model=SubmitQuizResponse)
def submit_quiz(session_id: str, body: SubmitQuizRequest):

    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    # ── Step 1: Grade quiz ─────────────────────────────
    try:
        state = _quiz_generator_node.grade_quiz(state, body.answers)
    except Exception as e:
        logger.error(f"grade_quiz error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    last_result = state["quiz_results"][-1]
    print(last_result)
    # ───────────────────────────────────────────────────
    # 🧪 TEST MODE: FORCE PASS
    # ───────────────────────────────────────────────────
    if ALLOW_FAIL_ADVANCE and not last_result["passed"]:
        logger.warning("TEST MODE: forcing pass to move forward")

        state["quiz_results"][-1]["passed"] = True
        # state["current_concept_index"] += 1

    current_index = state["current_concept_index"]

    # ───────────────────────────────────────────────────
    # 🔴 PRODUCTION: BLOCK ON FAIL
    # ───────────────────────────────────────────────────
    if not last_result["passed"] and not ALLOW_FAIL_ADVANCE:
        logger.info("Student failed → retry SAME concept")

        prereq = state["prerequisites"][current_index]

        try:
            state = _quiz_generator_node.run(state)
        except Exception as e:
            logger.error(f"Quiz regeneration error: {e}")
            raise HTTPException(status_code=500, detail="Failed to regenerate quiz")

        store.set(session_id, state)

        retry_quiz = state["quiz_results"][-1]

        return SubmitQuizResponse(
            graded_score=last_result["score"],
            passed=False,
            prereqs_complete=False,
            next_concept=prereq["concept"],
            next_concept_index=current_index,
            total_concepts=len(state["prerequisites"]),
            estimated_time=prereq["estimated_time"],
            next_quiz=[
                QuizQuestionOut(
                    type="mcq",
                    question=q["question"],
                    options=q["options"],
                )
                for q in retry_quiz["questions"]
            ],
        )

    # ───────────────────────────────────────────────────
    # ✅ PASS → RUN GRAPH
    # ───────────────────────────────────────────────────
    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 10},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated

            if node_name in ("wait_quiz_answers", "wait_student_approach"):
                break

    except Exception as e:
        logger.error(f"Graph execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    route = prereq_loop_router(state)

    # ── All concepts complete ─────────────────────────
    if route == "exit_prereq":
        return SubmitQuizResponse(
            graded_score=last_result["score"],
            passed=True,
            prereqs_complete=True,
            message="All prerequisites completed 🎉 Proceed to planning.",
        )

    # ── Next concept ─────────────────────────────────
    index = state["current_concept_index"]
    prereq = state["prerequisites"][index]
    next_quiz_result = state["quiz_results"][-1]

    return SubmitQuizResponse(
        graded_score=last_result["score"],
        passed=True,
        prereqs_complete=False,
        next_concept=prereq["concept"],
        next_concept_index=index,
        total_concepts=len(state["prerequisites"]),
        estimated_time=prereq["estimated_time"],
        next_quiz=[
            QuizQuestionOut(
                type="mcq",
                question=q["question"],
                options=q["options"],
            )
            for q in next_quiz_result["questions"]
        ],
    )


# ── status endpoint ───────────────────────────────────

@router.get("/{session_id}/status", response_model=PrereqStatusResponse)
def prereq_status(session_id: str):
    state = store.get(session_id)

    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    return PrereqStatusResponse(
        current_concept_index=state["current_concept_index"],
        total_concepts=len(state["prerequisites"]),
        quiz_results=[
            {
                "concept": r["concept"],
                "score": r["score"],
                "passed": r["passed"],
            }
            for r in state["quiz_results"]
        ],
    )