# backend/app/agents/nodes/prerequisite.py

from app.services.llm import call_llama

def prerequisite_node(state):
    prompt = fprompt = f"""
    You are an expert teacher.

    STRICT RULES:
    - Output ONLY valid JSON
    - Do NOT include explanations
    - Do NOT include text before or after JSON
    - Ensure JSON is parsable

    Format:
    [
    {{
        "concept": "",
        "toy_task": ""
    }}
    ]

    Student knows: {state['known_stack']}
    Student does not know: {state['unknown_stack']}
    Project: {state['project']}
    """

    response = call_llama(prompt)

    state["prerequisites"] = response
    return state