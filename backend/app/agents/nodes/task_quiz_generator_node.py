from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState, QuizResult, QuizQuestion
import os
import json
import logging

logger = logging.getLogger(__name__)


class TaskQuizGeneratorNode:
    """
    Generates a quiz based on the ACTUAL WORK the student submitted this week.

    Unlike the prerequisite QuizGeneratorNode (which tests concept theory),
    this node tests whether the student UNDERSTANDS what they just built.

    Inputs from state:
      - weekly_tasks           : the 5 tasks assigned this week (what they built)
      - roadmap.weeks[current_week - 1] : theme, topics, deliverable of this week
      - current_week           : which week we are in

    The quiz has 5 questions:
      - 2 MCQ  : conceptual understanding of THIS week's topics
      - 2 code : directly related to the code they wrote this week
      - 1 reflection : open-ended — "why did you choose this approach?"

    The reflection question is always type "text" — it is NOT auto-graded.
    It is read by the EvaluatorNode as a qualitative signal.

    Output appended to state["task_quiz_results"]:
      [
        {
          "week": <int>,
          "concept": "<week theme>",
          "questions": [ ... ],
          "passed": false,      <- set after grading
          "score": 0            <- set after grading
        }
      ]
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON object."
    )

    TASK_QUIZ_PROMPT = """You are an expert software engineering mentor writing a short quiz to check if a student truly understands what they just built this week.

=== WHAT THE STUDENT BUILT THIS WEEK ===
Week number  : {week_number}
Theme        : {theme}
Deliverable  : {deliverable}
Topics covered:
{topics}

Daily tasks completed:
{tasks_summary}

=== QUIZ RULES ===

Write EXACTLY 5 questions:
  - 2 MCQ questions        (type "mcq")
  - 2 code questions       (type "code")
  - 1 reflection question  (type "text")

MCQ rules:
  - 4 options labelled A, B, C, D
  - One correct answer
  - Questions must be about the SPECIFIC code or concepts from THIS week
  - Not generic theory — ask about what they actually built
  - WRONG: "What is useState?" (too generic)
  - RIGHT: "In your TaskList component, what would happen if you forgot the key prop on each list item?"

Code question rules:
  - Type 1 (fill-in-the-blank): show a code snippet from this week's topic with ONE blank marked ___
  - Type 2 (debugging): show a code snippet with ONE realistic bug and ask "What is wrong in this code?"
  - Both must be COMPLETE snippets (not single lines)
  - correct_answer for fill-in: only the missing part
  - correct_answer for debugging: a clear description of the bug and the fix

Reflection question rules:
  - type must be "text"
  - options must be null
  - correct_answer must be null  (this is NOT auto-graded)
  - Ask ONE open-ended question about a decision the student made this week
  - WRONG: "What did you learn?"
  - RIGHT: "You used useState to manage your task list. What would break if you used a regular variable instead, and why?"

STRICT OUTPUT RULES:
  - Output ONLY valid JSON
  - No text before or after
  - No markdown fences
  - All strings on a single line (no embedded newlines inside JSON strings)
  - options must be null for code and text questions

Required format:
{{
  "week": {week_number},
  "concept": "{theme}",
  "questions": [
    {{
      "type": "mcq",
      "question": "<specific question about what they built>",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "student_answer": null
    }},
    {{
      "type": "code",
      "question": "<complete code snippet with ___ OR debugging question>",
      "options": null,
      "correct_answer": "<missing part or bug description>",
      "student_answer": null
    }},
    {{
      "type": "text",
      "question": "<open-ended reflection about a decision they made>",
      "options": null,
      "correct_answer": null,
      "student_answer": null
    }}
  ],
  "passed": false,
  "score": 0
}}
"""

    PASS_THRESHOLD = 3   # out of 4 auto-graded questions (MCQ x2 + code x2)

    def __init__(self, huggingface_api_key: str = None):
        api_key = huggingface_api_key or os.getenv("HF_API_KEY")
        self.llm = ChatHuggingFace(
            llm=HuggingFaceEndpoint(
                repo_id=os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
                huggingfacehub_api_token=api_key,
                task="text-generation",
                max_new_tokens=1024,
            )
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_tasks_summary(self, weekly_tasks: list) -> str:
        """
        Summarise what the student built each day so the LLM can write
        questions that reference actual work, not generic topics.
        """
        if not weekly_tasks:
            return "  No task data available."
        lines = []
        for task in weekly_tasks:
            lines.append(f"  Day {task['day']}: {task['title']}")
            lines.append(f"    Deliverable: {task['submission']['filename']} in {task['submission']['github_folder']}")
        return "\n".join(lines)

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
        Generate the task quiz for the current week and append to state.

        Requires state keys:
          roadmap, current_week, weekly_tasks

        State keys updated:
          task_quiz_results  <- new QuizResult appended (unanswered)
        """
        roadmap = state.get("roadmap")
        if not roadmap:
            raise ValueError("TaskQuizGeneratorNode: state['roadmap'] is missing.")

        current_week = state.get("current_week", 1)
        week_plan = roadmap["weeks"][current_week - 1]
        weekly_tasks = state.get("weekly_tasks") or []

        prompt = self.TASK_QUIZ_PROMPT.format(
            week_number=current_week,
            theme=week_plan["theme"],
            deliverable=week_plan["deliverable"],
            topics="\n".join(f"  - {t}" for t in week_plan["topics"]),
            tasks_summary=self._build_tasks_summary(weekly_tasks),
        )

        try:
            logger.info(f"TaskQuizGeneratorNode: generating quiz for week {current_week}")
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            quiz: QuizResult = self._parse_response(response.content)

            existing = list(state.get("task_quiz_results") or [])
            existing.append(quiz)

            return {
                **state,
                "task_quiz_results": existing,
            }

        except json.JSONDecodeError as e:
            logger.error(f"TaskQuizGeneratorNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"TaskQuizGeneratorNode error: {e}")
            raise

    def grade_quiz(self, state: AgentState, student_answers: list[str]) -> AgentState:
        """
        Grade the most recent task quiz with the student's answers.

        Args:
            state           : current AgentState
            student_answers : list of answer strings, one per question
                              MCQ  → "A" / "B" / "C" / "D"
                              code → student's code string
                              text → student's free-text reflection (stored, not scored)

        Auto-grades only MCQ and code questions (4 questions).
        Reflection (type "text") is stored in student_answer but not scored —
        the EvaluatorNode reads it as a qualitative signal.

        State keys updated:
          task_quiz_results  <- last entry updated with answers, score, passed
        """
        task_quiz_results = list(state.get("task_quiz_results") or [])
        if not task_quiz_results:
            raise ValueError("TaskQuizGeneratorNode.grade_quiz: no quiz to grade.")

        current_quiz = dict(task_quiz_results[-1])
        questions: list[QuizQuestion] = [dict(q) for q in current_quiz["questions"]]

        score = 0
        for i, question in enumerate(questions):
            answer = student_answers[i].strip() if i < len(student_answers) else ""
            question["student_answer"] = answer

            if question["type"] == "mcq":
                if answer.upper().startswith(question["correct_answer"].upper()):
                    score += 1
            elif question["type"] == "code":
                if answer.strip() == question["correct_answer"].strip():
                    score += 1
            # type "text" → stored only, not scored

        passed = score >= self.PASS_THRESHOLD
        current_quiz["questions"] = questions
        current_quiz["score"] = score
        current_quiz["passed"] = passed

        task_quiz_results[-1] = current_quiz

        logger.info(
            f"TaskQuizGeneratorNode grade: week={current_quiz['week']} "
            f"score={score}/4 passed={passed}"
        )

        return {
            **state,
            "task_quiz_results": task_quiz_results,
        }


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    node = TaskQuizGeneratorNode()
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
                        "JSX syntax and conditional rendering with ternary operators",
                        "useState hook — declaring, reading, and updating state",
                        "Props — passing data and callbacks between parent and child",
                        "Rendering lists with Array.map() and unique key props",
                    ],
                    "deliverable": (
                        "React <TaskList> component with add and delete "
                        "functionality using useState — no backend yet"
                    ),
                    "focus_areas": ["React state management with useState and useEffect"],
                    "difficulty": "easy",
                }
            ],
            "milestones": [],
        },
        "weekly_tasks": [
            {
                "day": 1, "title": "Set up React project and build basic TaskCard component",
                "description": "...", "steps": [],
                "submission": {"github_folder": "frontend/src/components", "filename": "TaskCard.jsx", "commit_message": "feat: add TaskCard component"},
                "estimated_hours": 2,
            },
            {
                "day": 2, "title": "Add useState to manage task list in App component",
                "description": "...", "steps": [],
                "submission": {"github_folder": "frontend/src", "filename": "App.jsx", "commit_message": "feat: add task state management"},
                "estimated_hours": 2,
            },
            {
                "day": 3, "title": "Build AddTask form component with controlled input",
                "description": "...", "steps": [],
                "submission": {"github_folder": "frontend/src/components", "filename": "AddTask.jsx", "commit_message": "feat: add AddTask form"},
                "estimated_hours": 2,
            },
            {
                "day": 4, "title": "Add delete functionality with filter and props callback",
                "description": "...", "steps": [],
                "submission": {"github_folder": "frontend/src/components", "filename": "TaskList.jsx", "commit_message": "feat: add delete task feature"},
                "estimated_hours": 2,
            },
            {
                "day": 5, "title": "Polish TaskList and push final deliverable to GitHub",
                "description": "...", "steps": [],
                "submission": {"github_folder": "frontend/src", "filename": "TaskList.jsx", "commit_message": "feat: complete week 1 task list deliverable"},
                "estimated_hours": 2,
            },
        ],
        "current_week": 1,
        "completion_status": True,
        "task_quiz_results": None,
        "weekly_score": None,
        "start_date": "2025-06-01",
        "end_date": "2025-07-27",
        "blackout_dates": [],
    }

    # Step 1 — generate quiz
    state = node.run(state)
    quiz = state["task_quiz_results"][-1]

    print(f"\nTask Quiz — Week {quiz['week']}: {quiz['concept']}\n")
    for i, q in enumerate(quiz["questions"], 1):
        print(f"Q{i} [{q['type'].upper()}] {q['question']}")
        if q["options"]:
            for opt in q["options"]:
                print(f"    {opt}")
        print()

    # Step 2 — simulate student answers
    answers = []
    for q in quiz["questions"]:
        if q["type"] == "mcq":
            answers.append(q["correct_answer"])          # all correct
        elif q["type"] == "code":
            answers.append(q["correct_answer"])          # all correct
        else:
            answers.append("I used useState because it re-renders the component when the array changes, unlike a regular variable.")

    state = node.grade_quiz(state, answers)
    result = state["task_quiz_results"][-1]

    print(f"Score : {result['score']}/4")
    print(f"Passed: {result['passed']}")
    print(f"Reflection stored: {result['questions'][-1]['student_answer']}")