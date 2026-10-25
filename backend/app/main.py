"""
EXUNU backend (FastAPI).
  uvicorn app.main:app --reload --port 8000
Starts the candle-close scheduler (signals → Telegram) and the Telegram command bot.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import account, market, settings as settings_api, strategy
from .auth import ensure_admin
from .config import settings
from .db import SessionLocal, init_db
from .telegram import scheduler
from .telegram.bot import poll_forever

STARTED = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_admin(db)
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


app = FastAPI(title="EXUNU API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (account.router, market.router, strategy.router, settings_api.router):
    app.include_router(r)


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
    """Also the keep-alive target for an uptime pinger (Render free sleeps after 15 min idle)."""
    return {"status": "ok", "uptimeSeconds": int(time.time() - STARTED), "scheduler": settings.scheduler_enabled, "telegramPolling": settings.telegram_polling}
