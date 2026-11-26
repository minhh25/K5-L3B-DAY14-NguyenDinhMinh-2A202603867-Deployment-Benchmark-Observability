"""Production mock agent: authentication, shared guards and JSON telemetry."""
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import budget_key, calculate_cost, check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask

class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": datetime.now(timezone.utc).isoformat(),
                   "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False)

logger = logging.getLogger("day14.agent")
logger.setLevel(settings.log_level)
logger.propagate = False
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.handlers[:] = [handler]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uvicorn owns SIGTERM: it drains requests before entering shutdown here.
    logger.info("startup", extra={"fields": {"environment": settings.environment}})
    yield
    r.close()
    logger.info("shutdown")

app = FastAPI(title="Day 14 Production AI Agent", lifespan=lifespan)

@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info("http_request", extra={"fields": {
            "request_id": request_id, "method": request.method,
            "path": request.url.path, "status": status,
            "ms": round((time.perf_counter() - started) * 1000, 2)}})

@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    logger.error("internal_error", extra={"fields": {
        "request_id": getattr(request.state, "request_id", ""),
        "error_type": type(exc).__name__}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)

@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}

@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"ready": True}

@app.post("/ask")
def ask(body: AskRequest, key: str = Depends(verify_api_key)):
    check_rate_limit(key)
    input_tokens = max(1, len(body.question) // 4)
    # Bound mock output to 512 estimated tokens and reserve atomically so concurrent
    # workers cannot spend the same remaining budget. This is a mock-specific bound.
    reserved = calculate_cost(input_tokens, 512)
    ledger = budget_key()  # pin UTC day across midnight and the provider call
    check_budget(reserved, key=ledger)
    try:
        answer = llm_ask(body.question)
    except Exception:
        record_cost(0, 0, reserved_cost=reserved, key=ledger)
        raise
    output_tokens = max(1, len(answer) // 4)
    cost = record_cost(input_tokens, output_tokens, reserved_cost=reserved, key=ledger)
    return {"question": body.question, "answer": answer,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                      "cost_usd": cost}}
