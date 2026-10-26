"""
LiquidityDissection backend (FastAPI).
  uvicorn app.main:app --reload --port 8000
Starts the candle-close scheduler (signals → Telegram) and the Telegram command bot.
"""

import asyncio
import os
import re
import hmac
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import account, market, settings as settings_api, strategy
from .auth import ensure_admin
from .config import settings
from .db import SessionLocal, engine, init_db
from .telegram import scheduler
from .telegram.bot import poll_forever

STARTED = time.time()
_ready = False
_setup_error: Optional[str] = None


def _prepare() -> None:
    """Creates the tables and the first admin (idempotent)."""
    global _ready
    if _ready:
        return
    init_db()
    with SessionLocal() as db:
        ensure_admin(db)
    _ready = True


def _try_prepare() -> Optional[str]:
    """Like _prepare, but returns the error (password hidden) instead of crashing the process."""
    global _setup_error
    try:
        _prepare()
        _setup_error = None
    except Exception as err:  # a crash here would take the whole serverless function down
        _setup_error = re.sub(r"://[^/@\s]+@", "://***@", f"{type(err).__name__}: {err}")[:600]
        print(f"[startup] database setup failed: {_setup_error}")
    return _setup_error


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.database_missing:
        _try_prepare()
    stop = asyncio.Event()
    tasks: list[asyncio.Task] = []
    if settings.scheduler_enabled:
        tasks += scheduler.start(stop)
    if settings.telegram_polling:
        tasks.append(asyncio.create_task(poll_forever(stop)))
    yield
    stop.set()
    for t in tasks:
        t.cancel()


app = FastAPI(title="LiquidityDissection API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (account.router, market.router, strategy.router, settings_api.router):
    app.include_router(r)


def _deployment_info() -> dict:
    """Which Vercel deployment answered, and which database variable NAMES it sees (never their values)."""
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")
    return {"environment": os.environ.get("VERCEL_ENV"), "branch": os.environ.get("VERCEL_GIT_COMMIT_REF"), "commit": sha[:7] or None,
            "databaseVariablesSeen": sorted(k for k in os.environ if ("DATABASE" in k or "POSTGRES" in k or k.startswith("STORAGE")) and os.environ[k])}


@app.middleware("http")
async def ensure_prepared(request: Request, call_next):
    if settings.database_missing:
        msg = ("No database configured: connect a Neon/Postgres database to this Vercel project "
               "(Storage → Neon) or set DATABASE_URL for Production, then redeploy.")
        return JSONResponse({"success": False, "status": "error", "database": "missing", "error": msg, "detail": msg,
                             "deployment": _deployment_info()}, status_code=503)
    # Serverless hosts do not always run the lifespan startup: prepare on the first request instead
    if not _ready:
        err = await asyncio.to_thread(_try_prepare)
        if err:
            return JSONResponse({"success": False, "status": "error", "database": "setup failed", "error": err, "detail": err}, status_code=503)
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse({"success": False, "error": msg, "detail": msg}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return JSONResponse({"success": False, "error": msg, "detail": msg}, status_code=422)


@app.api_route("/api/health", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Database-aware health check and keep-alive target."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unavailable"}, status_code=503)
    return {"status": "ok", "database": "ok", "uptimeSeconds": int(time.time() - STARTED),
            "scheduler": settings.scheduler_enabled, "telegramPolling": settings.telegram_polling}


@app.api_route("/api/cron/tick", methods=["GET", "POST"])
async def cron_tick(authorization: Optional[str] = Header(None)):
    """One scheduled strategy pass for serverless hosts; protect it with CRON_SECRET."""
    if not settings.cron_secret:
        raise HTTPException(503, "CRON_SECRET is not configured")
    if not hmac.compare_digest(authorization or "", f"Bearer {settings.cron_secret}"):
        raise HTTPException(401, "Invalid cron authorization")
    return {"success": True, "results": await scheduler.tick()}
