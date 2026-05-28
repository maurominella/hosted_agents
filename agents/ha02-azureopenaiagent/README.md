# ha02-azureopenaiagent — Microsoft Foundry Hosted Agent (Azure OpenAI Hotel Agent)

> **Part of the [Microsoft Foundry Hosted Agents](../../README.md) collection.**
> See the top-level README for prerequisites, local-run instructions, containerization, ACR push, and deployment steps.

> **IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).
>
> Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.
>
> Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.
>
> Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.

## What this sample demonstrates

This sample demonstrates a **key advantage of code-based hosted agents**:

- **Local Python tool execution** - Run custom Python functions as agent tools

Code-based agents can execute **any Python code** you write. This sample includes a Seattle Hotel Agent with a `get_available_hotels` tool that searches for available hotels based on check-in/check-out dates and budget preferences.

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/) and can be deployed to Microsoft Foundry.

## How It Works

### Local Tools Integration

In [main.py](main.py), the agent uses a local Python function (`get_available_hotels`) that simulates a hotel availability API. This demonstrates how code-based agents can execute custom server-side logic that prompt agents cannot access.

The tool accepts:

- **check_in_date** - Check-in date in YYYY-MM-DD format
- **check_out_date** - Check-out date in YYYY-MM-DD format
- **max_price** - Maximum price per night in USD (optional, defaults to $500)

### Agent Hosting

The agent is hosted using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/),
which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

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

## Running the Agent Locally

### Prerequisites

Before running this sample, ensure you have:

1. **Microsoft Foundry Project**
   - A Microsoft Project created.
   - Chat model deployed (e.g., `gpt-4o` or `gpt-4.1`).
   - Note your project endpoint URL and model deployment name.

2. **Azure CLI**
   - Installed and authenticated
   - Run `az login` and verify with `az account show`

3. **Python 3.10 or higher**
   - Verify your version: `python --version`
   - If you have Python 3.9 or older, install a newer version:
     - Windows: `winget install Python.Python.3.12`
     - macOS: `brew install python@3.12`
     - Linux: Use your package manager

### Environment Variables

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

### Setting Up a Virtual Environment

It's recommended to use a virtual environment to isolate project dependencies:

**macOS/Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Installing Dependencies

Install the required Python dependencies using pip:

```bash
pip install -r requirements.txt
```

The required packages are:

- `azure-ai-agentserver-agentframework` - Agent Framework and AgentServer SDK

### Running the Sample

#### Option 1: Press F5 (Recommended)

Press **F5** in VS Code to start debugging. Alternatively, you can use the VS Code debug menu:

1. Open the **Run and Debug** view (Ctrl+Shift+D / Cmd+Shift+D)
2. Select **"Debug Local Workflow HTTP Server"** from the dropdown
3. Click the green **Start Debugging** button (or press F5)

This will:

1. Start the HTTP server with debugging enabled
2. Open the AI Toolkit Agent Inspector for interactive testing
3. Allow you to set breakpoints and inspect the workflow

#### Option 2: Run in Terminal

Run as HTTP server (default):

```bash
python main.py
```

This will start the hosted agent locally on `http://localhost:8088/`.

**PowerShell (Windows):**

```powershell
$body = @{
   input = "I need a hotel in Seattle from 2025-03-15 to 2025-03-18, budget under `$200 per night"
    stream = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8088/responses -Method Post -Body $body -ContentType "application/json"
```

**Bash/curl (Linux/macOS):**

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
   -d '{"input": "Find me hotels in Seattle for March 20-23, 2025 under $200 per night","stream":false}'
```

The agent will use the `get_available_hotels` tool to search for available hotels matching your criteria.


## Local Container Build & Test
The .dockerignore intentionally excludes .env from the build context (so it never reaches Docker). This is correct security behaviour: you should never bake secrets into an image.
So, don't use .env from the COPY instruction, but pass the .env at runtime instead:
```bash
# Build the image
docker build -t ha02-azureopenaitagent .

# Run the container (mapping host port 8090 → container port 8088)
docker run -p 8090:8088 --env-file .env ha02-azureopenaitagent

# or
docker run -p 8090:8088 \
  -e AZURE_TENANT_ID=<your-tenant-id> \
  -e AZURE_CLIENT_ID=<your-client-id> \
  -e AZURE_CLIENT_SECRET=<your-client-secret> \
  --env-file .env \
  ha02-azureopenaitagent:latest

# or, since they're already defined in your .env file, pass them without values to inherit from the current shell environment:
docker run -p 8090:8088 \
  -e AZURE_TENANT_ID \
  -e AZURE_CLIENT_ID \
  -e AZURE_CLIENT_SECRET \
  --env-file .env \
  ha02-azureopenaitagent:latest


# such variables might be defined in our shell's startup file.
# For bash, append to ~/.bashrc (interactive shells) or ~/.bash_profile (login shells):
echo 'export AZURE_TENANT_ID=3ad***' >> ~/.bashrc
echo 'export AZURE_CLIENT_ID=31***' >> ~/.bashrc
echo 'export AZURE_CLIENT_SECRET=F5***' >> ~/.bashrc
source ~/.bashrc
```

## Deploying the Agent to Microsoft Foundry

To deploy the hosted agent:

1. Open the VS Code Command Palette and run the `Microsoft Foundry: Deploy Hosted Agent` command.

2. Follow the interactive deployment prompts. The extension will help you select or create the container files it needs:
   - It first looks for a Dockerfile at the repository root. If not found, you can select an existing Dockerfile or generate a new one.
   - If you choose to generate a Dockerfile, the extension will place the files at the repo root and open the Dockerfile in the editor; the deployment flow is intentionally cancelled in that case so you can review and edit the generated files before re-running the deploy command.

3. After deployment completes, the hosted agent appears under the `Hosted Agents (Preview)` section of the extension tree. You can select the agent there to view details and test it using the integrated playground.

**What the deploy flow does for you:**

- Creates or obtains an Azure Container Registry for the target project.
- Builds and pushes a container image from your workspace (the build packages the workspace respecting `.dockerignore`).
- Creates an agent version in Microsoft Foundry using the built image. If a `.env` file exists at the workspace root, the extension will parse it and include its key/value pairs as the hosted agent's environment variables in the create request (these variables will be available to the agent runtime).
- Starts the agent container on the project's capability host. If the capability host is not provisioned, the extension will prompt you to enable it and will guide you through creating it.

### MSI Configuration in the Azure Portal

This sample requires the Microsoft Foundry Project to authenticate using a Managed Identity when running remotely in Azure. Grant the project's managed identity the required permissions by assigning the built-in [Azure AI User](https://aka.ms/foundry-ext-project-role) role.

To configure the Managed Identity:

1. In the Azure Portal, open the Foundry Project.
2. Select "Access control (IAM)" from the left-hand menu.
3. Click "Add" and choose "Add role assignment".
4. In the role selection, search for and select "Azure AI User", then click "Next".
5. For "Assign access to", choose "Managed identity".
6. Click "Select members", locate the managed identity associated with your Foundry Project (you can search by the project name), then click "Select".
7. Click "Review + assign" to complete the assignment.
8. Allow a few minutes for the role assignment to propagate before running the application.

## Additional Resources

- [Microsoft Agents Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)
- [Managed Identities for Azure Resources](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/)
