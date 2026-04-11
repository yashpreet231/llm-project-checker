from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app.agents.state import AgentState
import os
import json
import logging

logger = logging.getLogger(__name__)


class AnalyzerNode:
    """
    Analyzes the student's written approach to the project and produces
    a structured evaluation that feeds directly into the RoadmapNode.

    Inputs from state:
      - project              : project name + description
      - known_stack          : what the student already knows
      - unknown_stack        : what the student had to learn
      - prerequisites        : the concepts they studied
      - quiz_results         : how they performed concept-by-concept
      - student_approach     : their free-text plan for solving the project

    Output written to state["analysis"]:
      {
        "positives": [
          {
            "point": "<strength in the student's approach>",
            "detail": "<why this is good>"
          }
        ],
        "gaps": [
          {
            "point": "<missing or weak area>",
            "detail": "<what is wrong or missing and why it matters>",
            "suggestion": "<concrete fix the roadmap should address>"
          }
        ],
        "overall_understanding": "strong" | "moderate" | "weak",
        "recommended_focus_areas": ["<topic>", ...]
      }

    The RoadmapNode uses gaps + recommended_focus_areas to decide how to
    weight the weekly tasks.
    """

    SYSTEM_PROMPT = (
        "Respond ONLY with valid JSON. "
        "No explanation, no markdown fences, no text outside the JSON object."
    )

    ANALYZER_PROMPT = """You are an expert software engineering mentor evaluating a student's project plan.

=== PROJECT ===
Name       : {project_name}
Description: {project_description}

=== STUDENT PROFILE ===
Known stack  : {known_stack}
Unknown stack: {unknown_stack}

=== PREREQUISITE QUIZ PERFORMANCE ===
{quiz_summary}

=== STUDENT'S APPROACH ===
{student_approach}

=== YOUR TASK ===
Carefully read the student's approach and evaluate it against the project requirements.

Identify:
1. POSITIVES — things the student clearly understands and has planned well.
   - Be specific. Reference exact parts of their approach.
   - At least 2, at most 5.

2. GAPS — missing, vague, or incorrect parts of their plan.
   - Be specific. Quote or reference the weak part.
   - For each gap, give a concrete suggestion the roadmap should address.
   - At least 2, at most 6.

3. OVERALL UNDERSTANDING — rate as one of: "strong", "moderate", "weak"
   - strong  : covers most of the project correctly, minor gaps only
   - moderate: covers the basics but misses important technical details
   - weak    : approach is vague, incorrect, or missing major components

4. RECOMMENDED FOCUS AREAS — list 2-5 topics the weekly roadmap should
   emphasise given the gaps found. Be specific (e.g. "React state management"
   not just "React").

STRICT OUTPUT RULES:
- Output ONLY valid JSON.
- No text before or after.
- No markdown fences.
- All strings on a single line (no embedded newlines inside JSON strings).

Required format:
{{
  "positives": [
    {{
      "point": "<strength>",
      "detail": "<why this is good>"
    }}
  ],
  "gaps": [
    {{
      "point": "<weak area>",
      "detail": "<what is wrong or missing>",
      "suggestion": "<concrete fix the roadmap should address>"
    }}
  ],
  "overall_understanding": "strong" | "moderate" | "weak",
  "recommended_focus_areas": ["<topic>", ...]
}}
"""

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

    def _build_quiz_summary(self, state: AgentState) -> str:
        """
        Converts quiz_results into a readable summary for the prompt so the
        LLM knows which concepts the student struggled with.
        """
        results = state.get("quiz_results", [])
        if not results:
            return "No quiz data available."

        lines = []
        for r in results:
            status = "PASSED" if r["passed"] else "FAILED"
            lines.append(
                f"  - {r['concept']}: {r['score']}/5  [{status}]"
            )
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> dict:
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    def run(self, state: AgentState) -> AgentState:
        """
        Analyze the student's approach and write the result into state.

        State keys updated:
          analysis  <- dict with positives, gaps, overall_understanding,
                       recommended_focus_areas
        """
        project = state["project"]
        student_approach = state.get("student_approach", "")

        if not student_approach:
            raise ValueError("AnalyzerNode: state['student_approach'] is empty.")

        prompt = self.ANALYZER_PROMPT.format(
            project_name=project.get("name", ""),
            project_description=project.get("description", ""),
            known_stack=", ".join(state["known_stack"]),
            unknown_stack=", ".join(state["unknown_stack"]),
            quiz_summary=self._build_quiz_summary(state),
            student_approach=student_approach,
        )

        try:
            logger.info("AnalyzerNode: invoking LLM")
            response = self.llm.invoke([
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            analysis = self._parse_response(response.content)
            logger.info(
                f"AnalyzerNode: overall_understanding="
                f"{analysis.get('overall_understanding')} | "
                f"gaps={len(analysis.get('gaps', []))} | "
                f"positives={len(analysis.get('positives', []))}"
            )

            return {
                **state,
                "analysis": analysis,
            }

        except json.JSONDecodeError as e:
            logger.error(f"AnalyzerNode JSON error: {e}")
            raise
        except Exception as e:
            logger.error(f"AnalyzerNode error: {e}")
            raise


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    node = AnalyzerNode()
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
        "prerequisites": [
            {"concept": "REST APIs", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"},
            {"concept": "FastAPI", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"},
            {"concept": "React basics", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"},
            {"concept": "React hooks", "explanation": "...", "toy_task": "...", "estimated_time": "1 day"},
        ],
        "current_concept_index": 4,
        "quiz_results": [
            {"concept": "REST APIs",    "score": 5, "passed": True,  "questions": []},
            {"concept": "FastAPI",      "score": 4, "passed": True,  "questions": []},
            {"concept": "React basics", "score": 2, "passed": False, "questions": []},
            {"concept": "React hooks",  "score": 3, "passed": True,  "questions": []},
        ],
        "student_approach": (
            "I will create a React frontend with a task list page. "
            "Each task will be stored in a Python list on the backend. "
            "I'll use fetch() to call the API. "
            "For the AI part I'll just add a button that says 'suggest priority' "
            "but I haven't figured out how that will work yet. "
            "I'm not sure how to connect React to the backend."
        ),
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

    result = node.run(state)
    analysis = result["analysis"]

    print("\n=== POSITIVES ===")
    for p in analysis["positives"]:
        print(f"  + {p['point']}")
        print(f"    {p['detail']}")

    print("\n=== GAPS ===")
    for g in analysis["gaps"]:
        print(f"  - {g['point']}")
        print(f"    {g['detail']}")
        print(f"    Fix: {g['suggestion']}")

    print(f"\nOverall understanding : {analysis['overall_understanding']}")
    print(f"Recommended focus    : {', '.join(analysis['recommended_focus_areas'])}")