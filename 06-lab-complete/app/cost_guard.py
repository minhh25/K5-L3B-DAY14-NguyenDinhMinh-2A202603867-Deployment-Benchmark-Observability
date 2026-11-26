"""Daily simulated token spending in Redis, with atomic reservations."""
from datetime import datetime, timezone
import redis
from fastapi import HTTPException
from app.config import settings
from app.redis_client import dependency_unavailable, r, state_prefix

# Lab simulation rates, USD per 1K tokens (not live provider prices).
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
RESERVE = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) or current + tonumber(ARGV[2]) > tonumber(ARGV[1]) then
    return 0
end
redis.call('INCRBYFLOAT', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], 172800)
return 1
"""

def budget_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{state_prefix()}:cost:{day}"

def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K

def check_budget(estimated_cost: float = 0.0, *, key: str | None = None) -> None:
    try:
        allowed = r.eval(RESERVE, 1, key or budget_key(),
                         settings.daily_budget_usd, estimated_cost)
    except redis.RedisError as exc:
        raise dependency_unavailable() from exc
    if not allowed:
        raise HTTPException(status_code=402, detail="Daily budget exhausted or insufficient")

def record_cost(input_tokens: int, output_tokens: int, *, reserved_cost: float = 0.0,
                key: str | None = None) -> float:
    cost = calculate_cost(input_tokens, output_tokens)
    ledger = key or budget_key()
    try:
        with r.pipeline() as pipeline:
            pipeline.incrbyfloat(ledger, cost - reserved_cost)
            pipeline.expire(ledger, 172800)
            pipeline.execute()
    except redis.RedisError as exc:
        raise dependency_unavailable() from exc
    return cost
