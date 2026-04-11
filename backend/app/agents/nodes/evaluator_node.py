from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState
import os
import json
import logging

logger = logging.getLogger(__name__)


class EvaluatorNode:
    """
    Evaluates the student's overall performance for the current week and
    produces a score on a -5 to +5 scale, which is then mapped to 0-10
    for display.

    Signals used for evaluation:
      1. completion_status   : did they finish the deliverable? (binary)
      2. task_quiz_results   : how well did they understand what they built?
                               (MCQ + code score, 0-4)
      3. reflection answer   : qualitative signal — did they understand WHY?
      4. weekly_tasks        : complexity of what was asked this week
      5. roadmap difficulty  : expected effort level (easy/medium/hard)

    Scoring rubric (-5 to +5):
      +5 : Deliverable complete + quiz 4/4 + strong reflection
      +3 : Deliverable complete + quiz 3/4 + adequate reflection
      +1 : Deliverable complete + quiz 2/4 OR weak reflection
       0 : Deliverable complete + quiz 1/4
      -1 : Deliverable complete + quiz 0/4
      -3 : Deliverable NOT complete + some quiz attempt
      -5 : Deliverable NOT complete + no meaningful quiz attempt

    Output written to state:
      weekly_score          <- float, -5 to +5
      weekly_score_display  <- float, 0 to 10 (mapped for student-facing UI)
      evaluation_feedback   <- dict with detailed breakdown + encouragement message
      current_week          <- incremented by 1 if continuing
      project_complete      <- True if this was the final week

    The TaskGeneratorNode reads weekly_score next week to adjust pace.
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON object."
    )

    EVALUATOR_PROMPT = """You are a fair and encouraging software engineering mentor evaluating a student's weekly performance.

=== PROJECT ===
Name       : {project_name}
Description: {project_description}

=== THIS WEEK ===
Week number : {week_number} of {total_weeks}
Theme       : {theme}
Deliverable : {deliverable}
Difficulty  : {difficulty}

=== COMPLETION STATUS ===
Deliverable submitted: {completion_status}
Reason from completion check: {completion_reason}

=== TASK QUIZ RESULTS ===
Auto-graded score (MCQ + code): {quiz_score} / 4
Quiz passed: {quiz_passed}

Question-by-question breakdown:
{quiz_breakdown}

=== STUDENT REFLECTION ===
Question  : {reflection_question}
Answer    : {reflection_answer}

=== SCORING RUBRIC ===
Score the student on a scale of -5 to +5 using this rubric:

+5 : Deliverable complete + quiz 4/4 + reflection shows deep understanding
+4 : Deliverable complete + quiz 4/4 + adequate reflection
+3 : Deliverable complete + quiz 3/4 + adequate reflection
+2 : Deliverable complete + quiz 3/4 + weak reflection OR quiz 4/4 but no reflection
+1 : Deliverable complete + quiz 2/4
 0 : Deliverable complete + quiz 1/4
-1 : Deliverable complete + quiz 0/4
-2 : Deliverable NOT complete + quiz 3-4/4 (understands but didn't submit)
-3 : Deliverable NOT complete + quiz 1-2/4
-4 : Deliverable NOT complete + quiz 0/4
-5 : Deliverable NOT complete + no meaningful quiz attempt

Adjust by +1 if the difficulty was "hard" and the student scored at least +2.
Adjust by -1 if the difficulty was "easy" and the student scored below +2 (low effort).
Final score must stay within [-5, +5].

=== FEEDBACK RULES ===
1. strength    : 1-2 sentences on what the student did well this week (be specific)
2. improvement : 1-2 sentences on what to focus on next week (be specific and actionable)
3. message     : a short motivating message (1 sentence, encouraging but honest)
4. next_week_tip: one concrete thing they should do differently next week

Be honest — do not inflate scores or give generic praise.
Do not say "good job" or "well done" as standalone phrases.
Reference the actual quiz results and reflection in your feedback.

STRICT OUTPUT RULES:
- Output ONLY valid JSON
- No text before or after
- No markdown fences
- All strings on a single line

Required format:
{{
  "score": <int, -5 to +5>,
  "breakdown": {{
    "completion_points": <int>,
    "quiz_points": <int>,
    "reflection_points": <int>,
    "difficulty_adjustment": <int>
  }},
  "feedback": {{
    "strength": "<specific thing done well>",
    "improvement": "<specific actionable improvement>",
    "message": "<one honest motivating sentence>",
    "next_week_tip": "<one concrete thing to do differently>"
  }}
}}
"""

    def __init__(self, huggingface_api_key: str = None):
        api_key = huggingface_api_key or os.getenv("HF_API_KEY")
        self.llm = ChatHuggingFace(
            llm=HuggingFaceEndpoint(
                repo_id=os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
                huggingfacehub_api_token=api_key,
                task="text-generation",
                max_new_tokens=512,
            )
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _map_score_to_display(score: float) -> float:
        """
        Map internal score (-5 to +5) to student-facing display (0 to 10).
        Formula: display = (score + 5)   — linear mapping.
        """
        return round(score + 5, 1)

    def _build_quiz_breakdown(self, task_quiz_results: list) -> str:
        """
        Format the most recent task quiz question-by-question for the prompt.
        Skips the reflection question (type "text") since it is covered separately.
        """
        if not task_quiz_results:
            return "  No quiz data available."

        latest = task_quiz_results[-1]
        lines = []
        for i, q in enumerate(latest.get("questions", []), 1):
            if q["type"] == "text":
                continue
            correct = q.get("correct_answer", "")
            student = q.get("student_answer", "")
            verdict = "CORRECT" if (
                student and student.strip().upper().startswith(correct.strip().upper())
                if q["type"] == "mcq"
                else student.strip() == correct.strip()
            ) else "WRONG"
            lines.append(
                f"  Q{i} [{q['type'].upper()}]: {verdict}"
                f" | Expected: {correct[:60]}{'...' if len(correct) > 60 else ''}"
                f" | Got: {(student or 'no answer')[:60]}"
            )
        return "\n".join(lines) if lines else "  No graded questions."

    def _get_reflection(self, task_quiz_results: list) -> tuple[str, str]:
        """Extract the reflection question and student answer from the latest quiz."""
        if not task_quiz_results:
            return "N/A", "No reflection provided."
        latest = task_quiz_results[-1]
        for q in latest.get("questions", []):
            if q["type"] == "text":
                return (
                    q.get("question", "N/A"),
                    q.get("student_answer") or "No reflection provided.",
                )
        return "N/A", "No reflection provided."

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
        Evaluate the student's week and write results into state.

        Requires state keys:
          roadmap, current_week, completion_status, completion_reason,
          task_quiz_results, project

        State keys updated:
          weekly_score          <- float, -5 to +5
          weekly_score_display  <- float, 0 to 10
          evaluation_feedback   <- dict with strength, improvement, message, tip
          current_week          <- incremented by 1 (if not final week)
          project_complete      <- True if final week, else False
        """
        roadmap = state.get("roadmap")
        if not roadmap:
            raise ValueError("EvaluatorNode: state['roadmap'] is missing.")

        current_week = state.get("current_week", 1)
        total_weeks = roadmap.get("total_weeks", len(roadmap["weeks"]))
        week_plan = roadmap["weeks"][current_week - 1]

        task_quiz_results = state.get("task_quiz_results") or []
        latest_quiz = task_quiz_results[-1] if task_quiz_results else {}

        reflection_q, reflection_a = self._get_reflection(task_quiz_results)

        prompt = self.EVALUATOR_PROMPT.format(
            project_name=state["project"].get("name", ""),
            project_description=state["project"].get("description", ""),
            week_number=current_week,
            total_weeks=total_weeks,
            theme=week_plan["theme"],
            deliverable=week_plan["deliverable"],
            difficulty=week_plan.get("difficulty", "medium"),
            completion_status="YES" if state.get("completion_status") else "NO",
            completion_reason=state.get("completion_reason", "N/A"),
            quiz_score=latest_quiz.get("score", 0),
            quiz_passed=latest_quiz.get("passed", False),
            quiz_breakdown=self._build_quiz_breakdown(task_quiz_results),
            reflection_question=reflection_q,
            reflection_answer=reflection_a,
        )

        try:
            logger.info(f"EvaluatorNode: evaluating week {current_week}/{total_weeks}")
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            result = self._parse_response(response.content)

            raw_score = max(-5, min(5, int(result.get("score", 0))))
            display_score = self._map_score_to_display(raw_score)
            feedback = result.get("feedback", {})

            is_final_week = current_week >= total_weeks
            next_week = current_week if is_final_week else current_week + 1

            logger.info(
                f"EvaluatorNode: week {current_week} → score={raw_score} "
                f"({display_score}/10) | final={is_final_week}"
            )

            return {
                **state,
                "weekly_score": raw_score,
                "weekly_score_display": display_score,
                "evaluation_feedback": feedback,
                "current_week": next_week,
                "project_complete": is_final_week,
            }

        except json.JSONDecodeError as e:
            logger.error(f"EvaluatorNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"EvaluatorNode error: {e}")
            raise


# ── router for LangGraph ──────────────────────────────────────────────────────

def weekly_loop_router(state: AgentState) -> str:
    """
    LangGraph conditional edge after EvaluatorNode.

    Returns:
      "next_week"        → more weeks remain, loop back to TaskGeneratorNode
      "project_complete" → all weeks done, exit the execution loop
    """
    if state.get("project_complete"):
        return "project_complete"
    return "next_week"


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    node = EvaluatorNode()
    state: AgentState = {
        "user_id": "student_01",
        "project": {
            "name": "AI Task Manager",
            "description": "A web app for task management with an AI assistant.",
        },
        "known_stack": ["HTML", "CSS", "basic Python"],
        "unknown_stack": ["React", "FastAPI", "REST APIs", "React hooks"],
        "prerequisites": [],
        "current_concept_index": 4,
        "quiz_results": [],
        "student_approach": None,
        "analysis": None,
        "roadmap": {
            "total_weeks": 6,
            "weeks": [
                {
                    "week_number": 1,
                    "start_date": "2025-06-01",
                    "end_date": "2025-06-07",
                    "theme": "Building stateful React components using useState",
                    "goal": "Student can build a task list with add and delete using useState",
                    "topics": [
                        "JSX syntax and conditional rendering",
                        "useState hook",
                        "Props and callbacks",
                        "Array.map() with key props",
                    ],
                    "deliverable": "React <TaskList> component with add and delete using useState",
                    "focus_areas": ["React state management"],
                    "difficulty": "easy",
                },
                {
                    "week_number": 2,
                    "start_date": "2025-06-08",
                    "end_date": "2025-06-14",
                    "theme": "Connecting React to FastAPI using fetch and handling CORS",
                    "goal": "Student can fetch live task data from the FastAPI backend",
                    "topics": [
                        "fetch() with async/await",
                        "useEffect for data fetching on mount",
                        "FastAPI CORS middleware setup",
                        "Error and loading state handling",
                    ],
                    "deliverable": "React TaskList fetching real data from GET /tasks FastAPI endpoint",
                    "focus_areas": ["Frontend-backend integration"],
                    "difficulty": "medium",
                },
            ],
            "milestones": [],
        },
        "weekly_tasks": None,
        "current_week": 1,
        "completion_status": True,
        "completion_reason": "TaskList.jsx and App.jsx were modified with useState logic.",
        "task_quiz_results": [
            {
                "week": 1,
                "concept": "Building stateful React components using useState",
                "score": 3,
                "passed": True,
                "questions": [
                    {
                        "type": "mcq",
                        "question": "What happens when you call setTasks([]) in your TaskList component?",
                        "options": ["A. Nothing", "B. The component re-renders with an empty list", "C. The page reloads", "D. An error is thrown"],
                        "correct_answer": "B",
                        "student_answer": "B",
                    },
                    {
                        "type": "mcq",
                        "question": "Why must each list item have a unique key prop in React?",
                        "options": ["A. For CSS styling", "B. To help React efficiently update only changed items", "C. It is optional", "D. For accessibility"],
                        "correct_answer": "B",
                        "student_answer": "B",
                    },
                    {
                        "type": "code",
                        "question": "const [tasks, ___] = useState([]); Fill in the blank.",
                        "options": None,
                        "correct_answer": "setTasks",
                        "student_answer": "setTasks",
                    },
                    {
                        "type": "code",
                        "question": "function TaskList({ tasks }) { return <ul>{tasks.map(t => <li>{t}</li>)}</ul>; } What is wrong?",
                        "options": None,
                        "correct_answer": "Each <li> is missing a unique key prop",
                        "student_answer": "missing key prop on li elements",
                    },
                    {
                        "type": "text",
                        "question": "You used useState to manage your task list. What would break if you used a regular variable instead, and why?",
                        "options": None,
                        "correct_answer": None,
                        "student_answer": (
                            "If I used a regular variable, React wouldn't know the data changed "
                            "so it wouldn't re-render the component and the UI would stay the same "
                            "even though the data changed."
                        ),
                    },
                ],
            }
        ],
        "weekly_score": None,
        "weekly_score_display": None,
        "evaluation_feedback": None,
        "start_date": "2025-06-01",
        "end_date": "2025-07-27",
        "blackout_dates": [],
    }

    result = node.run(state)

    print(f"\nWeek {state['current_week']} Evaluation")
    print(f"  Raw score   : {result['weekly_score']} / 5")
    print(f"  Display     : {result['weekly_score_display']} / 10")
    print(f"\nFeedback:")
    fb = result["evaluation_feedback"]
    print(f"  Strength    : {fb.get('strength')}")
    print(f"  Improvement : {fb.get('improvement')}")
    print(f"  Message     : {fb.get('message')}")
    print(f"  Next week   : {fb.get('next_week_tip')}")
    print(f"\nProject complete : {result.get('project_complete')}")
    print(f"Next week number : {result.get('current_week')}")
    print(f"Router → {weekly_loop_router(result)}")