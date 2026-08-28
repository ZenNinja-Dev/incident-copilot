import asyncio
import os
import random
import time

import httpx
from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

SERVICE_NAME = os.getenv("SERVICE_NAME", "service")
# Comma-separated downstream base URLs, e.g. "http://payments:8000"
DOWNSTREAM = [u.strip() for u in os.getenv("DOWNSTREAM", "").split(",") if u.strip()]

# Runtime-tunable chaos knobs, seeded from env
chaos = {
    "failure_rate": float(os.getenv("FAILURE_RATE", "0.0")),  # 0.0..1.0
    "latency_ms": int(os.getenv("LATENCY_MS", "0")),          # extra latency
}

app = FastAPI(title=SERVICE_NAME)

REQUESTS = Counter(
    "app_requests_total", "Total requests", ["service", "endpoint", "status"]
)
LATENCY = Histogram(
    "app_request_latency_seconds", "Request latency", ["service", "endpoint"]
)
INFLIGHT = Gauge("app_inflight_requests", "In-flight requests", ["service"])


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "downstream": DOWNSTREAM, "chaos": chaos}


@app.get("/work")
async def work():
    endpoint = "/work"
    INFLIGHT.labels(SERVICE_NAME).inc()
    start = time.perf_counter()
    status = "200"
    try:
        # baseline work + injected latency
        await asyncio.sleep(random.uniform(0.02, 0.12) + chaos["latency_ms"] / 1000.0)

        # call downstreams; their failures propagate up (cascading incidents)
        async with httpx.AsyncClient(timeout=2.0) as client:
            for url in DOWNSTREAM:
                r = await client.get(f"{url}/work")
                r.raise_for_status()

        # injected local failures
        if random.random() < chaos["failure_rate"]:
            status = "500"
            return Response(
                '{"error":"injected failure"}',
                status_code=500,
                media_type="application/json",
            )
        return {"service": SERVICE_NAME, "ok": True}
    except Exception:
        status = "500"
        return Response(
            '{"error":"downstream failure"}',
            status_code=500,
            media_type="application/json",
        )
    finally:
        LATENCY.labels(SERVICE_NAME, endpoint).observe(time.perf_counter() - start)
        REQUESTS.labels(SERVICE_NAME, endpoint, status).inc()
        INFLIGHT.labels(SERVICE_NAME).dec()


@app.post("/chaos")
def set_chaos(failure_rate: float | None = None, latency_ms: int | None = None):
    if failure_rate is not None:
        chaos["failure_rate"] = max(0.0, min(1.0, failure_rate))
    if latency_ms is not None:
        chaos["latency_ms"] = max(0, latency_ms)
    return chaos
