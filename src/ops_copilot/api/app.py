"""FastAPI app factory — lifespan owns the DB, checkpointer and graph."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ops_copilot.config import settings
from ops_copilot.db.init import init_db
from ops_copilot.workflow.graph import build_graph

log = logging.getLogger("ops_copilot.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    # One long-lived checkpointer connection per process (ADR-0001/0008)
    async with aiosqlite.connect(settings.checkpoint_db_path) as conn:
        saver = AsyncSqliteSaver(conn)
        app.state.graph = build_graph(saver)
        log.info("started — llm=%s model=%s tracing=%s",
                 settings.llm_enabled, settings.google_model, settings.langsmith_tracing)
        yield
    log.info("stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Adda247 Operations Copilot",
        version="1.0.0",
        description="Multi-agent course-launch control plane with durable "
                    "human-in-the-loop approval, guardrails and observability.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    from ops_copilot.api import routes
    app.include_router(routes.router)
    return app


app = create_app()
