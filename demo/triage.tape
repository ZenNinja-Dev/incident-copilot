# Incident Copilot — triage demo
# Render:  vhs demo/triage.tape   (stack must be up, .venv created)
Output demo/triage.gif

Set Shell "bash"
Set FontSize 14
Set Width 1100
Set Height 620
Set Padding 18
Set TypingSpeed 45ms
Set Framerate 24
Set Theme "Catppuccin Mocha"

# --- hidden setup: neutral prompt, venv, start incident, warm the model ---
Hide
Type "export VIRTUAL_ENV_DISABLE_PROMPT=1" Enter
Type "source .venv/bin/activate" Enter
Type "export OLLAMA_MODEL=qwen2.5:14b" Enter
Type "export PS1='incident-copilot $ '" Enter
Type "clear" Enter
Type "curl -s -X POST 'http://localhost:8002/chaos?failure_rate=0.5' >/dev/null 2>&1" Enter
Sleep 20s
Type "python -m agent.triage >/dev/null 2>&1" Enter
Sleep 50s
Type "clear" Enter
Show

# --- visible demo ---
Type "# 1) inject an incident: 50% failures on payments" Enter
Sleep 1s
Type "curl -s -X POST 'http://localhost:8002/chaos?failure_rate=0.5' | python3 -m json.tool" Enter
Sleep 3s
Type "# 2) run the local AI triage agent (Ollama + LangGraph)" Enter
Sleep 1s
Type "python -m agent.triage" Enter
Sleep 16s
Sleep 3s
Type "# reset" Enter
Type "curl -s -X POST 'http://localhost:8002/chaos?failure_rate=0' >/dev/null" Enter
Sleep 2s
