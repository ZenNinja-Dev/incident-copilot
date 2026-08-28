"""Generic multi-endpoint toy service with per-endpoint chaos injection."""
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
# endpoints this service exposes, e.g. "charge,refund"
ENDPOINTS = [e.strip() for e in os.getenv("ENDPOINTS", "work").split(",") if e.strip()]
# downstream URLs (full path) called from this service's primary endpoint,
# e.g. "http://payments:8000/charge"
DOWNSTREAM = [u.strip() for u in os.getenv("DOWNSTREAM", "").split(",") if u.strip()]

# per-endpoint runtime chaos knobs
chaos = {ep: {"failure_rate": 0.0, "latency_ms": 0} for ep in ENDPOINTS}

app = FastAPI(title=SERVICE_NAME)

REQUESTS = Counter(
    "app_requests_total", "Total requests", ["service", "endpoint", "status"]
)
LATENCY = Histogram(
    "app_request_latency_seconds", "Request latency", ["service", "endpoint"]
)
INFLIGHT = Gauge("app_inflight_requests", "In-flight requests", ["service"])


async def _handle(endpoint: str, call_downstream: bool):
    INFLIGHT.labels(SERVICE_NAME).inc()
    start = time.perf_counter()
    status = "200"
    knobs = chaos.get(endpoint, {"failure_rate": 0.0, "latency_ms": 0})
    try:
        await asyncio.sleep(random.uniform(0.02, 0.12) + knobs["latency_ms"] / 1000.0)
        if call_downstream and DOWNSTREAM:
            async with httpx.AsyncClient(timeout=2.0) as client:
                for url in DOWNSTREAM:
                    r = await client.get(url)
                    r.raise_for_status()
        if random.random() < knobs["failure_rate"]:
            status = "500"
            return Response(
                '{"error":"injected failure"}',
                status_code=500,
                media_type="application/json",
            )
        return {"service": SERVICE_NAME, "endpoint": endpoint, "ok": True}
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


def _make_route(endpoint: str, call_downstream: bool):
    async def route():
        return await _handle(endpoint, call_downstream)
    return route


# one GET route per endpoint; the first endpoint is the one that calls downstreams
for i, ep in enumerate(ENDPOINTS):
    app.add_api_route(f"/{ep}", _make_route(ep, i == 0), methods=["GET"])


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "endpoints": ENDPOINTS}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def root():
    return {
        "service": SERVICE_NAME,
        "endpoints": ENDPOINTS,
        "downstream": DOWNSTREAM,
        "chaos": chaos,
    }


@app.post("/chaos")
def set_chaos(
    endpoint: str | None = None,
    failure_rate: float | None = None,
    latency_ms: int | None = None,
):
    """Inject chaos. Without ?endpoint=... it applies to all of the service's
    endpoints; with it, only that one endpoint is affected."""
    targets = [endpoint] if endpoint else list(ENDPOINTS)
    for ep in targets:
        if ep not in chaos:
            continue
        if failure_rate is not None:
            chaos[ep]["failure_rate"] = max(0.0, min(1.0, failure_rate))
        if latency_ms is not None:
            chaos[ep]["latency_ms"] = max(0, latency_ms)
    return chaos
