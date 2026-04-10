import json
from app.services.llm import call_llama  # ✅ THIS LINE FIXES ERROR

def quiz_node(state):
    prerequisites = state.get("prerequisites", [])

    prerequisites_text = json.dumps(prerequisites, indent=2)

    prompt = f"""
    You are a quiz generator.

    STRICT RULES:
    - Output ONLY valid JSON
    - No explanation

    Format:
    [
      {{
        "question": "",
        "options": ["", "", "", ""],
        "answer": ""
      }}
    ]

    Generate EXACTLY 3 questions based on:

    {prerequisites_text}
    """

    response = call_llama(prompt)

    if isinstance(response, dict) and "error" in response:
        state["quiz"] = []
    else:
        state["quiz"] = response

    return state