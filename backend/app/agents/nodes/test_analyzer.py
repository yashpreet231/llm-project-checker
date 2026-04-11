from app.agents.nodes.analyzer import AnalyzerNode
from app.agents.state import AgentState


def main():
    node = AnalyzerNode()

    # 🔹 Simulated state (same structure your node expects)
    state: AgentState = {
        "user_id": "1",

        "project": {
            "name": "AI Task Manager",
            "description": "A web app where users manage tasks with AI suggestions"
        },

        "known_stack": ["HTML", "CSS"],
        "unknown_stack": ["React", "FastAPI"],

        "prerequisites": [
            {"concept": "React basics", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"},
            {"concept": "FastAPI", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"}
        ],

        "current_concept_index": 2,

        "quiz_results": [
            {"concept": "React basics", "score": 2, "passed": False, "questions": []},
            {"concept": "FastAPI", "score": 4, "passed": True, "questions": []}
        ],

        # 🔥 VERY IMPORTANT (Analyzer depends on this)
        "student_approach": (
            "I will build a React frontend with a task list. "
            "I will use FastAPI for backend APIs. "
            "I will store tasks in a list. "
            "I will connect frontend and backend using fetch. "
            "For AI I will add a button but not sure how it works."
        ),

        # required placeholders
        "analysis": None,
        "roadmap": None,
        "weekly_tasks": None,
        "current_week": 0,
        "completion_status": None,
        "task_quiz_results": None,
        "weekly_score": None,
        "start_date": None,
        "end_date": None,
        "blackout_dates": None,
    }

    # 🔹 Run analyzer
    state = node.run(state)

    analysis = state["analysis"]

    print("\n=== ANALYSIS ===\n")

    print("POSITIVES:")
    for p in analysis["positives"]:
        print(f"- {p['point']}")
        print(f"  {p['detail']}")

    print("\nGAPS:")
    for g in analysis["gaps"]:
        print(f"- {g['point']}")
        print(f"  {g['detail']}")
        print(f"  Fix: {g['suggestion']}")

    print("\nOVERALL:", analysis["overall_understanding"])
    print("FOCUS AREAS:", ", ".join(analysis["recommended_focus_areas"]))


if __name__ == "__main__":
    main()