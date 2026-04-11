from langgraph.graph import StateGraph, END
from app.agents.state import AgentState

from app.agents.nodes.prerequisite_node import PrerequisiteNode
from app.agents.nodes.quiz_generator_node import QuizGeneratorNode, prereq_loop_router
from app.agents.nodes.analyzer_node import AnalyzerNode
from app.agents.nodes.roadmap_node import RoadmapNode
from app.agents.nodes.task_generator_node import TaskGeneratorNode
from app.agents.nodes.completion_check_node import CompletionCheckNode, completion_router
from app.agents.nodes.task_quiz_generator_node import TaskQuizGeneratorNode
from app.agents.nodes.evaluator_node import EvaluatorNode, weekly_loop_router

import logging

logger = logging.getLogger(__name__)


# ── node instances ─────────────────────────────────────────────────────────────
# All nodes share the HuggingFace API key from env (HF_API_KEY).
# Pass huggingface_api_key explicitly to any constructor for per-node overrides.

_prerequisite_node     = PrerequisiteNode()
_quiz_generator_node   = QuizGeneratorNode()
_analyzer_node         = AnalyzerNode()
_roadmap_node          = RoadmapNode()
_task_generator_node   = TaskGeneratorNode()
_completion_check_node = CompletionCheckNode()
_task_quiz_node        = TaskQuizGeneratorNode()
_evaluator_node        = EvaluatorNode()


# ── node wrappers ──────────────────────────────────────────────────────────────
# LangGraph node callables: (state) -> state.
# Nodes that need runtime args (repo_url, branch) read them from state fields.

def run_prerequisite(state: AgentState) -> AgentState:
    return _prerequisite_node.run(state)


def run_quiz_generator(state: AgentState) -> AgentState:
    """
    Generates the quiz for the current prereq concept.
    Grading (grade_quiz) is called by the API layer after the student
    submits answers — it is NOT a graph node.
    """
    return _quiz_generator_node.run(state)


def run_analyzer(state: AgentState) -> AgentState:
    return _analyzer_node.run(state)


def run_roadmap(state: AgentState) -> AgentState:
    return _roadmap_node.run(state)


def run_task_generator(state: AgentState) -> AgentState:
    return _task_generator_node.run(state)


def run_completion_check(state: AgentState) -> AgentState:
    """
    Reads repo_url and github_branch from state so the graph edge
    does not need to pass arguments directly.
    Add these two keys to AgentState before invoking this node:
      state["repo_url"]      = "https://github.com/owner/repo"
      state["github_branch"] = "main"
    """
    repo_url = state.get("repo_url", "")
    branch   = state.get("github_branch", "main")

    if not repo_url:
        raise ValueError(
            "run_completion_check: state['repo_url'] is not set. "
            "Set it when the student registers their GitHub repo."
        )
    return _completion_check_node.run(state, repo_url=repo_url, branch=branch)


def run_task_quiz(state: AgentState) -> AgentState:
    return _task_quiz_node.run(state)


def run_evaluator(state: AgentState) -> AgentState:
    return _evaluator_node.run(state)


# ── human-in-the-loop pause nodes ─────────────────────────────────────────────
# Lightweight pass-through nodes that mark where the graph pauses for
# student input.  In production use LangGraph's interrupt_before /
# interrupt_after on these node names, or use LangGraph Cloud's
# human-in-the-loop checkpointing.

def wait_for_quiz_answers(state: AgentState) -> AgentState:
    """
    PAUSE — prereq quiz generated.
    Frontend:
      1. Reads state["quiz_results"][-1] and renders the quiz.
      2. Collects student answers.
      3. Calls QuizGeneratorNode.grade_quiz(state, answers).
      4. Resumes graph — prereq_loop_router decides next node.
    """
    logger.info(
        f"PAUSE [wait_for_quiz_answers]: concept "
        f"{state['current_concept_index'] + 1}/{len(state['prerequisites'])}"
    )
    return state


def wait_for_student_approach(state: AgentState) -> AgentState:
    """
    PAUSE — prereq loop complete, all concepts passed.
    Frontend:
      1. Shows a text area: "Describe your plan for the project."
      2. Writes the answer to state['student_approach'].
      3. Resumes graph → analyzer.
    """
    logger.info("PAUSE [wait_for_student_approach]: all prereqs passed")
    return state


def wait_for_task_quiz_answers(state: AgentState) -> AgentState:
    """
    PAUSE — weekly task quiz generated.
    Frontend:
      1. Reads state["task_quiz_results"][-1] and renders the quiz.
      2. Collects student answers (MCQ + code + reflection text).
      3. Calls TaskQuizGeneratorNode.grade_quiz(state, answers).
      4. Resumes graph → evaluator.
    """
    logger.info(f"PAUSE [wait_for_task_quiz_answers]: week {state['current_week']}")
    return state


# ── graph builder ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Construct and return the full agent graph.

    Topology:
    ─────────────────────────────────────────────────────────────────
    PHASE 3 — PREREQUISITE LOOP
      prerequisite
        └─→ quiz_generator
              └─→ wait_quiz_answers
                    └─→ [prereq_loop_router]
                              │ quiz_concept  → quiz_generator  (loop: concept failed)
                              │ exit_prereq   → wait_student_approach

    PHASE 4 — PLANNING
      wait_student_approach
        └─→ analyzer
              └─→ roadmap

    PHASE 5 — WEEKLY EXECUTION LOOP
      roadmap
        └─→ task_generator ◄────────────────────────────────┐
              └─→ completion_check                           │
                    └─→ [completion_router]                  │
                              │ retry_task  → task_generator ┘ (loop: not done)
                              │ task_quiz   → task_quiz
                                              └─→ wait_task_quiz
                                                    └─→ evaluator
                                                          └─→ [weekly_loop_router]
                                                                    │ next_week       → task_generator
                                                                    │ project_complete→ END
    ─────────────────────────────────────────────────────────────────
    """
    graph = StateGraph(AgentState)

    # register all nodes
    graph.add_node("prerequisite",          run_prerequisite)
    graph.add_node("quiz_generator",        run_quiz_generator)
    graph.add_node("wait_quiz_answers",     wait_for_quiz_answers)
    graph.add_node("wait_student_approach", wait_for_student_approach)
    graph.add_node("analyzer",              run_analyzer)
    graph.add_node("roadmap",               run_roadmap)
    graph.add_node("task_generator",        run_task_generator)
    graph.add_node("completion_check",      run_completion_check)
    graph.add_node("task_quiz",             run_task_quiz)
    graph.add_node("wait_task_quiz",        wait_for_task_quiz_answers)
    graph.add_node("evaluator",             run_evaluator)

    # ── entry ──────────────────────────────────────────────────────────────────
    graph.set_entry_point("prerequisite")

    # ── Phase 3: Prerequisite loop ─────────────────────────────────────────────
    graph.add_edge("prerequisite",   "quiz_generator")
    graph.add_edge("quiz_generator", "wait_quiz_answers")

    graph.add_conditional_edges(
        "wait_quiz_answers",
        prereq_loop_router,
        {
            # concept failed → re-run quiz for the same index
            "quiz_concept": "quiz_generator",
            # all concepts passed → ask student for their approach
            "exit_prereq":  "wait_student_approach",
        }
    )

    # ── Phase 4: Planning ──────────────────────────────────────────────────────
    graph.add_edge("wait_student_approach", "analyzer")
    graph.add_edge("analyzer",              "roadmap")

    # ── Phase 5: Weekly execution loop ────────────────────────────────────────
    graph.add_edge("roadmap", "task_generator")

    graph.add_edge("task_generator", "completion_check")

    graph.add_conditional_edges(
        "completion_check",
        completion_router,
        {
            # work not done → regenerate tasks for the same week
            "retry_task": "task_generator",
            # work done → run task quiz
            "task_quiz":  "task_quiz",
        }
    )

    graph.add_edge("task_quiz",      "wait_task_quiz")
    graph.add_edge("wait_task_quiz", "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        weekly_loop_router,
        {
            # more weeks remaining → loop back for next week
            "next_week":        "task_generator",
            # all weeks done → terminate
            "project_complete": END,
        }
    )

    return graph


# ── compiled graph (import this in your FastAPI routers) ──────────────────────
compiled_graph = build_graph().compile()


# ── entrypoint helpers ────────────────────────────────────────────────────────

def get_initial_state(
    user_id: str,
    project: dict,
    known_stack: list[str],
    unknown_stack: list[str],
    start_date: str,
    end_date: str,
    repo_url: str,
    github_branch: str = "main",
    blackout_dates: list[str] | None = None,
) -> AgentState:
    """
    Build the zero-state dict to kick off a new student session.
    Pass the returned dict as the `input` arg to compiled_graph.invoke()
    or compiled_graph.stream().

    Example:
        state = get_initial_state(...)
        for event in compiled_graph.stream(state):
            print(event)
    """
    return AgentState(
        user_id=user_id,
        project=project,
        known_stack=known_stack,
        unknown_stack=unknown_stack,
        prerequisites=[],
        current_concept_index=0,
        quiz_results=[],
        student_approach=None,
        analysis=None,
        roadmap=None,
        weekly_tasks=None,
        current_week=0,
        completion_status=None,
        completion_reason=None,
        task_quiz_results=None,
        weekly_score=None,
        weekly_score_display=None,
        evaluation_feedback=None,
        project_complete=False,
        start_date=start_date,
        end_date=end_date,
        blackout_dates=blackout_dates or [],
        repo_url=repo_url,
        github_branch=github_branch,
    )


# ── dev runner ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Print the mermaid graph so you can paste it at mermaid.live
    try:
        print("\n=== MERMAID GRAPH ===")
        print(compiled_graph.get_graph().draw_mermaid())
    except Exception as e:
        print(f"(mermaid render failed: {e})")

    print("\n=== GRAPH NODES ===")
    for node in compiled_graph.get_graph().nodes:
        print(f"  {node}")

    print("\n=== GRAPH EDGES ===")
    for edge in compiled_graph.get_graph().edges:
        print(f"  {edge}")