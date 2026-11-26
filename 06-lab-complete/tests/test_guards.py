"""Concurrency tests against a real Redis. Never run against a production Redis.
REDIS_URL=redis://localhost:16379/0 python -m unittest discover -s tests -v
"""
import concurrent.futures
import os
import secrets
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ['AGENT_API_KEY'] = secrets.token_urlsafe(32)
os.environ['ENVIRONMENT'] = 'integration-test'
from fastapi import HTTPException
from app import cost_guard, rate_limiter
from app.config import settings
from app.redis_client import r, state_prefix

class AtomicGuards(unittest.TestCase):
    def tearDown(self):
        keys = list(r.scan_iter(f'{state_prefix()}*'))
        if keys:
            r.delete(*keys)

    def test_sliding_window_is_shared_and_atomic(self):
        def attempt(_):
            try:
                rate_limiter.check_rate_limit(settings.agent_api_key)
                return 200
            except HTTPException as exc:
                self.assertEqual(exc.status_code, 429)
                self.assertGreaterEqual(int(exc.headers['Retry-After']), 1)
                return 429
        with patch.object(rate_limiter, 'settings', replace(settings, rate_limit_per_minute=5)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
                codes = list(pool.map(attempt, range(40)))
        self.assertEqual(codes.count(200), 5)
        self.assertEqual(codes.count(429), 35)

    def test_expired_requests_leave_the_window(self):
        clock = r.time()
        now = clock[0] + clock[1]/1e6
        r.zadd(f'{state_prefix()}:rate', {'old': now - 61})
        with patch.object(rate_limiter, 'settings', replace(settings, rate_limit_per_minute=1)):
            rate_limiter.check_rate_limit(settings.agent_api_key)
        self.assertEqual(r.zcard(f'{state_prefix()}:rate'), 1)

    def test_budget_reservations_cannot_overspend(self):
        ledger = cost_guard.budget_key()
        def attempt(_):
            try:
                cost_guard.check_budget(.0003, key=ledger)
                return True
            except HTTPException as exc:
                self.assertEqual(exc.status_code, 402)
                return False
        with patch.object(cost_guard, 'settings', replace(settings, daily_budget_usd=.001)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
                allowed = list(pool.map(attempt, range(30)))
        self.assertEqual(sum(allowed), 3)
        self.assertAlmostEqual(float(r.get(ledger)), .0009)
        for _ in range(3):
            cost_guard.record_cost(0, 0, reserved_cost=.0003, key=ledger)
        self.assertAlmostEqual(float(r.get(ledger)), 0)

    def test_actual_cost_reconciles_the_reservation(self):
        ledger = cost_guard.budget_key()
        cost_guard.check_budget(.0003, key=ledger)
        cost = cost_guard.record_cost(100, 100, reserved_cost=.0003, key=ledger)
        self.assertAlmostEqual(cost, .000075)
        self.assertAlmostEqual(float(r.get(ledger)), cost)

if __name__ == '__main__':
    unittest.main()
