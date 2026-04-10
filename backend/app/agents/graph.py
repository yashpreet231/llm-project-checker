# backend/app/agents/graph.py

from langgraph.graph import StateGraph
from app.agents.state import AgentState

from app.agents.nodes.prerequisite import prerequisite_node
from app.agents.nodes.quiz import quiz_node

def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("prerequisite", prerequisite_node)
    builder.add_node("quiz", quiz_node)

    builder.set_entry_point("prerequisite")

    builder.add_edge("prerequisite", "quiz")

    return builder.compile()