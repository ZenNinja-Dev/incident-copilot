# Incident Copilot

A 100% local observability stack with an AI incident-triage agent — runs
entirely on your machine, no cloud and no paid APIs.

![Incident triage: inject a fault, the local agent finds the root cause](demo/triage.gif)

## Architecture

Four FastAPI services with cascading dependencies export Prometheus metrics.
A self-driving load generator produces continuous traffic. Prometheus scrapes
the services; Grafana visualises request rate, error ratio and p95 latency.
Runtime chaos injection lets you create real incidents. A local LLM agent then
reads the metrics and triages the incident.

```
loadgen -> checkout -> payments
        -> orders   -> inventory
                 |
           /metrics -> Prometheus -> Grafana
                            |
                     triage agent (Ollama + LangGraph)
```

## Run

    docker compose up -d --build

- Grafana:    http://localhost:3001  (anonymous, local only)
- Prometheus: http://localhost:9090/targets
- Services:   http://localhost:8001..8004

## Inject an incident

    # 50% failures on payments -> checkout errors cascade
    curl -X POST "http://localhost:8002/chaos?failure_rate=0.5"
    # +600ms latency on inventory -> orders p95 climbs
    curl -X POST "http://localhost:8004/chaos?latency_ms=600"
    # reset
    curl -X POST "http://localhost:8002/chaos?failure_rate=0"

## AI triage

A local agent (Ollama + LangGraph) queries live Prometheus metrics through
tools, flags unhealthy services and reasons about the root cause across the
service dependency graph — no cloud, no API keys. Full details in `agent/`.

    uv venv && source .venv/bin/activate
    uv pip install -r agent/requirements.txt
    curl -X POST "http://localhost:8002/chaos?failure_rate=0.5"   # break payments
    python -m agent.triage

Example output during the incident above:

    SUMMARY: Two services are unhealthy with high error ratios and latency.
    AFFECTED: checkout (error_ratio 0.22, p95 0.42s),
              payments (error_ratio 0.20, p95 0.23s).
    ROOT CAUSE: payments — the failing dependency; checkout errors are cascaded.

## Stack

FastAPI · Prometheus · Grafana · Docker Compose · Ollama · LangGraph

Configurable model via `OLLAMA_MODEL` (default `llama3.2`).
