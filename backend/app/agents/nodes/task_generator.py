from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState
import os
import json
import logging

logger = logging.getLogger(__name__)


class TaskGeneratorNode:
    """
    Generates a set of daily tasks for the CURRENT week based on the roadmap.

    Reads:
      - state["roadmap"]["weeks"][current_week - 1]  : this week's theme, goal,
                                                        topics, deliverable
      - state["current_week"]                         : 1-indexed week pointer
      - state["quiz_results"]                         : to avoid re-teaching
                                                        passed concepts
      - state["weekly_score"]                         : previous week's score
                                                        (adjusts difficulty if low)

    Each task tells the student:
      - WHAT to build or study
      - HOW to do it (step-by-step approach, not just a label)
      - HOW to submit (exact GitHub folder + filename convention)

    Output written to state["weekly_tasks"]:
      [
        {
          "day": 1,                        # 1–5 (Mon–Fri)
          "title": "<task title>",
          "description": "<what to do>",
          "steps": ["<step 1>", ...],      # 3–5 concrete steps
          "submission": {
            "github_folder": "<path>",
            "filename": "<file or folder name>",
            "commit_message": "<suggested git commit message>"
          },
          "estimated_hours": <int>         # 1–4
        }
      ]
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON array."
    )

    TASK_GENERATOR_PROMPT = """You are an expert software engineering mentor generating a week of daily tasks for a student.

=== PROJECT ===
Name        : {project_name}
Description : {project_description}

=== STUDENT PROFILE ===
Known stack  : {known_stack}
Unknown stack: {unknown_stack}

=== THIS WEEK ===
Week number  : {week_number}
Theme        : {theme}
Goal         : {goal}
Topics       : {topics}
Deliverable  : {deliverable}
Difficulty   : {difficulty}

=== PREVIOUS WEEK CONTEXT ===
Previous week score : {previous_score}
(Score is on a -5 to +5 scale. Below 0 means the student struggled — slow down and add reinforcement steps.)

=== CONCEPTS ALREADY MASTERED (do NOT re-teach these) ===
{mastered_concepts}

=== TASK GENERATION RULES ===

RULE 1 — EXACTLY 5 TASKS (one per day, Monday to Friday)
- Day 1 (Monday)  : Setup + foundation for the week's theme
- Day 2 (Tuesday) : Core concept — the most important topic
- Day 3 (Wednesday): Build the main feature
- Day 4 (Thursday): Integration + edge cases
- Day 5 (Friday)  : Complete the deliverable + push to GitHub

RULE 2 — EACH TASK MUST HAVE A CLEAR TITLE
WRONG: "Day 1 Task", "React stuff", "Work on backend"
RIGHT: "Set up FastAPI project structure and create the /tasks GET endpoint"
       "Build the TaskCard React component with props and conditional rendering"

RULE 3 — DESCRIPTION MUST EXPLAIN THE WHY AND THE WHAT
Not just what to build — explain WHY this step matters for the project.
2–4 sentences max.

RULE 4 — STEPS MUST BE ACTIONABLE (3–5 steps per task)
Each step must be specific enough to execute without guessing.
WRONG: "Learn useState", "Set up the component"
RIGHT: "Create a new file src/components/TaskList.jsx and define a functional component that accepts a 'tasks' prop"
       "Add a useState hook initialized to an empty array: const [tasks, setTasks] = useState([])"
       "Use useEffect to call fetch('http://localhost:8000/tasks') on mount and store the response in tasks"

RULE 5 — SUBMISSION MUST BE SPECIFIC
Every task must have:
  - github_folder : the exact subfolder in the repo (e.g. "frontend/src/components")
  - filename      : the exact file or folder name to push (e.g. "TaskList.jsx")
  - commit_message: a conventional commit message (feat/fix/chore/docs prefix)

RULE 6 — ESTIMATED HOURS must be realistic (1–4 hours per day)
- Easy difficulty  : 1–2 hours
- Medium difficulty: 2–3 hours
- Hard difficulty  : 3–4 hours

RULE 7 — DO NOT RE-TEACH MASTERED CONCEPTS
If a concept appears in the mastered list, do not dedicate a full day to it.
You may reference it briefly in steps but do not make it the focus.

RULE 8 — ADAPT TO PREVIOUS SCORE
- Score < 0  : slow down, add more explanation in steps, break tasks into smaller pieces
- Score 0–2  : normal pace
- Score 3–5  : can push slightly harder, add a stretch step at the end of day 5

RULE 9 — DAY 5 MUST COMPLETE THE WEEK'S DELIVERABLE
Day 5 task must result in the exact deliverable described in the week plan
being pushed to GitHub with a meaningful commit.

STRICT OUTPUT RULES:
- Output ONLY a valid JSON array of exactly 5 task objects
- No text before or after
- No markdown fences
- All strings on a single line (no embedded newlines in JSON strings)

Required format:
[
  {{
    "day": 1,
    "title": "<specific task title>",
    "description": "<2-4 sentence explanation of what and why>",
    "steps": [
      "<concrete step 1>",
      "<concrete step 2>",
      "<concrete step 3>"
    ],
    "submission": {{
      "github_folder": "<repo subfolder path>",
      "filename": "<file or folder name>",
      "commit_message": "<conventional commit message>"
    }},
    "estimated_hours": 2
  }}
]
"""

    def __init__(self, huggingface_api_key: str = None):
        api_key = huggingface_api_key or os.getenv("HF_API_KEY")
        self.llm = ChatHuggingFace(
            llm=HuggingFaceEndpoint(
                repo_id=os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
                huggingfacehub_api_token=api_key,
                task="text-generation",
                max_new_tokens=2048,
            )
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _mastered_concepts(self, state: AgentState) -> str:
        """Concepts the student passed in the prereq quiz — no need to re-teach."""
        passed = [
            r["concept"]
            for r in state.get("quiz_results", [])
            if r.get("passed")
        ]
        return ", ".join(passed) if passed else "None"

    def _previous_score(self, state: AgentState) -> str:
        score = state.get("weekly_score")
        if score is None:
            return "N/A (first week)"
        return str(score)

    def _parse_response(self, raw: str) -> list:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    # ── main ──────────────────────────────────────────────────────────────────

    def run(self, state: AgentState) -> AgentState:
        """
        Generate 5 daily tasks for the current week and write to state.

        Requires state keys:
          roadmap, current_week, project, known_stack, unknown_stack,
          quiz_results, weekly_score

        State keys updated:
          weekly_tasks  <- list of 5 task dicts for this week
        """
        roadmap = state.get("roadmap")
        if not roadmap:
            raise ValueError("TaskGeneratorNode: state['roadmap'] is missing. Run RoadmapNode first.")

        current_week = state.get("current_week", 1)
        weeks = roadmap.get("weeks", [])

        if current_week > len(weeks):
            logger.warning("TaskGeneratorNode: current_week exceeds roadmap length.")
            return state

        week_plan = weeks[current_week - 1]   # roadmap weeks are 1-indexed
        project = state["project"]

        prompt = self.TASK_GENERATOR_PROMPT.format(
            project_name=project.get("name", ""),
            project_description=project.get("description", ""),
            known_stack=", ".join(state["known_stack"]),
            unknown_stack=", ".join(state["unknown_stack"]),
            week_number=week_plan["week_number"],
            theme=week_plan["theme"],
            goal=week_plan["goal"],
            topics=", ".join(week_plan["topics"]),
            deliverable=week_plan["deliverable"],
            difficulty=week_plan.get("difficulty", "medium"),
            previous_score=self._previous_score(state),
            mastered_concepts=self._mastered_concepts(state),
        )

        try:
            logger.info(
                f"TaskGeneratorNode: generating tasks for week "
                f"{current_week}/{len(weeks)}"
            )
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            tasks = self._parse_response(response.content)
            logger.info(f"TaskGeneratorNode: {len(tasks)} tasks generated for week {current_week}")

            return {
                **state,
                "weekly_tasks": tasks,
            }

        except json.JSONDecodeError as e:
            logger.error(f"TaskGeneratorNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"TaskGeneratorNode error: {e}")
            raise


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    node = TaskGeneratorNode()
    state: AgentState = {
        "user_id": "student_01",
        "project": {
            "name": "AI Task Manager",
            "description": (
                "A web app where users create, assign, and track tasks "
                "with an AI assistant that suggests priorities."
            ),
        },
        "known_stack": ["HTML", "CSS", "basic Python"],
        "unknown_stack": ["React", "FastAPI", "REST APIs", "React hooks"],
        "prerequisites": [],
        "current_concept_index": 4,
        "quiz_results": [
            {"concept": "REST APIs",    "score": 5, "passed": True,  "questions": []},
            {"concept": "FastAPI",      "score": 4, "passed": True,  "questions": []},
            {"concept": "React basics", "score": 2, "passed": False, "questions": []},
            {"concept": "React hooks",  "score": 3, "passed": True,  "questions": []},
        ],
        "student_approach": None,
        "analysis": None,
        "roadmap": {
            "total_weeks": 6,
            "weeks": [
                {
                    "week_number": 1,
                    "start_date": "2025-06-01",
                    "end_date": "2025-06-07",
                    "theme": "Building stateful React components to fix the React basics gap",
                    "goal": "Student can build a React task list that adds and removes tasks using useState without page refresh",
                    "topics": [
                        "JSX syntax and conditional rendering with ternary operators",
                        "useState hook — declaring, reading, and updating state",
                        "Props — passing data and callbacks between parent and child components",
                        "Rendering lists with Array.map() and unique key props",
                    ],
                    "deliverable": "React <TaskList> component with add and delete functionality using useState — no backend yet",
                    "focus_areas": ["React state management with useState and useEffect"],
                    "difficulty": "easy",
                }
            ],
            "milestones": [],
        },
        "weekly_tasks": None,
        "current_week": 1,
        "completion_status": None,
        "task_quiz_results": None,
        "weekly_score": None,
        "start_date": "2025-06-01",
        "end_date": "2025-07-27",
        "blackout_dates": [],
    }

    result = node.run(state)
    tasks = result["weekly_tasks"]

    print(f"\nWeek 1 — {len(tasks)} tasks generated\n")
    for task in tasks:
        print(f"Day {task['day']}: {task['title']}")
        print(f"  {task['description']}")
        print(f"  Steps:")
        for step in task["steps"]:
            print(f"    → {step}")
        sub = task["submission"]
        print(f"  Submit : {sub['github_folder']}/{sub['filename']}")
        print(f"  Commit : {sub['commit_message']}")
        print(f"  Est.   : {task['estimated_hours']}h")
        print()