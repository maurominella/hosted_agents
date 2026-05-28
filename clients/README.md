# Clients for Microsoft Foundry Hosted Agents

> **Part of the [Microsoft Foundry Hosted Agents](../README.md) collection.**

This folder contains sample client code that demonstrates how to invoke a **Microsoft Foundry Hosted Agent** from a Python script or an HTTP client.

## Files

| File | Description |
|------|-------------|
| `01 - echo_agent.http` | REST Client (VS Code) calls to the local echo agent |
| `02 - Invoke AgentServer with Response_openaisdk.py` | Invoke an AgentServer endpoint using the OpenAI SDK |
| `03 - Invoke AgentServer with Response_mafsdk.py` | Invoke an AgentServer endpoint using the Microsoft Agent Framework SDK |
| `04 - Invoke HostedAgent_responses.py` | Invoke a Foundry-hosted agent via the Responses protocol |
| `main.py` | Minimal entry point for quick testing |

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
.\.venv\Scripts\Activate.ps1       # Windows PowerShell
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Set the agent endpoint before running the client scripts:

```bash
# Linux / macOS
export AGENT_ENDPOINT="http://localhost:8088"   # local agent
# or
export AGENT_ENDPOINT="https://<foundry-account>.services.ai.azure.com/api/projects/<project>/..."  # hosted agent
```

```powershell
# Windows PowerShell
$env:AGENT_ENDPOINT = "http://localhost:8088"
```

## Running a client script

```bash
python "04 - Invoke HostedAgent_responses.py"
```

> Make sure the target agent is running (locally or deployed in a Microsoft Foundry project) before executing the client.
