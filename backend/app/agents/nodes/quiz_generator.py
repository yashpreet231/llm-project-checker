from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState, QuizResult, QuizQuestion
import os
import json
import logging

logger = logging.getLogger(__name__)


class QuizGeneratorNode:
    """
    Generates a quiz for the CURRENT concept in state["prerequisites"]
    (identified by state["current_concept_index"]).

    The graph calls this node repeatedly — once per concept — forming the
    prerequisite loop.  After the student answers, a separate grading step
    appends a QuizResult to state["quiz_results"] and increments
    current_concept_index.  When the index reaches len(prerequisites), the
    loop exits to the planning phase.

    Each quiz contains:
      - 3 MCQ questions  : test conceptual understanding
      - 2 code questions : test practical ability (fill-in / write a snippet)

    The LLM is given the concept name, explanation, and toy task so the
    questions are tightly scoped — no questions about unrelated topics.
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON object."
    )


    QUIZ_PROMPT = """You are an expert software engineering teacher writing a short quiz.

The student just studied the following concept:

Concept     : {concept}
Explanation : {explanation}
Toy task    : {toy_task}

The student already knows: {known_stack}

Write a quiz with EXACTLY 5 questions:
- 3 MCQ questions          (type "mcq")
- 1 Fill-in-the-blank      (type "code")
- 1 Debugging question     (type "code")

MCQ rules:
- 4 answer options labelled A, B, C, D
- Exactly one correct answer
- Distractors must be plausible but clearly wrong
- Do NOT make trick questions

Fill-in-the-blank rules:
- MUST be a COMPLETE and VALID code snippet
- MUST include function/component structure (not a single line)
- MUST include exactly ONE blank marked as ___
- The code must be correct if the blank is filled

Example:
function TaskList(props) {{
  return (
    <ul>
      {{___}}
    </ul>
  );
}}

Debugging question rules:
- MUST be a COMPLETE code snippet
- MUST contain EXACTLY ONE realistic bug
- MUST ask clearly: "What is wrong in this code?"

Example:
function TaskList(props) {{
  return (
    <ul>
      {{props.tasks.map((task) => (
        <li>{{task}}</li>
      ))}}
    </ul>
  );
}}

What is wrong in this code?

STRICT RULES:
- Code questions MUST be complete snippets (no fragments)
- Code questions MUST NOT be a single line
- Every code question MUST contain ___ OR ask a debugging question
- DO NOT output plain code without a question

STRICT OUTPUT RULES:
- Output ONLY valid JSON
- No text before or after
- No markdown fences
- All strings must be on ONE line
- options must be null for code questions

Required format:
{{
  "concept": "{concept}",
  "questions": [
    {{
      "type": "mcq",
      "question": "<question>",
      "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
      "correct_answer": "A",
      "student_answer": null
    }},
    {{
      "type": "code",
      "question": "<code snippet>",
      "options": null,
      "correct_answer": "<answer>",
      "student_answer": null
    }}
  ],
  "passed": false,
  "score": 0
}}
"""

    PASS_THRESHOLD = 3  # student must answer at least 3/5 correctly to pass

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

    def _parse_response(self, raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    def run(self, state: AgentState) -> AgentState:
        """
        Generate a quiz for the concept at state["current_concept_index"].

        State keys updated:
          quiz_results  <- appended with the new QuizResult (unanswered, passed=False, score=0)

        NOTE:
          - student_answer fields are all null — the front-end fills these in.
          - After answers are submitted, call grade_quiz() to evaluate and
            decide whether to loop back (fail) or advance (pass).
        """
        index = state["current_concept_index"]
        prerequisites = state["prerequisites"]

        if index >= len(prerequisites):
            logger.warning("QuizGeneratorNode called but no more concepts to quiz.")
            return state

        concept_data = prerequisites[index]

        prompt = self.QUIZ_PROMPT.format(
            concept=concept_data["concept"],
            explanation=concept_data["explanation"],
            toy_task=concept_data["toy_task"],
            known_stack=", ".join(state["known_stack"]),
        )

        try:
            logger.info(
                f"QuizGeneratorNode: generating quiz for concept "
                f"{index + 1}/{len(prerequisites)}: '{concept_data['concept']}'"
            )
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            quiz: QuizResult = self._parse_response(response.content)

            # Append to existing results list
            updated_results = list(state["quiz_results"]) + [quiz]

            return {
                **state,
                "quiz_results": updated_results,
            }

        except json.JSONDecodeError as e:
            logger.error(f"QuizGeneratorNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"QuizGeneratorNode error: {e}")
            raise

    def grade_quiz(self, state: AgentState, student_answers: list[str]) -> AgentState:
        """
        Grade the most recently generated quiz with the student's answers.

        Args:
            state           : current AgentState
            student_answers : list of answer strings, one per question,
                              in the same order as quiz_results[-1]["questions"]
                              MCQ  → "A" / "B" / "C" / "D"
                              code → the student's code string

        Graph routing after this call:
          - quiz_results[-1]["passed"] == True  → advance (increment index, next concept or exit loop)
          - quiz_results[-1]["passed"] == False → loop back to PrerequisiteNode for the same concept

        State keys updated:
          quiz_results              <- last entry updated with answers, score, passed
          current_concept_index     <- incremented by 1 only if passed
        """
        quiz_results = list(state["quiz_results"])
        current_quiz: QuizResult = dict(quiz_results[-1])
        questions: list[QuizQuestion] = [dict(q) for q in current_quiz["questions"]]

        score = 0
        for i, question in enumerate(questions):
            answer = student_answers[i].strip() if i < len(student_answers) else ""
            question["student_answer"] = answer

            if question["type"] == "mcq":
                # Compare just the letter (first char) in case student writes "A. ..."
                if answer.upper().startswith(question["correct_answer"].upper()):
                    score += 1
            elif question["type"] == "code":
                # Normalise whitespace for a lenient match
                if answer.strip() == question["correct_answer"].strip():
                    score += 1

        passed = score >= self.PASS_THRESHOLD
        current_quiz["questions"] = questions
        current_quiz["score"] = score
        current_quiz["passed"] = passed

        quiz_results[-1] = current_quiz

        new_index = state["current_concept_index"] + (1 if passed else 0)

        logger.info(
            f"QuizGeneratorNode grade: concept='{current_quiz['concept']}' "
            f"score={score}/5 passed={passed} next_index={new_index}"
        )

        return {
            **state,
            "quiz_results": quiz_results,
            "current_concept_index": new_index,
        }


# ── router function for LangGraph ─────────────────────────────────────────────
def prereq_loop_router(state: AgentState) -> str:
    """
    LangGraph conditional edge function.

    Returns:
      "quiz_concept"   → still concepts left to quiz (stay in loop)
      "exit_prereq"    → all concepts passed, move to planning phase
    """
    index = state["current_concept_index"]
    total = len(state["prerequisites"])

    if index < total:
        return "quiz_concept"
    return "exit_prereq"


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Simulate state after PrerequisiteNode has already run
    state: AgentState = {
        "user_id": "student_01",
        "project": {
            "name": "AI Task Manager",
            "description": "A web app for task management with an AI priority assistant.",
        },
        "known_stack": ["HTML", "CSS", "basic Python"],
        "unknown_stack": ["React", "FastAPI", "REST APIs", "React hooks"],
        "prerequisites": [
            {
                "concept": "REST APIs",
                "explanation": (
                    "A REST API is a way for two programs to talk over HTTP. "
                    "The server exposes endpoints (URLs) and the client calls them "
                    "with verbs like GET, POST, PUT, DELETE to read or change data."
                ),
                "toy_task": (
                    "Build a tiny FastAPI server with two endpoints: "
                    "GET /tasks returns a hardcoded list of tasks, "
                    "POST /tasks accepts a JSON body and appends a new task."
                ),
                "estimated_time": "1 day",
            }
        ],
        "current_concept_index": 0,
        "quiz_results": [],
        "student_approach": None,
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

    node = QuizGeneratorNode()

    # Step 1 — generate quiz
    state = node.run(state)
    quiz = state["quiz_results"][-1]
    print(f"\nQuiz for: {quiz['concept']}\n")
    for i, q in enumerate(quiz["questions"], 1):
        print(f"Q{i} [{q['type'].upper()}] {q['question']}")
        if q["options"]:
            for opt in q["options"]:
                print(f"    {opt}")
        print()

    # Step 2 — simulate student answers (all correct = pass)
    answers = [
        q["correct_answer"] for q in quiz["questions"]
    ]
    state = node.grade_quiz(state, answers)

    result = state["quiz_results"][-1]
    print(f"Score : {result['score']}/5")
    print(f"Passed: {result['passed']}")
    print(f"Next concept index: {state['current_concept_index']}")
    print(f"Router would go to: {prereq_loop_router(state)}")