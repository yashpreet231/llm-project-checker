# AI Teacher Agent

Personalised, project-based learning driven by a LangGraph agent.
A student declares what they want to build and what they already know; the
agent turns that into a prerequisites loop, a weekly roadmap, daily tasks,
GitHub-verified completion checks, and per-week evaluation.

```
Teacher-Agent/
├── backend/      FastAPI + LangGraph — the agent, routes, services
├── frontend/     Next.js 16 / React 19 — student + teacher UI
├── database/     Target Postgres schema (the demo runs in-memory)
└── requirements.txt
```

## Quick start

### Backend

```bash
cd Teacher-Agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# minimal .env — copy into backend/.env
# LLM_PROVIDER=groq
# GROQ_API_KEY=sk-...
# GITHUB_TOKEN=ghp_...     (optional, lifts the 60 req/hr anon limit)

cd backend
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the OpenAPI explorer.

### Frontend

```bash
cd Teacher-Agent/frontend
npm install
npm run dev   # http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

## The flow

1. **Setup** (`/`) — student enters project + known/unknown stack + repo URL.
2. **Prereqs** — the agent generates concept 1, quizzes, advances on pass.
3. **Approach** — student writes how they'd build it; agent analyses.
4. **Roadmap** — week-by-week plan with milestones, respecting blackout dates.
5. **Weekly loop** — daily tasks → push to GitHub → completion check → quiz → evaluation → next week.
6. **Done** — final score across all weeks.

## LLM providers

Swap via `LLM_PROVIDER` in `backend/.env`:

| Value          | Notes                               |
|----------------|-------------------------------------|
| `groq`         | Free, default, `llama-3.1-8b-instant` |
| `ollama`       | Local, free, requires Ollama        |
| `huggingface`  | Paid after free quota               |
| `openai`       | Paid                                |

## API surface (high-level)

| Route                               | Purpose                        |
|-------------------------------------|--------------------------------|
| `POST /sessions/start`              | kick off prereqs for a student |
| `POST /prereq/{sid}/submit`         | grade + advance concept        |
| `POST /planning/{sid}/approach`     | analyse + build roadmap        |
| `POST /weekly/{sid}/start`          | generate 5 daily tasks         |
| `POST /weekly/{sid}/check`          | GitHub completion check        |
| `GET  /weekly/{sid}/quiz`           | this week's quiz               |
| `POST /weekly/{sid}/quiz/submit`    | grade + evaluate               |
| `GET  /projects`                    | teacher catalog                |
| `GET  /dashboard`                   | aggregate teacher view         |
| `POST /agents/{node}/run`           | invoke a single node (debug)   |

## Persistence

The demo uses `app.api.store` (in-memory dict). To move to Postgres, run
`database/schema.sql` and replace `store.get/set/delete/exists` with
something asyncpg-backed — no route changes required.
