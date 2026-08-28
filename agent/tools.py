"""LangChain tools the agent uses to inspect the running system."""
import json

from langchain_core.tools import tool

from agent import prometheus


@tool
def analyze_incident() -> str:
    """Snapshot all services and analyse the incident. Returns per-service health,
    which services are unhealthy, root_cause_candidates (dependency-aware),
    root_cause_symptoms (errors|latency per candidate) and severity (SEV1/2/3).
    A service is a root-cause candidate when it is unhealthy but none of its
    dependencies are. Call this first; its results are authoritative."""
    return json.dumps(prometheus.analyze(), indent=2)


@tool
def endpoint_breakdown(service: str) -> str:
    """Break a service down by endpoint: request rate, error ratio and p95 per
    endpoint. Use on a root-cause service to pinpoint WHICH endpoint is failing."""
    try:
        return json.dumps(prometheus.endpoint_breakdown(service), indent=2)
    except Exception as e:
        return f"query failed: {e}"


@tool
def whats_changed() -> str:
    """Compare each service's error ratio and p95 latency now vs 5 minutes ago,
    to confirm the incident's onset and what degraded."""
    return json.dumps(prometheus.whats_changed(), indent=2)


@tool
def get_service_health() -> str:
    """Raw per-service health only (request rate, error ratio, p95), no analysis."""
    return json.dumps(prometheus.service_health(), indent=2)


@tool
def run_promql(query: str) -> str:
    """Run an arbitrary instant PromQL query for a deeper look. Metrics:
    app_requests_total{service,endpoint,status},
    app_request_latency_seconds_bucket{service,le},
    app_inflight_requests{service}."""
    try:
        return json.dumps(prometheus.raw_query(query), indent=2)
    except Exception as e:
        return f"query failed: {e}"
