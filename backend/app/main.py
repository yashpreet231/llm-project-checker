from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api.routers import sessions, prereq, planning, weekly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI Teacher Agent API — startup")
    yield
    logger.info("AI Teacher Agent API — shutdown")


app = FastAPI(
    title="AI Teacher Agent",
    description="Personalised project-based learning platform powered by LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],       # tighten to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
app.include_router(prereq.router,   prefix="/prereq",   tags=["Prerequisite"])
app.include_router(planning.router, prefix="/planning",  tags=["Planning"])
app.include_router(weekly.router,   prefix="/weekly",    tags=["Weekly"])


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}