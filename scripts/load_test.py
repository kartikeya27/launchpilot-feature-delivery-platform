#!/usr/bin/env python3
"""Bounded HTTP load test with explicit pass/fail thresholds. No third-party dependencies.

Runs against localhost by default. Never use load test on a public site without authorization.
"""
import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct * len(values)) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--flag", help="Evaluate a seeded flag with tracking disabled")
    parser.add_argument("--environment", default="production", choices=["development", "staging", "production"])
    parser.add_argument("--country", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--token", default=None, help="OIDC bearer token for authorized evaluation")
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--p95-ms", type=float, default=2000)
    parser.add_argument("--allow-remote", action="store_true", help="Explicit permission for non-loopback targets")
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        parser.error("Only valid HTTP(S) URLs are allowed")
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
        parser.error("Refusing non-loopback load testing without --allow-remote")
    if not (1 <= args.requests <= 10000 and 1 <= args.concurrency <= 100):
        parser.error("requests must be 1–10000; concurrency must be 1–100")
    if not (0 <= args.max_error_rate <= 1 and args.p95_ms > 0):
        parser.error("Invalid error-rate or latency threshold")

    base = args.url.rstrip("/")
    def sample(index: int) -> tuple[float, bool, int]:
        body = None
        url = base + ("/api/evaluate" if args.flag else "/api/health/ready")
        headers = {}
        if args.flag:
            body = json.dumps({
                "key": args.flag, "environment": args.environment,
                "user_id": f"synthetic-load-{index}", "track": False,
                "country": args.country, "plan": args.plan,
            }).encode()
            headers["Content-Type"] = "application/json"
        if args.token:
            headers["Authorization"] = f"Bearer {args.token}"
        request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
        started = time.perf_counter()
        status = 0
        try:
            with urlopen(request, timeout=12) as response:
                response.read()
                status = response.status
        except HTTPError as exc:
            status = exc.code
        except (URLError, TimeoutError, OSError):
            pass
        return (time.perf_counter() - started) * 1000, 200 <= status < 300, status

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = [f.result() for f in as_completed(pool.submit(sample, index) for index in range(args.requests))]
    elapsed = time.perf_counter() - start
    latency = [x[0] for x in results]
    errors = sum(not x[1] for x in results)
    error_rate = errors / len(results)
    report = {
        "scenario": "flag_evaluation_no_tracking" if args.flag else "readiness",
        "requests": len(results), "concurrency": args.concurrency,
        "duration_seconds": round(elapsed, 3),
        "throughput_rps": round(len(results) / max(elapsed, 0.001), 2),
        "p50_ms": round(statistics.median(latency), 2),
        "p95_ms": round(percentile(latency, 0.95), 2),
        "p99_ms": round(percentile(latency, 0.99), 2),
        "errors": errors, "error_rate": round(error_rate, 4),
        "http_statuses": {str(code): sum(x[2] == code for x in results) for code in sorted({x[2] for x in results})},
    }
    print(json.dumps(report, indent=2))
    passed = error_rate <= args.max_error_rate and report["p95_ms"] <= args.p95_ms
    print("PASS: load thresholds satisfied" if passed else "FAIL: load thresholds exceeded")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
