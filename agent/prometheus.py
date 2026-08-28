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


def _by_label(result, label):
    out = {}
    for item in result:
        out[item["metric"].get(label, "unknown")] = float(item["value"][1])
    return out


def service_health():
    """Per-service request rate (req/s), error ratio (0-1) and p95 latency (s)."""
    rate = _by_label(_query("sum by (service) (rate(app_requests_total[1m]))"), "service")
    errors = _by_label(
        _query(
            'sum by (service) (rate(app_requests_total{status="500"}[1m])) '
            "/ clamp_min(sum by (service) (rate(app_requests_total[1m])), 0.001)"
        ),
        "service",
    )
    p95 = _by_label(
        _query(
            "histogram_quantile(0.95, sum by (service, le) "
            "(rate(app_request_latency_seconds_bucket[5m])))"
        ),
        "service",
    )
    return {
        svc: {
            "request_rate": round(rate.get(svc, 0.0), 3),
            "error_ratio": round(errors.get(svc, 0.0), 4),
            "p95_latency_s": round(p95.get(svc, 0.0), 4),
        }
        for svc in SERVICES
    }


def _is_unhealthy(m):
    return m["error_ratio"] > ERROR_RATIO_THRESHOLD or m["p95_latency_s"] > P95_LATENCY_THRESHOLD


def analyze():
    """Health snapshot, dependency-aware root cause, symptom and severity.

    A service is a root-cause candidate when it is unhealthy AND none of its
    dependencies are — its failure is not explained by a failing downstream.
    Severity: SEV1 (peak error >=25% or >=3 services down), SEV2 (errors present
    or >=2 down), SEV3 (minor, e.g. single latency blip).
    """
    health = service_health()
    unhealthy = {s for s, m in health.items() if _is_unhealthy(m)}
    candidates = sorted(
        s for s in unhealthy
        if not any(dep in unhealthy for dep in DEPENDENCIES.get(s, []))
    )
    symptoms = {
        s: ("errors" if health[s]["error_ratio"] > ERROR_RATIO_THRESHOLD else "latency")
        for s in candidates
    }
    peak_error = max((health[s]["error_ratio"] for s in unhealthy), default=0.0)
    n = len(unhealthy)
    if not unhealthy:
        severity = None
    elif peak_error >= 0.25 or n >= 3:
        severity = "SEV1"
    elif peak_error >= ERROR_RATIO_THRESHOLD or n >= 2:
        severity = "SEV2"
    else:
        severity = "SEV3"
    return {
        "health": health,
        "dependencies": DEPENDENCIES,
        "unhealthy": sorted(unhealthy),
        "root_cause_candidates": candidates,
        "root_cause_symptoms": symptoms,
        "severity": severity,
        "thresholds": {
            "error_ratio": ERROR_RATIO_THRESHOLD,
            "p95_latency_s": P95_LATENCY_THRESHOLD,
        },
    }


def endpoint_breakdown(service):
    """Per-endpoint request rate, error ratio and p95 latency for one service."""
    rate = _by_label(
        _query(f'sum by (endpoint) (rate(app_requests_total{{service="{service}"}}[1m]))'),
        "endpoint",
    )
    errors = _by_label(
        _query(
            f'sum by (endpoint) (rate(app_requests_total{{service="{service}",status="500"}}[1m])) '
            f'/ clamp_min(sum by (endpoint) (rate(app_requests_total{{service="{service}"}}[1m])), 0.001)'
        ),
        "endpoint",
    )
    p95 = _by_label(
        _query(
            f"histogram_quantile(0.95, sum by (endpoint, le) "
            f'(rate(app_request_latency_seconds_bucket{{service="{service}"}}[5m])))'
        ),
        "endpoint",
    )
    eps = sorted(set(rate) | set(errors) | set(p95))
    return {
        ep: {
            "request_rate": round(rate.get(ep, 0.0), 3),
            "error_ratio": round(errors.get(ep, 0.0), 4),
            "p95_latency_s": round(p95.get(ep, 0.0), 4),
        }
        for ep in eps
    }


def whats_changed():
    """Per-service error ratio and p95 now vs 5 minutes ago (incident onset)."""
    def err(offset=""):
        return _by_label(
            _query(
                f'sum by (service) (rate(app_requests_total{{status="500"}}[1m] {offset})) '
                f"/ clamp_min(sum by (service) (rate(app_requests_total[1m] {offset})), 0.001)"
            ),
            "service",
        )

    def p95(offset=""):
        return _by_label(
            _query(
                f"histogram_quantile(0.95, sum by (service, le) "
                f"(rate(app_request_latency_seconds_bucket[5m] {offset})))"
            ),
            "service",
        )

    en, ea = err(), err("offset 5m")
    pn, pa = p95(), p95("offset 5m")
    return {
        svc: {
            "error_ratio_now": round(en.get(svc, 0.0), 4),
            "error_ratio_5m_ago": round(ea.get(svc, 0.0), 4),
            "p95_now_s": round(pn.get(svc, 0.0), 4),
            "p95_5m_ago_s": round(pa.get(svc, 0.0), 4),
        }
        for svc in SERVICES
    }


def raw_query(promql: str):
    """Run an arbitrary instant PromQL query; return a list of {metric, value}."""
    return [
        {"metric": i["metric"], "value": float(i["value"][1])}
        for i in _query(promql)
    ]
