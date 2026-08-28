"""Local SRE incident-triage agent (Ollama + LangGraph).

Reads live Prometheus metrics, detects unhealthy services and identifies the
root cause using dependency-aware analysis. Runs 100% locally.
"""
import os

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from agent.tools import analyze_incident, get_service_health, run_promql

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

SYSTEM = """You are an SRE incident-triage agent for a small microservice system.

Dependency graph (caller -> callee; the caller depends on / calls the callee):
  checkout -> payments
  orders   -> inventory

Failures propagate UPSTREAM: when a callee (dependency) fails or slows down, its
callers show elevated errors or latency as a side effect. The ROOT CAUSE is the
failing CALLEE, never the caller that merely inherits the failure — even if the
caller's error ratio looks slightly higher.

Process:
1. Call analyze_incident. It returns per-service health, which services are
   unhealthy, and root_cause_candidates computed from the dependency graph.
2. Treat root_cause_candidates as the authoritative origin. Unhealthy callers
   that are NOT in that list are collateral damage, not the cause.
3. Use run_promql only if you need extra detail.

Answer with exactly these sections:
SUMMARY: one line describing what is wrong.
AFFECTED: unhealthy services with their key numbers.
ROOT CAUSE: the service(s) in root_cause_candidates and why — name the failing
            dependency and which callers are cascading from it.
If nothing is unhealthy, say the system is healthy in one line and stop.
Be concise and factual. Do not contradict root_cause_candidates."""


def main():
    llm = ChatOllama(model=MODEL, base_url=OLLAMA_URL, temperature=0)
    agent = create_agent(
        llm, [analyze_incident, get_service_health, run_promql], system_prompt=SYSTEM
    )
    print(f"[triage] model={MODEL} prometheus={os.getenv('PROM_URL', 'http://localhost:9090')}\n")
    result = agent.invoke(
        {"messages": [("user", "Run an incident triage on the system right now.")]}
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
