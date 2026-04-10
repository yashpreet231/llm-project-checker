# backend/app/main.py

from fastapi import FastAPI
from app.agents.graph import build_graph

app = FastAPI()

graph = build_graph()

@app.get("/")
def root():
    return {"message": "AI Teacher Agent Running 🚀"}


@app.post("/run-agent")
def run_agent():
    state = {
        "user_id": "1",
        "project": {
            "name": "AI Task Manager",
            "tech_stack": ["React", "FastAPI"]
        },
        "known_stack": ["HTML", "CSS"],
        "unknown_stack": ["React", "FastAPI"],

        "prerequisites": [],
        "quiz": []
    }

    result = graph.invoke(state)

    return result