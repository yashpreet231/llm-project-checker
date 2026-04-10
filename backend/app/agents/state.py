# backend/app/agents/state.py

from typing import TypedDict, List, Dict

class AgentState(TypedDict):
    user_id: str
    project: Dict
    known_stack: List[str]
    unknown_stack: List[str]

    prerequisites: List[Dict]
    quiz: List[Dict]