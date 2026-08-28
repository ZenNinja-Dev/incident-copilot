# Triage agent

Local SRE incident-triage agent (Ollama + LangGraph). It reads live Prometheus
metrics, flags unhealthy services and reasons about the most likely root cause
using the service dependency graph. No cloud, no API keys.

## Run

From the repo root, with the stack already up (`docker compose up -d`):

    uv venv
    source .venv/bin/activate
    uv pip install -r agent/requirements.txt
    python -m agent.triage

Configure via env (optional):

    OLLAMA_MODEL=qwen2.5:14b python -m agent.triage   # default: llama3.2
    OLLAMA_URL=http://localhost:11434                  # Ollama endpoint
    PROM_URL=http://localhost:9090                     # Prometheus endpoint

## Demo

    # trigger an incident, then run the agent
    curl -X POST "http://localhost:8002/chaos?failure_rate=0.5"
    python -m agent.triage
    # reset
    curl -X POST "http://localhost:8002/chaos?failure_rate=0"
