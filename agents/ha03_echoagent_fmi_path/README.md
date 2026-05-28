# ha03_echoagent_fmi_path — Microsoft Foundry Hosted Agent (Echo Agent)

> **Part of the [Microsoft Foundry Hosted Agents](../../README.md) collection.**
> See the top-level README for prerequisites, local-run instructions, containerization, ACR push, and deployment steps.

This is the simplest hosted-agent sample. It echoes back the user's input without calling any LLM, making it ideal for testing the **Microsoft Agent Framework** hosting infrastructure end-to-end.

## Quick Start

### UV Installation
- On Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- On Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

### Setup Steps
```bash
# 1. **MKDIR** the new folder and and **CD** into it

# 2 Create the environment
uv init . --python 3.13

# 3. Create the local virtual environment
uv venv

# 4. Activate the environment:
source .venv/bin/activate # on Linux/macOS
.\.venv\Scripts\activate.ps1 # on Windows

# 5. Add libraries (it's KEY to use `--active`):
uv add --active $(cat requirements.txt) --prerelease=allow # Automatically
uv add --active <package-name> --prerelease=allow # Manually

# 6. Check that the packges are installed
uv pip list

# 7. Synchronize to create the file structure (not needed in normal situations, just with pre-existing pyproject.toml
uv sync --active --prerelease=allow

# 8. List jupyter kernels
jupyter kernelspec list

# 9. Delete a jupyter kernel
jupyter kernelspec uninstall responses

# 10. Create kernel for the jupyter notebook
python -m ipykernel install --name responses --use

# 11. To deactivate
deactivate
```

**Test it:**
```bash
curl -sS -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello!", "stream": false}'
```

```python
python - << 'EOF'
import agent_framework
print("OK:", agent_framework)
EOF
```

## Local Container Build & Test

```bash
# Build the image
docker build -t ha03_echoagent_fmi_path .

# Run the container (mapping host port 8089 → container port 8088)
docker run --rm -p 8089:8088 --env-file .env ha03_echoagent_fmi_path
```

> To push the image to ACR and deploy to a Foundry project, see
> [Build, Push & Deploy](../../README.md#push-to-azure-container-registry-acr) in the top-level README,
> or use the helper scripts in [`../../scripts/`](../../scripts/).

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

| Variable | Required | Description |
|----------|----------|-------------|
| `PROJECT_ENDPOINT` | No | Microsoft Foundry project endpoint URL |
| `MODEL_DEPLOYMENT_NAME` | No | Chat model deployment name (e.g. `gpt-4o`) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Enable distributed tracing via Application Insights |
| `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` | No | Set to `true` to enable GenAI tracing |
| `ENABLE_SENSITIVE_DATA` | No | Set to `true` to enable sensitive tracing, like conversations |

, orr set them via PowerShell:

```powershell
# Replace with your actual values
$env:PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
$env:MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
$env:AZURE_TENANT_ID=""
$env:AZURE_CLIENT_ID=""
$env:AZURE_CLIENT_SECRET=""
```


> **Never commit `.env`** — it is listed in `.gitignore`.

## Files

| File | Description |
|------|-------------|
| `main.py` | Agent entry point; starts the HTTP server on port 8088 |
| `Dockerfile` | Container image definition |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `agent.yaml` | Microsoft Foundry agent manifest |

# Logging
Logging is activated with the following lines of code:
```python
# Configure logging - INFO for this module only, WARNING for everything else
logging.basicConfig(level=logging.WARNING) # this is the "father" logger, set to WARNING to avoid too much noise from other modules
logger = logging.getLogger(__name__) # this is the "child" logger for our module (this module)
logger.setLevel(logging.INFO) # we set the child logger to INFO to get more detailed logs from our module
if not logger.handlers: # avoid adding multiple handlers if this code is reloaded multiple times (e.g. during development)
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    logger.addHandler(_handler)
    # propagate=True (default) so logs also reach the root logger,
    # where configure_azure_monitor() attaches the App Insights handler
```

Given the following line:<br/>
![alt text](./_README%20images/image-1.png)

, while here is the output in ***Foundry --> Traces --> Log stream***: <br/>
![alt text](./_README%20images/image-2.png)

, while this is the *much more detailed* trace sent to ***Application Insights***:<br/>
![alt text](./_README%20images/image-3.png)
![alt text](./_README%20images/image-4.png)

## How Logging is implemente in EchoAgent

EchoAgent uses the **standard Python `logging` module as the API** and optionally **OpenTelemetry (via Azure Monitor) as a backend**. Both coexist transparently.

### Logger hierarchy

Python `logging` is organized as a tree. The setup creates two nodes:

```
root logger  (level: WARNING)   ← set by logging.basicConfig()
    └── __main__  (level: INFO) ← set by logging.getLogger(__name__)
```

Setting the root logger to `WARNING` silences third-party libraries (e.g. `httpx`, `azure.core`) that emit many low-level `INFO` messages. Setting the child logger to `INFO` ensures that log statements in `main.py` are visible.

### Why a StreamHandler is added explicitly

Without an explicit handler on the child logger, this would happen:

1. `logger.info("...")` is accepted by the child logger (level `INFO` ✓).
2. With `propagate=True` (the default), the record travels up to the root logger.
3. The root logger's handler has level `WARNING` → **it drops the `INFO` record**.

Adding a `StreamHandler` directly on the child logger ensures that `INFO` messages from this module are always written to **stderr** (visible in the container / Foundry log stream), regardless of the root logger's level.

The `if not logger.handlers:` guard prevents duplicate handlers if the module is reloaded (e.g. in a hot-reload dev workflow).

### How OpenTelemetry fits in

```python
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor()
```

`configure_azure_monitor()` performs **auto-instrumentation**: it silently attaches an additional handler to the **root logger**. You never call it on individual loggers. The full flow for a single `logger.info(...)` call is:

```
logger.info("run() called...")
    │
    ├─► StreamHandler  (on child logger)  →  stderr  ← always active
    │
    └─► propagate to root logger
            ├─► basicConfig StreamHandler  [dropped: level WARNING]
            └─► Azure Monitor Handler      [forwarded to App Insights via OpenTelemetry]
```

### What actually reaches Application Insights

| Source | Level | Reaches App Insights? |
|---|---|---|
| Third-party libraries | `INFO` | ❌ filtered at their own logger (inherits `WARNING` from root) |
| Third-party libraries | `WARNING`+ | ✅ propagated to root → Azure Monitor handler |
| `main.py` (`__main__`) | `INFO`+ | ✅ propagated to root → Azure Monitor handler |

`configure_azure_monitor()` is only called when the `APPLICATIONINSIGHTS_CONNECTION_STRING` environment variable is present, which is automatically injected by Foundry when Application Insights is connected to the agent. In local development the variable is absent, so only the `StreamHandler` (stderr) is active.

---

### Activating Application Insights locally and in Docker

#### 1 — Get the connection string

In the Azure Portal, open your Application Insights resource → **Overview** → copy the **Connection string** (format: `InstrumentationKey=...;IngestionEndpoint=...`).

#### 2 — Set it in your OS (permanent, local development)

**Linux / macOS** — add to `~/.bashrc` or `~/.zshrc`:
```bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=xxxx;IngestionEndpoint=https://..."
```
Then reload: `source ~/.bashrc`

**Windows** — from an elevated PowerShell:
```powershell
[System.Environment]::SetEnvironmentVariable(
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "InstrumentationKey=xxxx;IngestionEndpoint=https://...",
    "User"   # or "Machine" for system-wide
)
```

#### 3 — Pass it to the Docker container

**Option A — pass at `docker run` time** (good for testing, value stays out of the image):
```bash
docker run -p 8089:8088 \
  -e APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=xxxx;IngestionEndpoint=https://..." \
  echoagent
```

**Option B — use a `.env` file** (recommended for local docker-compose workflows, add `.env` to `.gitignore`):
```
# .env  (never commit this file)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxxx;IngestionEndpoint=https://...
```
```bash
docker run -p 8089:8088 --env-file .env echoagent
```

> **Never bake the connection string into the `Dockerfile`** with `ENV` — it would be embedded in the image layers and potentially leaked.

#### 4 — Do you need `load_dotenv()` in the Python code?

**No.** `os.environ.get(...)` reads environment variables that the OS or container runtime has already injected into the process. `load_dotenv()` (from the `python-dotenv` library) is only needed when you store variables in a `.env` file and want Python itself to load them — it is a convenience for local development scripts, not for production containers.

The recommended pattern for this project:

| Scenario | How to set the variable | `load_dotenv()` needed? |
|---|---|---|
| Local dev (bare Python) | Export in shell / OS settings | No |
| Local dev (want a `.env` file) | Add `load_dotenv()` at top of `main.py` | Yes |
| Docker (local) | `--env-file .env` or `-e` flag | No |
| Foundry (production) | Injected automatically by Foundry | No |
