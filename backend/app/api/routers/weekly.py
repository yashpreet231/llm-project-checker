"""
Weekly router
─────────────
POST /weekly/{session_id}/start        → generate tasks for current week
POST /weekly/{session_id}/check        → run completion check against GitHub
POST /weekly/{session_id}/quiz/submit  → grade task quiz + run evaluator
GET  /weekly/{session_id}/tasks        → return current week's tasks
GET  /weekly/{session_id}/quiz         → return current week's task quiz
GET  /weekly/{session_id}/score        → return latest evaluation result
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from app.agents.graph import compiled_graph, _task_quiz_node
from app.agents.nodes.completion_check_node import completion_router
from app.agents.nodes.evaluator_node import weekly_loop_router
import app.api.store as store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── models ────────────────────────────────────────────────────────────────────

class TaskSubmission(BaseModel):
    github_folder: str
    filename: str
    commit_message: str


class TaskOut(BaseModel):
    day: int
    title: str
    description: str
    steps: List[str]
    submission: TaskSubmission
    estimated_hours: int


class WeekTasksResponse(BaseModel):
    week_number: int
    theme: str
    goal: str
    difficulty: str
    tasks: List[TaskOut]


class CheckCompletionResponse(BaseModel):
    week_number: int
    completed: bool
    reason: str
    next_step: str     # "task_quiz" | "retry_tasks"


class SubmitTaskQuizRequest(BaseModel):
    answers: List[str] = Field(
        description=(
            "Answers in question order. "
            "MCQ → 'A'/'B'/'C'/'D'. "
            "Code → exact answer string. "
            "Reflection → free-text string."
        )
    )


class EvaluationBreakdown(BaseModel):
    completion_points: int
    quiz_points: int
    reflection_points: int
    difficulty_adjustment: int


class EvaluationFeedback(BaseModel):
    strength: str
    improvement: str
    message: str
    next_week_tip: str


class EvaluationResponse(BaseModel):
    week_number: int
    score: float            # -5 to +5
    score_display: float    # 0 to 10
    breakdown: EvaluationBreakdown
    feedback: EvaluationFeedback
    project_complete: bool
    next_week: Optional[int] = None


class QuizQuestionOut(BaseModel):
    type: str
    question: str
    options: Optional[List[str]]


class TaskQuizResponse(BaseModel):
    week_number: int
    concept: str
    questions: List[QuizQuestionOut]


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/start", response_model=WeekTasksResponse)
def start_week(session_id: str):
    """
    Generate the 5 daily tasks for the current week.
    Call this once per week — at the start of each new week.
    """
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.get("roadmap"):
        raise HTTPException(
            status_code=409,
            detail="Roadmap not yet generated. Complete planning phase first.",
        )

    if state.get("project_complete"):
        raise HTTPException(status_code=410, detail="Project is already complete.")

    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 5},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated
            if node_name == "task_generator":
                break

    except Exception as e:
        logger.error(f"start_week graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    current_week = state["current_week"]
    week_plan = state["roadmap"]["weeks"][current_week - 1]

    return WeekTasksResponse(
        week_number=current_week,
        theme=week_plan["theme"],
        goal=week_plan["goal"],
        difficulty=week_plan.get("difficulty", "medium"),
        tasks=[TaskOut(**t) for t in state["weekly_tasks"]],
    )


@router.post("/{session_id}/check", response_model=CheckCompletionResponse)
def check_completion(session_id: str):
    """
    Run the CompletionCheckNode against the student's GitHub repo.
    Reads repo_url and github_branch from state (set at session start).

    Returns completed=True/False and the next step the frontend should take.
    """
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.get("weekly_tasks"):
        raise HTTPException(
            status_code=409,
            detail="No tasks generated yet. Call /weekly/{id}/start first.",
        )

    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 5},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated
            if node_name == "completion_check":
                break

    except Exception as e:
        logger.error(f"check_completion graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    route = completion_router(state)
    next_step = "task_quiz" if route == "task_quiz" else "retry_tasks"

    return CheckCompletionResponse(
        week_number=state["current_week"],
        completed=state["completion_status"],
        reason=state.get("completion_reason", ""),
        next_step=next_step,
    )


@router.get("/{session_id}/quiz", response_model=TaskQuizResponse)
def get_task_quiz(session_id: str):
    """
    Generate and return the task quiz for the current week.
    Only callable after a successful completion check (completed=True).
    """
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.get("completion_status"):
        raise HTTPException(
            status_code=409,
            detail="Completion check not passed yet.",
        )

    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 5},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated
            if node_name == "wait_task_quiz":
                break

    except Exception as e:
        logger.error(f"get_task_quiz graph error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    quiz = state["task_quiz_results"][-1]
    return TaskQuizResponse(
        week_number=state["current_week"],
        concept=quiz["concept"],
        questions=[
            QuizQuestionOut(
                type=q["type"],
                question=q["question"],
                options=q.get("options"),
            )
            for q in quiz["questions"]
        ],
    )


@router.post("/{session_id}/quiz/submit", response_model=EvaluationResponse)
def submit_task_quiz(session_id: str, body: SubmitTaskQuizRequest):
    """
    1. Grade the task quiz with student's answers.
    2. Run the EvaluatorNode.
    3. Return the score, feedback, and whether the project is complete.
    """
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.get("task_quiz_results"):
        raise HTTPException(
            status_code=409,
            detail="No task quiz generated yet. Call GET /weekly/{id}/quiz first.",
        )

    # ── grade task quiz ───────────────────────────────────────────────────────
    try:
        state = _task_quiz_node.grade_quiz(state, body.answers)
    except Exception as e:
        logger.error(f"grade task quiz error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # ── run evaluator ─────────────────────────────────────────────────────────
    try:
        for event in compiled_graph.stream(
            state,
            config={"recursion_limit": 5},
        ):
            node_name, updated = next(iter(event.items()))
            state = updated
            if node_name == "evaluator":
                break

    except Exception as e:
        logger.error(f"submit_task_quiz evaluator error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    store.set(session_id, state)

    week_plan = state["roadmap"]["weeks"][state["current_week"] - 2]   # evaluated week
    feedback = state["evaluation_feedback"] or {}
    breakdown = (
        state.get("evaluation_breakdown") or
        {"completion_points": 0, "quiz_points": 0, "reflection_points": 0, "difficulty_adjustment": 0}
    )

    return EvaluationResponse(
        week_number=week_plan["week_number"],
        score=state["weekly_score"],
        score_display=state["weekly_score_display"],
        breakdown=EvaluationBreakdown(**breakdown),
        feedback=EvaluationFeedback(**feedback),
        project_complete=state.get("project_complete", False),
        next_week=state["current_week"] if not state.get("project_complete") else None,
    )


@router.get("/{session_id}/tasks", response_model=WeekTasksResponse)
def get_tasks(session_id: str):
    """Return current week's tasks (re-fetch without re-generating)."""
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if not state.get("weekly_tasks"):
        raise HTTPException(status_code=404, detail="No tasks generated yet.")

    current_week = state["current_week"]
    week_plan = state["roadmap"]["weeks"][current_week - 1]

    return WeekTasksResponse(
        week_number=current_week,
        theme=week_plan["theme"],
        goal=week_plan["goal"],
        difficulty=week_plan.get("difficulty", "medium"),
        tasks=[TaskOut(**t) for t in state["weekly_tasks"]],
    )


@router.get("/{session_id}/score", response_model=EvaluationResponse)
def get_score(session_id: str):
    """Return the latest week's evaluation result."""
    state = store.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("weekly_score") is None:
        raise HTTPException(status_code=404, detail="No evaluation yet.")

    evaluated_week = state["current_week"] - 1
    week_plan = state["roadmap"]["weeks"][evaluated_week - 1]
    feedback = state["evaluation_feedback"] or {}
    breakdown = (
        state.get("evaluation_breakdown") or
        {"completion_points": 0, "quiz_points": 0, "reflection_points": 0, "difficulty_adjustment": 0}
    )

    return EvaluationResponse(
        week_number=evaluated_week,
        score=state["weekly_score"],
        score_display=state["weekly_score_display"],
        breakdown=EvaluationBreakdown(**breakdown),
        feedback=EvaluationFeedback(**feedback),
        project_complete=state.get("project_complete", False),
        next_week=state["current_week"] if not state.get("project_complete") else None,
    )