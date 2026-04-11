from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState
import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RoadmapNode:
    """
    Builds a week-by-week project roadmap personalised to the student.

    Uses:
      - analysis.gaps + recommended_focus_areas  : to weight early weeks
      - analysis.overall_understanding           : to set the pace
      - prerequisites + quiz_results             : to reinforce failed concepts
      - start_date / end_date / blackout_dates   : to align with the real calendar

    Output written to state["roadmap"]:
      {
        "total_weeks": <int>,
        "weeks": [
          {
            "week_number": 1,
            "start_date":  "YYYY-MM-DD",
            "end_date":    "YYYY-MM-DD",
            "theme":       "<specific one-sentence focus>",
            "goal":        "<measurable outcome by end of week>",
            "topics":      ["<specific topic>", ...],
            "deliverable": "<working GitHub-pushable feature>",
            "focus_areas": ["<from recommended_focus_areas>"],
            "difficulty":  "easy" | "medium" | "hard"
          }
        ],
        "milestones": [
          {
            "week": <int>,
            "description": "<meaningful project checkpoint>"
          }
        ]
      }

    The TaskGeneratorNode reads this roadmap and produces granular daily
    tasks week by week as the student progresses.
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON object."
    )

    ROADMAP_PROMPT = """You are an expert software engineering mentor creating a highly personalised project roadmap.

=== PROJECT ===
Name        : {project_name}
Description : {project_description}

=== STUDENT PROFILE ===
Known stack           : {known_stack}
Unknown stack         : {unknown_stack}
Overall understanding : {overall_understanding}

=== ANALYSIS SUMMARY ===
Positives (what the student already understands well):
{positives_summary}

Gaps to address (ordered by severity — the FIRST gap is the most critical):
{gaps_summary}

Recommended focus areas (EVERY item MUST appear in at least one week):
{focus_areas}

=== QUIZ PERFORMANCE PER CONCEPT ===
{quiz_summary}
Any concept marked FAILED must be explicitly reinforced in week 1 or 2.
Do NOT assume the student knows it just because it was in the prerequisites.

=== TIMELINE ===
Start date     : {start_date}
End date       : {end_date}
Available weeks: {available_weeks}
Blackout periods (do NOT assign tasks to these dates): {blackout_dates}

=== WEEK-BY-WEEK STRUCTURE RULES ===

RULE 1 — GAPS FIRST, ALWAYS
The first 1–2 weeks must directly address the most severe gaps and failed concepts.
Do NOT start with easy wins or topics the student already knows.
Week 1 is for the student's biggest weakness, not their strongest area.

RULE 2 — PACE MATCHES UNDERSTANDING LEVEL
- "weak"     → minimum 2 foundational weeks, one new concept per week, slow ramp
- "moderate" → 1 foundational week, integration starts by week 3
- "strong"   → no foundational weeks, start integration in week 1 or 2

RULE 3 — THEME (required, must be specific)
One sentence describing exactly what this week is about.
WRONG: "React Week", "Backend Work", "Learning APIs"
RIGHT: "Building stateful React components with useState and lifting state up"
       "Connecting React frontend to FastAPI using fetch, handling CORS and async responses"

RULE 4 — GOAL (required, must be measurable)
One sentence: what the student can DO by end of the week, not what they will study.
WRONG: "Learn about React hooks"
RIGHT: "Student can build a React task list that adds, removes, and updates tasks using useState without refreshing the page"

RULE 5 — TOPICS (2–4 items, must be specific enough to search or study directly)
WRONG: "React basics", "FastAPI", "state management"
RIGHT: "JSX syntax and conditional rendering with ternary operators"
       "FastAPI POST endpoint with Pydantic request body validation"
       "useEffect dependency array — when and why it re-runs"
       "fetch() with async/await — handling loading and error states"

RULE 6 — DELIVERABLE (must be a working, GitHub-pushable feature)
WRONG: "Read docs", "Set up project", "Practice React", "Learn API"
RIGHT: "React component <TaskList> that fetches GET /tasks from the FastAPI server and renders each task with a delete button"
       "FastAPI router /tasks with GET (list all), POST (create), DELETE (by id) — tested with curl"
       "Priority suggestion UI: clicking 'Suggest' sends task data to HuggingFace inference API and shows the response below the task card"

RULE 7 — DIFFICULTY ARC (must increase over the roadmap)
- Week 1    : always "easy"
- Middle    : "medium"
- Advanced  : "hard"
- Final week: "medium" (polish is effortful but not conceptually hard)
Never assign "hard" to week 1 or 2.

RULE 8 — WEEK PROGRESSION ARC
Early weeks  → fix gaps + foundational topics (based on quiz failures and analysis)
Middle weeks → integration (wire frontend to backend, real data flowing end-to-end)
Later weeks  → advanced features (AI integration, auth, error handling, edge cases)
Final week   → polish (end-to-end testing, README, edge cases, deployment prep)

RULE 9 — AI FEATURE MUST BE TECHNICALLY SPECIFIED
Never write "add AI" or "use AI button".
Always specify:
  → which API endpoint is called (e.g. HuggingFace inference, OpenAI chat completions)
  → what data is sent in the request body
  → what the response looks like and how it is displayed in the UI

RULE 10 — FOCUS AREAS MUST BE EXPLICITLY MAPPED
Every item in the recommended focus areas list must appear in at least one week's
topics list or theme. Cross-check before finalising — do not skip any.

RULE 11 — MILESTONES (2–4, at real turning points)
WRONG: "Backend done", "Frontend started", "Week 3 complete"
RIGHT: "CRUD API fully functional — all four endpoints return correct responses validated with curl and Postman"
       "React frontend connected to live FastAPI backend — task list renders real data, create and delete work end-to-end"
       "AI priority feature live — POST to HuggingFace inference returns suggested priority and renders inside the task card"

RULE 12 — NO REPETITION, NO FILLER
Every week must cover NEW ground.
Do not repeat topics from a previous week.
If available weeks exceed what the project genuinely needs, merge thin weeks rather than padding.

=== STRICT OUTPUT RULES ===
- Output ONLY valid JSON
- No text before or after the JSON object
- No markdown fences
- Every string value must be on a single line (no embedded newlines)

=== REQUIRED FORMAT ===
{{
  "total_weeks": <int>,
  "weeks": [
    {{
      "week_number": 1,
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "theme": "<specific one-sentence focus for this week>",
      "goal": "<one measurable outcome the student achieves by end of week>",
      "topics": ["<specific topic 1>", "<specific topic 2>"],
      "deliverable": "<working GitHub-pushable feature or component>",
      "focus_areas": ["<mapped focus area from recommended list, or empty list []>"],
      "difficulty": "easy"
    }}
  ],
  "milestones": [
    {{
      "week": <int>,
      "description": "<meaningful project checkpoint — not vague>"
    }}
  ]
}}
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

    # ── prompt helpers ────────────────────────────────────────────────────────

    def _format_positives(self, analysis: dict) -> str:
        lines = []
        for p in analysis.get("positives", []):
            lines.append(f"  + {p['point']}: {p['detail']}")
        return "\n".join(lines) if lines else "  None identified."

    def _format_gaps(self, analysis: dict) -> str:
        """
        Gaps are listed with severity index and the concrete roadmap suggestion
        so the LLM knows exactly which week to put the fix in.
        """
        lines = []
        for i, g in enumerate(analysis.get("gaps", []), 1):
            lines.append(
                f"  {i}. GAP: {g['point']}\n"
                f"     Problem    : {g['detail']}\n"
                f"     Roadmap fix: {g['suggestion']}"
            )
        return "\n".join(lines) if lines else "  None identified."

    def _build_quiz_summary(self, state: AgentState) -> str:
        results = state.get("quiz_results", [])
        if not results:
            return "  No quiz data available."
        lines = []
        for r in results:
            status = "PASSED" if r["passed"] else "FAILED"
            lines.append(f"  - {r['concept']}: {r['score']}/5  [{status}]")
        return "\n".join(lines)

    def _compute_available_weeks(
        self, start_date: str, end_date: str, blackout_dates: list[str]
    ) -> int:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            total_days = (end - start).days
            raw_weeks = max(1, total_days // 7)
            blackout_week_penalty = len(blackout_dates) // 7
            return max(1, raw_weeks - blackout_week_penalty)
        except ValueError:
            logger.warning("RoadmapNode: could not parse dates, defaulting to 4 weeks.")
            return 4

    # ── parse ─────────────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    # ── main ──────────────────────────────────────────────────────────────────

    def run(self, state: AgentState) -> AgentState:
        """
        Generate the full project roadmap and write it into state.

        Requires state keys:
          project, known_stack, unknown_stack,
          analysis, quiz_results, start_date, end_date, blackout_dates

        State keys updated:
          roadmap       <- full roadmap dict
          current_week  <- reset to 1 (TaskGeneratorNode starts here)
        """
        analysis = state.get("analysis")
        if not analysis:
            raise ValueError("RoadmapNode: state['analysis'] is missing. Run AnalyzerNode first.")

        project = state["project"]
        start_date = state.get("start_date") or datetime.today().strftime("%Y-%m-%d")
        end_date = state.get("end_date") or (
            datetime.today() + timedelta(weeks=8)
        ).strftime("%Y-%m-%d")
        blackout_dates = state.get("blackout_dates") or []

        available_weeks = self._compute_available_weeks(start_date, end_date, blackout_dates)

        prompt = self.ROADMAP_PROMPT.format(
            project_name=project.get("name", ""),
            project_description=project.get("description", ""),
            known_stack=", ".join(state["known_stack"]),
            unknown_stack=", ".join(state["unknown_stack"]),
            overall_understanding=analysis.get("overall_understanding", "moderate"),
            positives_summary=self._format_positives(analysis),
            gaps_summary=self._format_gaps(analysis),
            focus_areas=", ".join(analysis.get("recommended_focus_areas", [])),
            quiz_summary=self._build_quiz_summary(state),
            start_date=start_date,
            end_date=end_date,
            available_weeks=available_weeks,
            blackout_dates=", ".join(blackout_dates) if blackout_dates else "None",
        )

        try:
            logger.info("RoadmapNode: invoking LLM")
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            roadmap = self._parse_response(response.content)
            logger.info(
                f"RoadmapNode: {roadmap.get('total_weeks')} weeks | "
                f"{len(roadmap.get('milestones', []))} milestones"
            )

            return {
                **state,
                "roadmap": roadmap,
                "current_week": 1,
            }

        except json.JSONDecodeError as e:
            logger.error(f"RoadmapNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"RoadmapNode error: {e}")
            raise


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    node = RoadmapNode()
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
        "student_approach": "I'll build a React frontend and FastAPI backend...",
        "analysis": {
            "positives": [
                {"point": "Good grasp of FastAPI routing",
                 "detail": "Correctly described endpoint structure."},
                {"point": "Understands REST verbs",
                 "detail": "Correctly mapped GET/POST to actions."},
            ],
            "gaps": [
                {
                    "point": "No React state management plan",
                    "detail": "Student did not mention how React state will be managed across components.",
                    "suggestion": "Dedicate week 2 to useState and useEffect with practical task-list examples.",
                },
                {
                    "point": "Frontend-backend connection missing",
                    "detail": "Student has no plan for how React will call the FastAPI endpoints.",
                    "suggestion": "Week 3 must cover fetch/axios with CORS setup and live API calls.",
                },
                {
                    "point": "AI integration is vague",
                    "detail": "Student said 'add a button' without any technical plan.",
                    "suggestion": (
                        "Plan a POST call to HuggingFace inference API "
                        "sending task details and rendering the priority suggestion in the UI."
                    ),
                },
            ],
            "overall_understanding": "moderate",
            "recommended_focus_areas": [
                "React state management with useState and useEffect",
                "Frontend-backend integration with fetch and CORS",
                "AI API integration via HuggingFace inference endpoint",
            ],
        },
        "roadmap": None,
        "weekly_tasks": None,
        "current_week": 0,
        "completion_status": None,
        "task_quiz_results": None,
        "weekly_score": None,
        "start_date": "2025-06-01",
        "end_date": "2025-07-27",
        "blackout_dates": ["2025-06-20", "2025-06-21"],
    }

    result = node.run(state)
    roadmap = result["roadmap"]

    print(f"\nTotal weeks: {roadmap['total_weeks']}\n")
    for week in roadmap["weeks"]:
        diff = week.get("difficulty", "?").upper()
        print(f"Week {week['week_number']}  [{week['start_date']} → {week['end_date']}]  [{diff}]")
        print(f"  Theme      : {week['theme']}")
        print(f"  Goal       : {week['goal']}")
        print(f"  Topics     : {', '.join(week['topics'])}")
        print(f"  Deliverable: {week['deliverable']}")
        if week.get("focus_areas"):
            print(f"  Focus      : {', '.join(week['focus_areas'])}")
        print()

    print("=== MILESTONES ===")
    for m in roadmap["milestones"]:
        print(f"  Week {m['week']}: {m['description']}")