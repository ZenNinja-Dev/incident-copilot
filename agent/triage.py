"""Local SRE incident-triage agent (Ollama + LangGraph).

Reads live Prometheus metrics and produces a full incident report: severity,
dependency-aware root cause, the failing endpoint, what changed, and a suggested
remediation. Runs 100% locally.
"""
import os

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from agent.tools import (
    analyze_incident,
    endpoint_breakdown,
    get_service_health,
    run_promql,
    whats_changed,
)

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

SYSTEM = """You are an SRE incident-triage agent for a small microservice system.

Dependency graph (caller -> callee; the caller calls the callee):
  checkout -> payments   (checkout calls payments /charge)
  orders   -> inventory  (orders calls inventory /reserve)

Failures propagate UPSTREAM: when a callee (dependency) fails or slows down, its
callers show elevated errors or latency as a side effect. The ROOT CAUSE is the
failing CALLEE, never the caller that merely inherits the failure — even if the
caller's error ratio looks slightly higher.

Process:
1. Call analyze_incident. It returns health, unhealthy services,
   root_cause_candidates, root_cause_symptoms and severity. Trust these.
2. For each root-cause service, call endpoint_breakdown to find WHICH endpoint
   is failing (high error ratio or p95).
3. Call whats_changed once to confirm onset (now vs 5 min ago).
4. Callers unhealthy only because their dependency failed are collateral.

Answer with exactly these sections, in this order:
SEVERITY: the severity from analyze_incident, justified by the peak error ratio
          among affected services or the number of services affected.
SUMMARY: one line, what is wrong.
AFFECTED: unhealthy services with their key numbers.
ROOT CAUSE: the service in root_cause_candidates, the specific failing endpoint,
            and the symptom (errors or latency).
WHAT CHANGED: how the root-cause service's error ratio / p95 shifted vs 5 min ago
            (from whats_changed), showing the incident onset.
REMEDIATION: a concrete next action. For an ERRORS symptom: inspect the failing
            endpoint's recent deploy/config, check its logs, consider rollback
            or restart, and verify its own dependencies. For a LATENCY symptom:
            check the service for resource saturation or a slow dependency and
            consider scaling it or its downstream.
If nothing is unhealthy, reply "System healthy." and stop.
Be concise and factual. Do not contradict analyze_incident."""


def main():
    llm = ChatOllama(model=MODEL, base_url=OLLAMA_URL, temperature=0)
    agent = create_agent(
        llm,
        [analyze_incident, endpoint_breakdown, whats_changed, get_service_health, run_promql],
        system_prompt=SYSTEM,
    )
    print(f"[triage] model={MODEL} prometheus={os.getenv('PROM_URL', 'http://localhost:9090')}\n")
    result = agent.invoke(
        {"messages": [("user", "Run an incident triage on the system right now.")]}
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
