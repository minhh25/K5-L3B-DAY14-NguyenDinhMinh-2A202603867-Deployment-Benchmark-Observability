"""Lazy Redis connections: a missing dependency must not break liveness."""
import hashlib
import redis
from fastapi import HTTPException
from app.config import settings

r = redis.from_url(settings.redis_url, decode_responses=True,
                   socket_connect_timeout=1, socket_timeout=1)

def state_prefix(api_key: str | None = None) -> str:
    digest = hashlib.sha256((api_key or settings.agent_api_key).encode()).hexdigest()
    return f"day14:{settings.environment}:{digest}"

def redis_healthy() -> bool:
    try:
        return bool(r.ping())
    except redis.RedisError:
        return False

def dependency_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="State store unavailable; please retry")
