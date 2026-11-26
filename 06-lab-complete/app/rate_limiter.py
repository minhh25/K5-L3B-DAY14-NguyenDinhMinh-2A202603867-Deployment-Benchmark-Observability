"""Atomic Redis sliding window, shared across processes and restarts."""
import math
import uuid
import redis
from fastapi import HTTPException
from app.config import settings
from app.redis_client import dependency_unavailable, r, state_prefix

WINDOW = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 60)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return tostring(math.max(1, tonumber(oldest[2]) + 60 - now))
end
redis.call('ZADD', KEYS[1], now, ARGV[2])
redis.call('EXPIRE', KEYS[1], 61)
return '0'
"""

def check_rate_limit(key: str) -> None:
    try:
        retry = float(r.eval(WINDOW, 1, f"{state_prefix(key)}:rate",
                             settings.rate_limit_per_minute, uuid.uuid4().hex))
    except redis.RedisError as exc:
        raise dependency_unavailable() from exc
    if retry:
        raise HTTPException(status_code=429, detail="Rate limit exceeded",
                            headers={"Retry-After": str(math.ceil(retry))})
