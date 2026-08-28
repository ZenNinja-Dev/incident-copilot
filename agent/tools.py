"""LangChain tools the agent uses to inspect the running system."""
import json

from langchain_core.tools import tool

from agent import prometheus


@tool
def analyze_incident() -> str:
    """Snapshot all services, flag unhealthy ones, and compute root-cause
    candidates from the dependency graph. A service is a root-cause candidate
    when it is unhealthy but none of its dependencies are — its failure is not
    explained by a failing downstream service. Call this first; the returned
    root_cause_candidates are the authoritative origin of the incident."""
    return json.dumps(prometheus.analyze(), indent=2)


@tool
def get_service_health() -> str:
    """Get raw per-service health only: request rate (req/s), error ratio (0-1)
    and p95 latency (seconds), without root-cause analysis."""
    return json.dumps(prometheus.service_health(), indent=2)


@tool
def run_promql(query: str) -> str:
    """Run an arbitrary instant PromQL query for a deeper look. Available metrics:
    app_requests_total{service,endpoint,status},
    app_request_latency_seconds_bucket{service,le},
    app_inflight_requests{service}."""
    try:
        return json.dumps(prometheus.raw_query(query), indent=2)
    except Exception as e:
        return f"query failed: {e}"
