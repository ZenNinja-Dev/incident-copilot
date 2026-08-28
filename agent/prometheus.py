"""Prometheus HTTP API client + dependency-aware incident analysis."""
import os

import httpx

PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")
SERVICES = ["checkout", "payments", "orders", "inventory"]

# caller -> callees it depends on (the caller calls each callee)
DEPENDENCIES = {
    "checkout": ["payments"],
    "orders": ["inventory"],
}

ERROR_RATIO_THRESHOLD = 0.05   # 5%
P95_LATENCY_THRESHOLD = 0.5    # seconds (caller services idle ~0.35s waiting on downstreams)


def _query(promql: str):
    r = httpx.get(f"{PROM_URL}/api/v1/query", params={"query": promql}, timeout=10.0)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {data}")
    return data["data"]["result"]


def _by_service(result):
    out = {}
    for item in result:
        svc = item["metric"].get("service", "unknown")
        out[svc] = float(item["value"][1])
    return out


def service_health():
    """Per-service request rate (req/s), error ratio (0-1) and p95 latency (s)."""
    rate = _by_service(_query("sum by (service) (rate(app_requests_total[1m]))"))
    errors = _by_service(
        _query(
            'sum by (service) (rate(app_requests_total{status="500"}[1m])) '
            "/ clamp_min(sum by (service) (rate(app_requests_total[1m])), 0.001)"
        )
    )
    p95 = _by_service(
        _query(
            "histogram_quantile(0.95, sum by (service, le) "
            "(rate(app_request_latency_seconds_bucket[5m])))"
        )
    )
    health = {}
    for svc in SERVICES:
        health[svc] = {
            "request_rate": round(rate.get(svc, 0.0), 3),
            "error_ratio": round(errors.get(svc, 0.0), 4),
            "p95_latency_s": round(p95.get(svc, 0.0), 4),
        }
    return health


def _is_unhealthy(metrics):
    return (
        metrics["error_ratio"] > ERROR_RATIO_THRESHOLD
        or metrics["p95_latency_s"] > P95_LATENCY_THRESHOLD
    )


def analyze():
    """Health snapshot plus dependency-aware root-cause candidates.

    A service is a root-cause candidate when it is unhealthy AND none of its
    dependencies (callees) are unhealthy — i.e. its failure is not explained by
    a failing downstream service. Callers that are unhealthy only because a
    dependency failed are collateral, not the cause.
    """
    health = service_health()
    unhealthy = {svc for svc, m in health.items() if _is_unhealthy(m)}
    candidates = sorted(
        svc for svc in unhealthy
        if not any(dep in unhealthy for dep in DEPENDENCIES.get(svc, []))
    )
    return {
        "health": health,
        "dependencies": DEPENDENCIES,
        "unhealthy": sorted(unhealthy),
        "root_cause_candidates": candidates,
        "thresholds": {
            "error_ratio": ERROR_RATIO_THRESHOLD,
            "p95_latency_s": P95_LATENCY_THRESHOLD,
        },
    }


def raw_query(promql: str):
    """Run an arbitrary instant PromQL query; return a list of {metric, value}."""
    return [
        {"metric": i["metric"], "value": float(i["value"][1])}
        for i in _query(promql)
    ]
