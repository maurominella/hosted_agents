# Microsoft Foundry Hosted Agents — Building, Testing, and Deploying an Agent End‑to‑End

> A complete, hands‑on walkthrough for building a **Foundry Hosted Agent** in Python, running and debugging it locally, securing its secrets with **Azure Key Vault + Managed Identity**, isolating its telemetry in **Application Insights**, upgrading it to the **Microsoft Agent Framework (MAF)**, wiring a **Microsoft Graph** tool through **On‑Behalf‑Of (OBO)**, and finally deploying and invoking it into a **Microsoft Foundry** project with the **Azure Developer CLI (`azd`)**.
>
> This guide is based on a real, working end‑to‑end setup: the agent (`hello-world-python-responses`) is created, tested locally, deployed into a Foundry project, and invoked — the full round trip.

---

## Table of Contents

- [Introduction](#introduction)
- [Final Result](#final-result)
- [1. Clarifying the Terminology](#1-clarifying-the-terminology)
- [2. Choosing the Right Sample (Host, Not Framework)](#2-choosing-the-right-sample-host-not-framework)
- [3. Which Agent Server Samples Exist](#3-which-agent-server-samples-exist)
- [4. Schema Change — July 6, 2026 (`0.1.0-preview` → `1.0.0-beta.4`)](#4-schema-change--july-6-2026-010-preview--100-beta4)
- [5. Setting Up the Agent Locally](#5-setting-up-the-agent-locally)
- [6. Storing Secrets: Key Vault and Managed Identity](#6-storing-secrets-key-vault-and-managed-identity)
- [7. Customizing the Sample: monitoring.py and the Handler](#7-customizing-the-sample-monitoringpy-and-the-handler)
- [8. First Local Test of the Hosted Agent](#8-first-local-test-of-the-hosted-agent)
- [9. Adding a Dockerfile (Optional)](#9-adding-a-dockerfile-optional)
- [10. From "Responses" to "Responses + Agent Framework (MAF)"](#10-from-responses-to-responses--agent-framework-maf)
- [11. Observability: Isolating Telemetry in Application Insights](#11-observability-isolating-telemetry-in-application-insights)
- [12. Real vs. Simulated Streaming](#12-real-vs-simulated-streaming)
- [13. Adding a Tool to the MAF Agent (Graph + OBO)](#13-adding-a-tool-to-the-maf-agent-graph--obo)
- [14. Installing AZD Extensions](#14-installing-azd-extensions)
- [15. Agent Provisioning and Deployment](#15-agent-provisioning-and-deployment)

---

## Introduction

A **Foundry Hosted Agent** is an agent whose code runs as a container on the **Microsoft Foundry** hosting infrastructure. You write ordinary Python, the platform turns it into an HTTP service that speaks Foundry's container protocol, and Foundry hosts, scales, and exposes it through a standard endpoint (Playground, Teams, or a raw API).

This document builds one such agent from the ground up, with a very specific requirement in mind: the agent must be able to **read the custom `x-client-*` request headers**, because that is how we securely pass a **user assertion token** into the agent so it can later call downstream APIs (such as Microsoft Graph) **On‑Behalf‑Of (OBO)** the signed‑in user.

That single requirement drives most of the early design decisions — in particular, **which hosting library** we choose. From there the guide follows the natural lifecycle:

1. Understand the three moving parts (Agent Service, Agent Framework, and the `azure-ai-agentserver-*` libraries).
2. Pick the right starter sample and scaffold it locally.
3. **Secure the secrets** with Key Vault + Managed Identity, and understand the agent's own identity (Microsoft Entra Agent ID).
4. Customize `monitoring.py` and the handler, then run and debug locally.
5. Upgrade it from raw *Responses* handling to the **Microsoft Agent Framework**, and make its telemetry isolable in **Application Insights**.
6. Add a **Graph tool** that uses the propagated user token via OBO.
7. **Provision, deploy, and invoke** it in a Foundry project with `azd`.

Every step below corresponds to something that was actually executed, with the relevant screenshots included.

---

## Final Result

This is the end state we reach by the end of this analysis — the "full round trip" works:

✅ **We can create the agent** from the *Hello World (Responses, bring‑your‑own)* sample, using the `azure-ai-agentserver-responses` host so that the custom `x-client-*` headers (and therefore the user assertion token) are accessible to our code.

✅ **We keep secrets out of `.env` and in Key Vault.** The OBO client secret lives in **Azure Key Vault**; locally the agent reads it with the developer's `az login` identity, and in the Foundry container it reads it with its own **Agent Identity (Microsoft Entra Agent ID)**, which is granted the **Key Vault Secrets User** role.

✅ **We can run, debug, and observe it.** The agent starts on `http://0.0.0.0:8088`, answers real prompts, exposes the `x-client-user-token` header to the handler, and stamps its telemetry with a dedicated `cloud_RoleName` and a `log_source="app"` custom dimension so it can be isolated in a shared Application Insights resource.

✅ **We upgrade it to the Microsoft Agent Framework (MAF)** without losing the `-responses` host, and add a **Microsoft Graph tool** (`onedrive_root_folders_async`) that reads the propagated user assertion from a per‑request `ContextVar` and performs the OBO token exchange (via MSAL, with the client secret pulled from Key Vault) to call Graph as the user.

✅ **We deploy and invoke it.** With `azd deploy` (code deploy) the agent is published as an immutable version into the Foundry project; invoking it with a Foundry auth token **plus** the user‑delegated token produces the real end‑to‑end result — the agent answering a question about the user's own OneDrive via OBO:

![The final end-to-end result in VS Code: main.py (left) with the handler that reads x-client-user-token, sets the per-request ContextVar, and runs the MAF agent with the OneDrive tool; on the right, the HTTP 200 Response from invoking the deployed hosted agent on Foundry.](images/18-final-invocation-result.png)

The rest of this document explains **how** we get there, chapter by chapter.

---

## 1. Clarifying the Terminology

Before anything else, we need to separate three concepts that are easy to confuse.

| Concept | What it is |
|---|---|
| **Foundry Agent Service** | The **hosting platform**. Our agents run as **containers** on the Foundry infrastructure. |
| **Microsoft Agent Framework (MAF)** | An **authoring library** for writing agents (`ChatAgent`, workflows, orchestration). It is a **programming model — optional**. |
| **`azure-ai-agentserver-*`** | The **hosting / protocol libraries**. They turn our code into an HTTP server that speaks Foundry's container protocol (gateway ↔ container). |

### Two hosting libraries, one important difference

Microsoft ships **two** Python libraries for building a Foundry Hosted Agent:

- `azure-ai-agentserver-agentframework`
- `azure-ai-agentserver-responses`

The critical difference for **our** scenario is header access:

| | `azure-ai-agentserver-agentframework` | `azure-ai-agentserver-responses` |
|---|---|---|
| **Authoring model** | Microsoft Agent Framework | Bring‑your‑own (you write the handler) |
| **Reads `x-client-*`?** | ❌ No — the adapter did not expose them | ✅ Yes — via `context.client_headers` |
| **Protocol** | Responses / Invocations (via adapter) | Responses (direct) |

Because `azure-ai-agentserver-agentframework` does **not** expose the custom `x-client-*` headers — which we need in order to securely pass the assertion token — **we will use `azure-ai-agentserver-responses`.**

> **Key relationship:** *Agent Service is always present*; *Agent Framework* is present **only** with `azure-ai-agentserver-agentframework`, **not** with `azure-ai-agentserver-responses`.

### Breaking down the `azure-ai-agentserver-*` family

- **`-core`** — shared foundations (ASGI host, `PlatformHeaders`, the `x-client-*` passthrough, …).
- **`-responses`** — hosts the **Responses** protocol; **you** write `@app.response_handler`. This is the *bring‑your‑own* option.
- **`-invocations`** — hosts the **Invocations** protocol (arbitrary JSON).
- **`-agentframework`** — an **adapter** that hosts an agent written with the Microsoft Agent Framework (`from_agent_framework`), without making you write the protocol handler.

You can see this in the sample list too: *"Basic agent (Responses, Agent Framework)"* vs. *"Hello World (Responses, without a framework)"* → **same** Responses protocol, but the first uses Agent Framework and the second does not.

[↑ Back to top](#table-of-contents)

---

## 2. Choosing the Right Sample (Host, Not Framework)

**Question:** Do we start from the *Hello World agent (Responses, without a framework, Python)*, or from a sample based on the Agent Framework?

**Answer: choose the sample for its *host*, not its *framework*. The framework is additive; the host is not.**

- If we need a hosting library that exposes `x-client-*` → **`azure-ai-agentserver-responses`**.
- So we start from a template that is **`agentserver-responses`‑compatible** — like *Hello World agent (Responses, without a framework, Python)* — and then we add the Agent Framework (or LangGraph, or nothing) **by hand**.

The alternative — picking a sample that integrates `azure-ai-agentserver-agentframework` and then switching it to `azure-ai-agentserver-responses` — would force us to **rip out the hosting mechanism** (exactly the part that hides the headers) and rebuild it, which is the most delicate piece.

> A framework (MAF, LangGraph, …) is **additive**: we import it as a library inside `@app.response_handler`. So we don't choose the sample by framework, we choose it by **host**.

Later — in theory even in parallel — once the agent is ready, we can choose a starter kit for the **infrastructure** part, such as `azd-ai-starter-basic`, which is framework‑agnostic.

[↑ Back to top](#table-of-contents)

---

## 3. Which Agent Server Samples Exist

Regardless of whether we ultimately use MAF, we first list the available samples and find one based on `azure-ai-agentserver-responses`:

```bash
azd ai agent sample list --language python --output json
```

As of **July 8, 2026**, there are **18** samples. From this list we can see the sample **Hello World agent (Responses, without a framework, Python)**, described as:

> *"Minimal Hello World agent using the Responses protocol with a bring‑your‑own approach. Calls a Foundry model via the Responses API and returns the response."*

![The JSON output of `azd ai agent sample list`. Item 12 is the "Hello World agent (Responses, without a framework, Python)"; the highlighted description reads "Calls a Foundry model via the Responses API and returns the response." The manifest URL and init command point at the bring-your-own/responses/hello-world sample.](images/01-agent-sample-list.png)

It is perfect because:

- **Responses protocol + no framework** → it uses `azure-ai-agentserver-responses` (so it reads the `x-client-*` headers).
- It is **minimal** (unlike the *background* / *notetaking* / *toolbox* samples).
- It **already calls an LLM** → which is exactly our goal: "hook up an LLM without worrying about OBO yet."

### Two decisions to make before running `init`

1. **Where it scaffolds.** `azd ai agent init` creates an `azure.yaml` + `src/<agent-name>/…` structure (not the simple `agents/ha01_echoagent` layout). We decide the init folder.
2. **Which model.** The sample calls the model through the **Foundry project** (project endpoint + deployment, using the agent's managed identity). We can either **(a)** keep the sample's approach (model via the Foundry project), or **(b)** repoint it to a specific Azure OpenAI resource. In this guide we keep the Foundry‑project approach with the `gpt-5.4-mini` deployment.

[↑ Back to top](#table-of-contents)

---

## 4. Schema Change — July 6, 2026 (`0.1.0-preview` → `1.0.0-beta.4`)

During the development of this hosted agent, the **Azure Developer CLI (`azd`) + Foundry agents extension** changed its configuration model. This is **not** a simple update: it is a **major‑version** jump, from **`0.1.0-preview`** to **`1.0.0-beta.4`** (still in beta), with a restructuring of the definition files.

### Before — dedicated agent schema (extension `azure.ai.agents` `0.x`)

The definition was split across two files, each with its own schema:

| File | Schema | Role |
|---|---|---|
| `agent.manifest.yaml` | `AgentManifest.yaml` | Agent manifest/template (name, parameters, resources) |
| `agent.yaml` | `ContainerAgent.yaml` | Container runtime (kind, protocols, resources, env vars) |

The init command pointed at the dedicated manifest:

```bash
azd ai agent init -m agent.manifest.yaml
```

### After — native `azd` schema (extension `azure.ai.agents` `>=1.0.0-beta.4`)

Everything is consolidated into a **single `azure.yaml`**, which uses the **native `azd` schema** (`azure.yaml.json`) — the same as any `azd` project. The agent becomes a normal **service**, and so does the model:

```yaml
# azure.yaml (new format)
name: <project-name>
services:
  ai-project:                 # the Foundry project + the model deployment
    host: azure.ai.project
    deployments: [ ... ]
  <agent-name>:               # the hosted agent
    host: azure.ai.agent
    codeConfiguration: { ... }
    environmentVariables: [ ... ]
infra:
  provider: microsoft.foundry # (or bicep)
```

The init command now points at this file:

```bash
azd ai agent init -m azure.yaml
```

### What changes, in short

| | Before (`0.x`) | After (`1.x` beta) |
|---|---|---|
| **Definition files** | `agent.manifest.yaml` + `agent.yaml` | a single `azure.yaml` |
| **Schema** | dedicated agent schemas | native `azd` schema |
| **Agent** | standalone manifest | `service host: azure.ai.agent` |
| **Model** | resource inside the manifest | `service host: azure.ai.project` |
| **Infrastructure** | implicit | `infra` section (`microsoft.foundry` or `bicep`) |
| **`azd` extension** | `azure.ai.agents 0.x` | `azure.ai.agents >=1.0.0-beta.4` |

**Why it matters.** The new format aligns hosted agents with standard `azd` conventions: a single manifest, the same lifecycle commands (`azd provision`, `azd deploy`), and the same service structure used by any `azd` app. The result is **fewer files, more consistency, and portability** — at the price of still being on a **major beta** (`1.0.0-beta.x`), where names and details can still change.

[↑ Back to top](#table-of-contents)

---

## 5. Setting Up the Agent Locally

### 5.1 Clone the sample

Among all the Foundry samples, the one we want is **Hello World agent (Responses, without a framework, Python)**.

> **Note:** the target project must contain the `gpt-5.4-mini` deployment.

Inside `requirements.txt`, remove what **uv** does not like — **every empty line** and **the comment line** — then add the libraries listed at the bottom (pinned versions, `agent-framework` split into `-core` and `-foundry`, plus `azure-keyvault-secrets`):

```text
python-dotenv==1.2.2
azure-monitor-opentelemetry==1.8.9
agent-framework-core==1.10.0
agent-framework-foundry==1.0.1
azure-keyvault-secrets==4.11.0
```

Clone the sample into a fresh destination folder and open it in VS Code:

```bash
folder_name=hello-world-responses01

# 1. delete the destination folder if it exists
rm -rf "./$folder_name"
# 2. delete any previous clone
rm -rf foundry-samples
# 3. clone the repo
git clone --depth 1 https://github.com/microsoft-foundry/foundry-samples.git
# 4. create the destination folder
mkdir -p "./$folder_name"
# 5. copy the hello-world folder into the destination
cp -r foundry-samples/samples/python/hosted-agents/bring-your-own/responses/hello-world/* \
  "./$folder_name/"
# 6. go into the folder
cd "./$folder_name"
# 7. open VS Code
code .
```

![VS Code opened on the cloned project HELLO-WORLD-RESPONSES (WSL: Ubuntu). The Explorer shows src/hello-world-python-responses with .azdignore, .dockerignore, .env.example, Dockerfile, main.py, requirements.txt; requirements.txt is open with lines 6–8 highlighted — azure-monitor-opentelemetry==1.8.9, agent-framework-core==1.10.0, agent-framework-foundry==1.0.1.](images/02-cloned-project-requirements.png)

### 5.2 Create the environment and verify the imports

Create the local virtual environment with **uv**, install the dependencies, and test that all the key imports resolve:

```bash
cd ./src/hello-world-python-responses    # + code . --reuse-window
uv init . --python 3.13
uv venv
source .venv/bin/activate
uv add --active $(cat requirements.txt) --prerelease=allow

uv run python -c "
from azure.ai.agentserver.responses import ResponsesAgentServerHost, CreateResponse, ResponseContext, TextResponse
from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
print('ALL IMPORTS OK')
"
```

Expected output (the experimental warnings are normal):

```text
Resolving despite existing lockfile due to change in pre-release mode: `allow` vs. `if-necessary-or-explicit`
.../agent_framework/_skills.py:122: ExperimentalWarning: [SKILLS] SkillResource is experimental and may change or be removed in future versions without notice.
.../agent_framework/_harness/_file_access.py:602: ExperimentalWarning: [HARNESS] AgentFileStore is experimental and may change or be removed in future versions without notice.
ALL IMPORTS OK
```

If you see **`ALL IMPORTS OK`**, the configuration is in place. The uv‑generated `pyproject.toml` captures the resolved dependency set:

![The uv-generated pyproject.toml for hello-world-python-responses, version 0.1.0, requires-python ">=3.13", with dependencies: agent-framework-core==1.10.0, agent-framework-foundry==1.0.1, azure-ai-agentserver-responses==1.0.0b8, azure-ai-projects==2.0.1, azure-identity==1.25.3, azure-monitor-opentelemetry==1.8.9, debugpy>=1.8.21, python-dotenv==1.2.2.](images/03-pyproject-dependencies.png)

### 5.3 Variables for running the agent (the `.env` file)

We add a `.env` file in the agent root, with the variables needed **while the agent runs locally**. The idea is to keep **no real secrets** in this file — only "durable" strings such as the `client_id` and the **name** of the secret (`APP-OBO-CLIENT-SECRET`), which is stored in the Key Vault at `KEY_VAULT_URL` under the key `APP_OBO_CLIENT_SECRET_NAME`.

This `.env` holds **11 variables**. As we will see in [Chapter 15 — container environment variables](#152-container-environment-variables), the hosted agent on Foundry needs **two fewer** — `FOUNDRY_PROJECT_ENDPOINT` and `APPLICATIONINSIGHTS_CONNECTION_STRING` — because they are **auto‑injected by the Foundry runtime**, so there it is **9 instead of 11**.

**And the Key Vault?** At startup, `main.py` retrieves the secret and puts it into `os.environ["APP_OBO_CLIENT_SECRET"]`, so `utils.py` reads it as before. Naturally, `APP_OBO_CLIENT_SECRET_NAME` is **not** a vault key — it is the local variable that holds the **name** of the Key Vault secret. Reading from the vault requires it to be in **Azure RBAC** mode with the **Key Vault Secrets User** role — the topic of the [next chapter](#6-storing-secrets-key-vault-and-managed-identity).

> [!WARNING]
> **`APPLICATIONINSIGHTS_CONNECTION_STRING` CANNOT be quoted.** It must be written as a single string **without** quotes — otherwise the SDK fails to parse it. (The other variables can stay quoted.)

**`.env`** — variables used by the agent when it runs locally (11 variables; all needed to run inside the Foundry container **except** the 2 auto‑injected ones — App Insights + project endpoint):

```dotenv
# --------------------------------------------------------
# .env.example for ha02-azureopenaiagent — copy to .env
# and fill in values. NEVER commit .env to source control.
# --------------------------------------------------------

# --------------------------------------------------------
# Microsoft Azure section
# --------------------------------------------------------
KEY_VAULT_URL="https://mauromikeyvault01.vault.azure.net/"
APP_OBO_TENANT_ID="3ad0b905-34ab-4116-93d9-c1dcc2d35af6"
APP_OBO_CLIENT_ID="3a0fad96-b026-4f5f-914a-fc6348656f6b"
APP_OBO_CLIENT_SECRET_NAME="APP-OBO-CLIENT-SECRET"
GRAPH_SCOPES='["https://graph.microsoft.com/Files.Read"]'

# --------------------------------------------------------
# Microsoft Foundry section
# Format: https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>
# --------------------------------------------------------
FOUNDRY_PROJECT_ENDPOINT="https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
CLIENT_USER_TOKEN_HEADER="x-client-user-token"

# --------------------------------------------------------
# Monitoring section
# IMPORTANT: APPLICATIONINSIGHTS_CONNECTION_STRING CANNOT BE QUOTED.
# It must be a single string without quotes.
# --------------------------------------------------------
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=b8637e87-3083-427a-8b03-32391c706b58;IngestionEndpoint=https://swedencentral-0.in.applicationinsights.azure.com/;LiveEndpoint=https://swedencentral.livediagnostics.monitor.azure.com/;ApplicationId=15bfc2ba-379c-4422-b11c-bbcac3cecac7
AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING="true"
ENABLE_SENSITIVE_DATA="true"
```

[↑ Back to top](#table-of-contents)

---

## 6. Storing Secrets: Key Vault and Managed Identity

**Should we store the secrets right next to the variables, in `.env`? No!** We use **Azure Key Vault + Managed Identity**. The standard pattern **decouples secret rotation from deployment**: the OBO client secret lives in the vault, the code reads it at runtime, and `azure.yaml` carries only non‑secret values.

### The challenge — a different identity locally vs. in the container

- **Locally**, access to the Key Vault happens by default through the **developer's credentials** stored via the CLI (`az login` / the user), because authentication uses `DefaultAzureCredential`. So if the user who ran `az login` has at least the **Key Vault Secrets User** RBAC role, they can read the secrets even from code running locally (executed by the CLI or by VS Code).
- **In the Foundry container**, instead, `DefaultAzureCredential` uses the **container's managed identity**. We therefore need to retrieve the object ID of the identity that runs the agent and assign **it** the **Key Vault Secrets User** RBAC role.

### Two planes that must be kept distinct

Before the solution, one fundamental point: there are **two separate, independent planes** — the first is *"who gets in"*, the second is *"with which identity the agent presents itself to the outside"*.

**1) Ingress — who can invoke the agent.** The caller (a user or a service principal) must hold the **Foundry User** role **on the project** (not on the agent). This governs invocation access.

**2) Egress — with which identity the agent accesses remote resources** *(we will obtain this identity only after the deployment).* The agent runs under its own **Agent Identity (Microsoft Entra Agent ID)**: a **per‑instance service principal**, distinct both from the caller and from the Foundry account's managed identity. Roles on resources (e.g. **Key Vault Secrets User**) are assigned to **this** identity.

Two handy verification commands (post‑assignment):

```bash
# Identities that can invoke a Foundry Project (Foundry User role):
PROJECT_SCOPE="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
az role assignment list --scope "$PROJECT_SCOPE" \
  --query "[?roleDefinitionName=='Foundry User'].{principal:principalId, type:principalType}" -o table

# Identities that can access the Key Vault resource:
RES_SCOPE="/subscriptions/.../providers/Microsoft.KeyVault/vaults/<kv>"
az role assignment list --scope "$RES_SCOPE" \
  --query "[?principalType=='ServicePrincipal'].{principal:principalId, role:roleDefinitionName}" -o table
```

### Assigning **Foundry User** to a service principal (ingress)

The following three screenshots show how to assign the **Foundry User** role to an *Entra ID registered application* — or, more precisely, to its **Service Principal** instance `svc-foundry-dataplane-access-dev`.

First, note the application's **Application (client) ID** on the App registration blade:

![Azure portal — App registration svc-foundry-dataplane-access-dev, Essentials. The Application (client) ID is highlighted (b0cc68f2-87d7-491d-8cc2-…), alongside the Object ID and the Directory (tenant) ID.](images/04-assign-foundry-user-sp-app-registration.png)

The same application also appears as an **Enterprise Application** (its Service Principal), with a matching Application ID:

![Azure portal — Enterprise Application svc-foundry-dataplane-access-dev, Properties: Name, the highlighted Application ID (b0cc68f2-87d7-491d-8cc2-…), and the Object ID.](images/05-assign-foundry-user-sp-enterprise-app.png)

Then, on the **Foundry project's** Access control (IAM) → Role assignments, we grant that service principal the **Foundry User** role:

![Azure portal — the aif7159-standard-agent-project Foundry project, Access control (IAM) → Role assignments, filtered by the client ID. Under "Foundry User (1)", the service principal svc-foundry-dataplane-access-dev is listed as the assignee.](images/06-foundry-user-role-assignment.png)

### Assigning **Key Vault Secrets User** to the Agent Identity (egress)

The next three screenshots show how to retrieve the **agent's identity** inside the Foundry portal → select the agent, open **Details**, and read the **Entra agent identity** ID. That ID is then added to the **Key Vault** IAM with the **Key Vault Secrets User** role.

![Microsoft Foundry portal — agent hello-world-python-responses (Version 1, Running), Details tab. Under "Identity & access", the "Entra agent identity" ID is highlighted, together with the "Entra agent blueprint" ID.](images/07-agent-identity-foundry-portal.png)

![Azure portal — Key Vault mauromikeyvault01, Access control (IAM) → Add role assignment. Selected role: Key Vault Secrets User; "Assign access to: User, group, or service principal"; the Select members panel is filtered by the agent identity's object ID and shows the agent's service identity (cog-…-mm-foundry-account0001-project01-hello-world-python-…).](images/08-keyvault-add-role-assignment.png)

![Azure portal — Key Vault mauromikeyvault01, Access control (IAM), role assignments grouped by role. Under "Key Vault Secrets User" the agent's service principal (foundry7159-aif7159-standard-agent-project-hell…) is listed with its object ID.](images/09-keyvault-iam-agent-identity.png)

### Summary

| Needed for… | Correct identity | How to obtain it |
|---|---|---|
| **Invoking** the agent | the caller, with **Foundry User** on the project | `az role assignment list` on the project scope |
| The agent **accessing a resource** | the **Agent Identity** (per‑instance SP) | from the resource's role assignments / the Foundry portal / Microsoft Entra Agent ID |

### Why Key Vault beats `.env`, and what's even better

- **No redeploy on rotation:** rotate the secret in the Key Vault → the agent reads the updated value at the next `get_secret` (or on container restart). **No `azd deploy`.**
- **Even better (remove the secret entirely):** for OBO you can use **Workload Identity Federation** — the app registration trusts the agent's managed identity, which obtains tokens **without a client secret**. **Zero secrets to rotate.** It is more setup but is the ideal long‑term approach (there is a dedicated skill, `entra-agent-id`).
- **Library:** the only package to add to `requirements.txt` to access Key Vault programmatically is **`azure-keyvault-secrets`**.

### References

- **Foundry RBAC** — roles and assignments on the project: <https://learn.microsoft.com/azure/ai-foundry/concepts/rbac-ai-foundry>
- **Microsoft Entra Agent ID** — the Blueprint → BlueprintPrincipal → Agent Identity model, per‑identity permissions, and OBO / `fmi_path` token exchange: Microsoft Learn, search *"Microsoft Entra Agent ID"*.

[↑ Back to top](#table-of-contents)

---

## 7. Customizing the Sample: monitoring.py and the Handler

### 7.1 Add `monitoring.py` (and fix the logger in `main.py`)

Add `monitoring.py`, and import it in `main.py` — remembering that `load_dotenv()` is called inside `monitoring`.

**Fundamental logging detail:** in `main.py` the `logger` imported from `monitoring` is **overwritten** by the line `logger = logging.getLogger(__name__)`, so our logging settings and filters would **not** be applied to our logs. We remove that line (and the now‑redundant `import logging`) so that the logger configuration set in `monitoring.py` is actually used:

![VS Code main.py imports. Green "ADD THIS LINE" on `from monitoring import logger`; red "DELETE THIS LINE" on `import logging`; and red "DELETE THIS LINE" on `logger = logging.getLogger(__name__)`.](images/10-mainpy-logger-edits.png)

`monitoring.py` (initial version):

```python
import os
import logging
from dotenv import load_dotenv

load_dotenv()

if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(logging_level=logging.INFO)
```

> We refine `monitoring.py` further in [Chapter 11](#11-observability-isolating-telemetry-in-application-insights) to isolate our agent's telemetry in Application Insights.

### 7.2 Run `main.py` in debug mode

Expected terminal output when the host starts:

```text
2026-07-06 00:22:51,588 INFO azure.ai.agentserver: AgentServerHost starting on 0.0.0.0:8088
2026-07-06 00:22:51,591 INFO azure.ai.agentserver: AgentServerHost started
2026-07-06 00:22:51,592 INFO azure.ai.agentserver: Connectivity:
2026-07-06 00:22:51,592 INFO azure.ai.agentserver: Connectivity: project_endpoint=https://foundry7159.services.ai.azure.com
[2026-07-06 00:22:51 +0200] [397896] [INFO] Running on http://0.0.0.0:8088 (CTRL + C to quit)
2026-07-06 00:22:51,593 INFO hypercorn.error: Running on http://0.0.0.0:8088 (CTRL + C to quit)
```

### 7.3 The handler (bring‑your‑own Responses)

The **key difference** compared to `azure-ai-agentserver-agentframework`: there, `from_agent_framework(agent)` did everything; **here we write the handler ourselves and call the model**. That is the price *and* the power of *bring‑your‑own* — and it gives us access to `context`, hence to the `x-client-*` headers.

```python
@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    """Forward user input to the model with conversation history."""
    user_assertion = context.client_headers.get(os.environ["CLIENT_USER_TOKEN_HEADER"], "")
    logger.info(f"User assertion: {user_assertion}")

    user_input = await context.get_input_text() or "Hello!"
    history = await context.get_history()
    input_items = _build_input(user_input, history)

    response = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _responses_client.create(
            model=_model,
            instructions=_SYSTEM_PROMPT,
            input=input_items,
            store=False,
        ),
    )
    return TextResponse(context, request, text=response.output_text)
```

What each piece does:

- We **write the handler ourselves** — in the `agentframework` version it did not exist, because the adapter generated it.
- We **retrieve the token** transmitted via `CLIENT_USER_TOKEN_HEADER` (i.e. `x-client-user-token`).
- `context.get_input_text()` → the user message; `context.get_history()` → the history managed by the platform.
- `_build_input(...)` transforms history + message into the Responses API input format (a list of `{role, content}`).
- `_responses_client.create(...)` calls the model (a blocking call → wrapped in `run_in_executor` so it does not block the event loop).
- It returns `TextResponse(... text=response.output_text)`.

[↑ Back to top](#table-of-contents)

---

## 8. First Local Test of the Hosted Agent

We are ready for the first test of this `azure-ai-agentserver-responses` hosted agent. The procedure:

1. Put a **breakpoint** in `main.py` on the line `user_input = await context.get_input_text() or "Hello!"`.
2. Run the **first** REST request from `agent_via_responses_simple.http` — the one **without** `x-client-user-token`.
3. Run the **second** REST request and verify the value in `context.client_headers["x-client-user-token"]`.

True, we are local and it *could* behave differently once published — but, as we will see, it works as a hosted agent on Foundry too.

Request file (`agent_via_responses_simple.http`):

```http
@baseUrl = http://localhost:8088
@query = What is a meaning function? Please answer in less than 10 words.

POST {{baseUrl}}/responses
Content-Type: application/json
x-client-user-token: aaa

{
  "input": "{{query}}"
}
```

In the debugger we can confirm that the handler receives the request input **and** the `x-client-user-token` header (here set to `aaa`), visible under `context.client_headers`:

![VS Code debugging main.py: execution paused at the breakpoint on the user_input line. The Variables panel expands context.client_headers and highlights 'x-client-user-token': '"aaa"', with request = {'input': 'What is a meaning function. Answer in…'} — proving the custom header reached the handler.](images/11-handler-debug-user-assertion.png)

And the HTTP response comes back `200 OK` with the model's answer:

![The HTTP Response (200). Headers include x-platform-server: azure-ai-agentserver-core/2.0.0b7 and azure-ai-agentserver-responses/1.0.0b8. The JSON body's output → content → output_text reads "Maps expressions to their referents or truth conditions." with status "completed".](images/12-local-test-response-200.png)

### How streaming works here

The client (Playground, Teams, API) decides whether it wants `stream: true` or `false`. When you return a `TextResponse`, it is the **host** that bridges:

- Non‑streaming client → receives the complete response.
- Streaming client → the host wraps your text in the Responses protocol's streaming events.

So our current handler **already works for both Playground and Teams** — no need to handle the two cases by hand.

### The real difference (true streaming vs. not)

There is a UX/latency nuance:

- **`TextResponse`** = you produce the entire text and then the host delivers it (possibly "packaged" as a stream). The user waits for the model to finish before seeing anything.
- **True streaming (token‑by‑token)** = the model's tokens flow as they are generated. To do this you do **not** return a `TextResponse`, but a **streaming response** (an async generator of events provided by the responses SDK), fed by the model's stream.

| What you want | What you return | Works in Playground/Teams? |
|---|---|---|
| Simple, complete response | `TextResponse` (current) | ✅ Yes (the host adapts) |
| Real‑time token‑by‑token | streaming response (async gen of events) | ✅ Yes, with better UX |

When we add MAF: `await agent.run(text)` → non‑streaming (returns the complete result) → maps to `TextResponse`. Perfect to start. MAF also offers `agent.run_stream(...)` → if you later want true streaming, we use that plus the host's streaming response.

[↑ Back to top](#table-of-contents)

---

## 9. Adding a Dockerfile (Optional)

In this context a Dockerfile is **not strictly needed**, because later we do a **code deployment**, not a **container deployment**. Still, it is useful to see and costs very little. The steps:

1. **Duplicate `.env` into `.env.docker`** and add the last 3 lines, so Docker can authenticate to Foundry with a **service principal** that is a *Foundry User* of that project. **These label names are fixed** (`AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` — the names `DefaultAzureCredential` looks for):

   ```dotenv
   AZURE_TENANT_ID=3ad0b905-34ab-4116-93d9-c1dcc2d35af6
   AZURE_CLIENT_ID=b0cc68f2-87d7-491d-8cc2-60624256126e
   AZURE_CLIENT_SECRET=4bp***
   ```

2. **Clean the environment** if needed:

   ```bash
   for id in $(docker images -aq); do docker rmi -f "$id"; done
   for id in $(docker ps -aq); do docker rm -f "$id"; done
   ```

3. **Build the container and run it on port 8080** (mapping to the container's 8088):

   ```bash
   docker build -t hello-world-python-responses .
   docker run --rm -p 8080:8088 --env-file .env.docker hello-world-python-responses
   ```

The `Dockerfile` itself:

```dockerfile
FROM python:3.13-slim
WORKDIR /app

# Copy only the application files — do NOT copy .env (secrets must be
# injected at runtime via environment variables or --env-file).

# Copy requirements first to leverage Docker layer caching:
# pip install is re-executed only when requirements.txt changes,
# not on every source code change.
COPY requirements.txt user_agent/
WORKDIR /app/user_agent
RUN if [ -f requirements.txt ]; then \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt; \
    fi

# Copy source code after dependencies. Changes here only invalidate this layer.
COPY main.py utils.py monitoring.py ./

EXPOSE 8088
CMD ["python", "main.py"]
```

> As we will see in [Chapter 15](#15-agent-provisioning-and-deployment), because we use **code deploy** (a `codeConfiguration` block in `azure.yaml`), this **Dockerfile is ignored** at deploy time — Foundry builds the image server‑side from `requirements.txt`. The `COPY` list here matters only for a **local** Docker build.

[↑ Back to top](#table-of-contents)

---

## 10. From "Responses" to "Responses + Agent Framework (MAF)"

The downloaded project already works as‑is: the handler calls the Foundry model via the "raw" Responses API and returns the text. Now we transform it into the **MAF** version, which brings:

- **Automatic tool/function calling** (MAF manages the model→tool→model loop).
- **Multi‑step / multi‑agent orchestration**, thread/memory management.
- A **simpler handler**: one line (`agent.run`) instead of building input/history by hand.
- **Provider abstraction** + integrated middleware/telemetry.
- It keeps the **`-responses` host** → access to `x-client-*` and Playground/Teams compatibility.

**Prerequisite (dependencies):** add `agent-framework` (which brings `agent-framework-foundry` → `FoundryChatClient`). Do **not** add `agent-framework-azure-ai` (incompatible with `1.10`).

### Step 1 — Imports: add MAF

*Why:* `Agent` is the MAF authoring model; `FoundryChatClient` is the MAF client to the Foundry project's model.

```python
# after
from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient
```

### Step 2 — Imports: remove the "raw" Foundry client

```python
# before (removed)
from azure.ai.projects import AIProjectClient
```

### Step 3 — Imports: remove the input‑building models

```python
# before (removed)
from azure.ai.agentserver.responses.models import (
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
)
```

### Step 4 — Replace the "raw" client with a MAF client + agent

```python
# before
_responses_client = AIProjectClient(
    endpoint=_endpoint,
    credential=DefaultAzureCredential()
).get_openai_client().responses

# after
_chat_client = FoundryChatClient(
    project_endpoint=_endpoint,
    model=_model,
    credential=DefaultAzureCredential(),
)
_agent = Agent(
    _chat_client,                 # 1st positional = client
    _SYSTEM_PROMPT,               # 2nd positional = instructions
    name="BYO Responses Agent",
    # tools=[...],                # <-- MAF tools go here
)
```

### Step 5 — Remove `_ROLE_MAP` and `_build_input`

```python
# before (removed)
_ROLE_MAP = {
    MessageContentOutputTextContent: "assistant",
    MessageContentInputTextContent: "user",
}

def _build_input(current_input: str, history: list) -> list[dict]:
    items = []
    for item in history:
        for content in getattr(item, "content", None) or []:
            role = _ROLE_MAP.get(type(content))
            if role and content.text:
                items.append({"role": role, "content": content.text})
    items.append({"role": "user", "content": current_input})
    return items
```

### Step 6 — Handler: a single call to the agent

*Why:* `_agent.run()` is natively async (no `run_in_executor`) and encapsulates the LLM call plus any tool‑calling. You return `result.text`. Keep the first line and replace the rest:

```python
# after
user_input = await context.get_input_text() or "Hello!"
result = await _agent.run(user_input)
return TextResponse(context, request, text=result.text)
```

**Unchanged:** `app = ResponsesAgentServerHost(...)`, the `@app.response_handler` decorator, `TextResponse`, and the rest of the host.

> **Step 7 — customize and test `monitoring.py` for observability** is large enough to deserve its own chapter → see [Chapter 11](#11-observability-isolating-telemetry-in-application-insights).

[↑ Back to top](#table-of-contents)

---

## 11. Observability: Isolating Telemetry in Application Insights

The application works fine, so let's take the chance to set up tracking on Application Insights properly, so that afterwards we can **isolate only our agent's telemetry**.

### 11.1 A dedicated cloud role name

The most structured and robust approach is to give this app a **dedicated cloud role name**, so every trace is "stamped" with a unique identifier (independent of the logger name and of APIM). In `monitoring.py`, set `OTEL_SERVICE_NAME` **before** `configure_azure_monitor()`. This makes every telemetry item (traces, requests, dependencies) carry `cloud_RoleName == "hello-world-python-responses"`.

> Only the black‑background lines below must be added; the surrounding (green) lines only mark where they go.

```python
import os
import logging
from dotenv import load_dotenv

load_dotenv()  # MUST be first: env vars must be set before any import reads them

THISAPP_NAME = "hello-world-python-responses"

# --- Azure Monitor setup ---------------------------------------------------
# We configure Azure Monitor OURSELVES at INFO level so our logger.info() traces
# reach Application Insights. The agentserver runtime also configures OpenTelemetry
# internally, so the double setup may emit two harmless one-time startup warnings:
#   "Overriding of current LoggerProvider is not allowed"
#   "Overriding of current TracerProvider is not allowed"
# These are cosmetic only: they fire once at startup and do not affect runtime.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    # Give this app a distinct cloud role name so ALL its telemetry (traces, requests,
    # dependencies) is stamped with cloud_RoleName == this value. This is what lets you
    # isolate it in a shared Application Insights resource (e.g. away from APIM noise).
    # Must be set BEFORE configure_azure_monitor() reads the environment.
    os.environ.setdefault("OTEL_SERVICE_NAME", THISAPP_NAME)  # e.g. "hello-world-python-responses"

    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(logging_level=logging.INFO)  # capture INFO+ (default is WARNING)

# Configure logging - WARNING for everything else, while INFO for this module only
logging.basicConfig(level=logging.WARNING)  # "father" logger at WARNING to avoid noise from other modules
```

A KQL query to extract all logs tied to our agent:

```kql
traces
| where cloud_RoleName == "hello-world-python-responses"
| project timestamp, message, severityLevel, operation_Id, cloud_RoleName
| order by timestamp desc
```

To reconstruct an end‑to‑end conversation, every HTTP request carries an `operation_Id` you can group by.

### 11.2 The problem: `severityLevel` is a fragile filter

`cloud_RoleName` gets us all the logs generated **during** the agent's execution — but that includes telemetry from **other components** that write to the same instrumentation string. The filter `logger.setLevel(logging.INFO)` we set in `monitoring.py` only means "Information" (`severityLevel >= 1`) — it does **not** distinguish *who* wrote the log. So `where severityLevel >= 1` tells App Insights to capture **all** INFO+ logs of the process — including uvicorn, the runtime, and the framework, not just ours:

![Application Insights Logs query results for cloud_RoleName == "hello-world-python-responses" filtered by severityLevel >= 1, with three annotated example rows: "access log by uvicorn (web server)", "runtime log → azure.ai.agentserver", and "framework log (agent_framework)" — showing that the severity filter also captures non-application logs.](images/13-appinsights-severity-filter-noise.png)

So `severityLevel` and `!startswith "Inbound POST"` are a **fragile, imprecise** filter.

### 11.3 The fix: a custom dimension via a log filter

Extracting *all* traces tied to our application is one thing; extracting *only* the traces **we explicitly created** is another. The most reliable way to isolate only the messages written by our code is to **stamp them** with a property we control. We add a logging filter that appends `log_source="app"` to every record from our logger:

> Only the black‑background part (the filter class and its registration) must be added; the surrounding (green) lines only mark where they go.

```python
# Configure logging - WARNING for everything else, while INFO for this module only
logging.basicConfig(level=logging.WARNING)  # "father" logger at WARNING to avoid noise from other modules
logger = logging.getLogger(__name__)        # "child" logger for this module
logger.setLevel(logging.INFO)               # INFO for more detailed logs from our module

class _AppLogFilter(logging.Filter):
    """Stamp every record from OUR logger with a custom dimension so it can be
    isolated in Application Insights, independently of severity level.
    In App Insights it lands in customDimensions['log_source'] == 'app'."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.log_source = "app"
        return True

logger.addFilter(_AppLogFilter())           # only records going through THIS logger get tagged
if not logger.handlers:                      # avoid duplicate handlers on reload
    ...
```

Now run, ask a question, and use this query to see **only** the logs written by our code:

```kql
traces
| where cloud_RoleName == "hello-world-python-responses"
| where customDimensions.log_source == "app"
| project timestamp, message, severityLevel, operation_Id
| order by timestamp desc
```

### 11.4 Azure‑side tips (so you don't rewrite the query every time)

- In **App Insights → Logs**, paste the query and click **Save → Save as query** (e.g. `HelloWorldAgent`). Find it again under **Queries → Saved queries**.
- Or **Pin to dashboard** for an always‑visible widget.
- For continuous monitoring, create a **New alert rule** from the query (e.g. alert if `severityLevel >= 3` / errors appear for your `cloud_RoleName`).

[↑ Back to top](#table-of-contents)

---

## 12. Real vs. Simulated Streaming

**Is this true streaming or simulated?** It is **simulated: full‑then‑deliver** — and for now we leave it as is.

With `result = await _agent.run(user_input)` + `TextResponse(...)`: `agent.run()` waits for the **entire** model response to complete; then you return all the text in a `TextResponse`; the host **can** deliver it to a streaming client by "packaging" it into the protocol's events, but the tokens **do not** flow in real time from the model. So it is exactly like the default with plain Responses (`_responses_client.create(...)` without `stream=True`): produce‑all‑then‑return. Only **who** makes the call changes (MAF instead of the raw client), not the streaming.

### To get true (token‑by‑token) streaming

Two changes are needed:

1. Use `_agent.run_stream(user_input)` instead of `_agent.run(...)` → MAF gives you an async iterator that emits partial updates as the model generates.
2. Return from the handler a **streaming response** of the `-responses` host (an async generator of events) instead of a `TextResponse`, forwarding the chunks arriving from `run_stream`.

*(The exact name of the streaming response type we will verify in the SDK when we implement it.)*

### Summary

| Version | Streaming |
|---|---|
| Default Responses (`create`, no stream) | Simulated (full‑then‑deliver) |
| Current MAF (`agent.run` + `TextResponse`) | Simulated (full‑then‑deliver) |
| MAF streaming (`agent.run_stream` + streaming response) | True (token‑by‑token) |

**Recommendation:** for the "from scratch" documentation, keep the **non‑streaming** version as the baseline (simple, works everywhere) and add streaming as an **optional advanced variant**.

[↑ Back to top](#table-of-contents)

---

## 13. Adding a Tool to the MAF Agent (Graph + OBO)

To test **Microsoft Graph** engagement, we add a **tool** to the agent. MAF makes this extremely convenient.

First we import the **`utils`** library, which contains the function `onedrive_root_folders(user_assertion: str)` — given the correct Graph‑scoped token via the `user_assertion` parameter, it returns the folders in the user's OneDrive root. In the imports we also add **`contextvars`**, which lets us store per‑session ("per‑request") globals.

### The OBO subtlety: never pass the token as a parameter

Clearly, somewhere the function will have to use the **user token** to access Graph via **OBO**. But that token **cannot** be passed as a tool parameter: the LLM that prepares the tool call **does not know it** (and rightly so — it is a secret). So we **inject the user assertion (Token C) into a `ContextVar`**, so the tool can read it on its own:

```python
from utils import onedrive_root_folders
import contextvars

# Per-request user assertion (Token C), exposed to tools via a ContextVar so it is
# NOT an LLM-visible tool parameter. The handler sets it; the tool reads it.
_current_user_assertion: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_assertion", default=""
)
```

### The helper that calls Graph (`onedrive_root_folders`)

Instead of implementing the Graph call inside the tool, we write a **helper function** and have the tool invoke it. Being internal and never called by the LLM, it can freely accept `user_assertion` **as a parameter**, because the tool passes it in after reading it from the `ContextVar`. This function does the **token exchange**: from **Token C** it derives **Token D**, the real bearer to Graph.

```python
def onedrive_root_folders(user_assertion: str) -> list[dict]:
    """OBO-exchange the user assertion (Token C) for a Microsoft Graph token,
    then return the biggest folder in the user's OneDrive root.
    Returns a human-readable string and never raises (any failure is reported
    in the returned text)."""
    scopes = ast.literal_eval(
        os.environ.get("GRAPH_SCOPES", '["https://graph.microsoft.com/Files.Read"]')
    )
    token = token_exchange(user_assertion, scopes)  # Token D
    if token.startswith("[graph]"):  # token_exchange returns an error string on failure
        return token
    try:
        resp = requests.get(
            GRAPH_ROOT_CHILDREN,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return f"[graph] /me/drive/root/children -> {resp.status_code}: {resp.text[:300]}"
        folders = [
            {"name": it["name"], "size": it["size"], "childCount": it["folder"]["childCount"]}
            for it in resp.json().get("value", [])
            if "folder" in it
        ]
        if not folders:
            return "No folders found in the OneDrive root."
        return f"Here are the folders on your OneDrive root: {folders}"
    except Exception as e:  # noqa: BLE001 - report any failure as text, never crash the tool
        return f"[graph] error: {type(e).__name__}: {e}"
```

### The OBO token exchange (`token_exchange`) and reading the secret from Key Vault

To call Graph, the token must have `aud="https://graph.microsoft.com/Files.Read"`. It is obtained by **exchanging** the user assertion through a `ConfidentialClientApplication` that authenticates **silently**, using its `APP_OBO_CLIENT_ID` and `APP_OBO_CLIENT_SECRET`:

```python
def token_exchange(user_assertion: str, scopes: list) -> str:
    tenant_id = os.environ.get("APP_OBO_TENANT_ID")
    client_id = os.environ.get("APP_OBO_CLIENT_ID")
    client_secret = os.environ.get("APP_OBO_CLIENT_SECRET")
    if not (tenant_id and client_id and client_secret):
        return (
            "[graph] OBO not configured "
            "(set APP_OBO_TENANT_ID / APP_OBO_CLIENT_ID / APP_OBO_CLIENT_SECRET)"
        )
    # Token D: App-OBO (confidential client) exchanges Token C for a Graph token.
    app = msal.ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_on_behalf_of(user_assertion=user_assertion, scopes=scopes)
    if "access_token" not in result:
        return (
            f"[graph] OBO failed: {result.get('error')}: "
            f"{str(result.get('error_description', ''))[:300]}"
        )
    return result["access_token"]
```

The `APP_OBO_CLIENT_SECRET` is pulled from Key Vault via the `SecretClient` of `azure.keyvault.secrets` (see [Chapter 6](#6-storing-secrets-key-vault-and-managed-identity)):

```python
from azure.keyvault.secrets import SecretClient

os.environ["APP_OBO_CLIENT_SECRET"] = SecretClient(
    vault_url=os.environ["KEY_VAULT_URL"],
    credential=DefaultAzureCredential(),
).get_secret(os.environ["APP_OBO_CLIENT_SECRET_NAME"]).value

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
```

### The async tool wrapper

The tool is the async function `onedrive_root_folders_async`, which calls the "real" `onedrive_root_folders`:

```python
async def onedrive_root_folders_async() -> str:
    """Return the name and size of all folders in the signed-in user's OneDrive root.
    Use ONLY for questions about the user's own OneDrive files or folders (e.g.
    "what is the biggest folder in my OneDrive?")."""
    assertion = _current_user_assertion.get()
    if not assertion:
        return "No user token is available, so I cannot access the user's OneDrive."
    # token_exchange + Graph REST are blocking -> run off the event loop.
    return await asyncio.to_thread(onedrive_root_folders, assertion)
```

### The handler: capture the assertion and register the tool

Functions that do the token exchange (then OBO) need the secondary token — the `user_assertion` — passed via the `x-client-user-token` header. So the handler must first **retrieve it, log it, and store it** into the `ContextVar` before running the agent:

```python
@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    """Forward user input to the model with conversation history."""
    user_input = await context.get_input_text() or "Hello!"
    user_assertion = context.client_headers.get(os.environ["CLIENT_USER_TOKEN_HEADER"], "")
    logger.info(f"User assertion received. Length: {len(user_assertion)}.")
    _current_user_assertion.set(user_assertion)

    result = await _agent.run(user_input)
    return TextResponse(context, request, text=result.text)
```

Finally, register `onedrive_root_folders_async` as a tool of the agent. When the agent's LLM deems it necessary, it has the framework invoke the function:

```python
_agent = Agent(
    _chat_client,                        # 1st positional = client
    _SYSTEM_PROMPT,                      # 2nd positional = instructions
    name="BYO Responses Agent",
    tools=[onedrive_root_folders_async], # <-- MAF tools go here
)
```

> The `ContextVar` is a **per‑request** variable: it prevents concurrent requests from overwriting each other, which would happen with a normal global variable.

[↑ Back to top](#table-of-contents)

---

## 14. Installing AZD Extensions

When we install `microsoft.foundry`, `azd` automatically pulls in all its Foundry dependencies (projects, connections, inspector, routines, skills, toolboxes). So `microsoft.foundry` is effectively the **meta‑package** that bundles everything.

Useful commands:

```bash
# upgrade one extension
azd extension upgrade <extension-id>
# upgrade them all
azd extension upgrade --all
```

![Terminal output of `azd extension list` (run from ~/git_repos/hosted_agents/agents/hello-world-responses01), listing the Foundry extensions and their status: azure.ai.agents "Foundry agents (Beta)" 1.0.0-beta.5 (Up to date), azure.ai.connections, azure.ai.inspector, azure.ai.projects, azure.ai.routines, azure.ai.skills, azure.ai.toolboxes, and microsoft.foundry "Microsoft Foundry (Beta)" 1.0.0-beta.1 (Up to date), among others.](images/14-azd-extension-list.png)

[↑ Back to top](#table-of-contents)

---

## 15. Agent Provisioning and Deployment

### 15.1 The AZD environment

Now that we have a working hosted agent, we create the **named deployment profile** — the `azd` **environment**. It lives in `.azure/<name>/` at the project root (next to `azure.yaml`) and contains: subscription, region, and the `.env` from which `azd` resolves the `${...}` placeholders. **It has nothing to do with your code** — it records only the deploy state.

```bash
# Select the folder and reload VS Code
cd ..
cd ..
code . --reuse-window

# Create the environment
azd env new hello-world-responses02-dev
```

![VS Code Explorer showing the .azure/ folder expanded: the newly created hello-world-responses02-dev environment with .env, .env.lock, config.json, and .gitignore, alongside src/hello-world-python-responses.](images/15-azd-environment-created.png)

> ⚠️ **Do not confuse** this with a possible `.env` in the project root (the one `load_dotenv()` uses in `monitoring.py` for the local `python main.py` run): that is a **different** file, for a **different** purpose. The one under `.azure/…/` belongs only to `azd`.

### 15.2 Container environment variables

The agent needs **11 variables** (see [5.3](#53-variables-for-running-the-agent-the-env-file)); the hosted agent on Foundry needs **two fewer** — `FOUNDRY_PROJECT_ENDPOINT` and `APPLICATIONINSIGHTS_CONNECTION_STRING` — because they are **auto‑injected by the Foundry runtime**, so it is **9 instead of 11**. Those 9 go into `azure.yaml`'s `environmentVariables`; for the CLI to resolve them at `azd deploy`, they must exist in the environment's own `.env` under `.azure/<env_name>/`.

`azure.yaml` **assumes** those variables exist: if one is missing, `${NAME}` resolves to an **empty string**. Values can be written directly into the `.env`, or set with `azd env set X y`; `azd env get-values` reads them back.

**`azure.yaml` — the 9 container variables:**

```yaml
environmentVariables:
  - name: KEY_VAULT_URL
    value: ${KEY_VAULT_URL}
  - name: APP_OBO_TENANT_ID
    value: ${APP_OBO_TENANT_ID}
  - name: APP_OBO_CLIENT_ID
    value: ${APP_OBO_CLIENT_ID}
  - name: APP_OBO_CLIENT_SECRET_NAME
    value: ${APP_OBO_CLIENT_SECRET_NAME}
  - name: GRAPH_SCOPES
    value: ${GRAPH_SCOPES}
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  - name: CLIENT_USER_TOKEN_HEADER
    value: ${CLIENT_USER_TOKEN_HEADER}
  - name: AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING
    value: ${AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING}
  - name: ENABLE_SENSITIVE_DATA
    value: ${ENABLE_SENSITIVE_DATA}
```

Key characteristics of the **environment** `.env`:

- The only pre‑existing variable is `AZURE_ENV_NAME`, added automatically when we create the environment — we leave it.
- Add the **9 variables** that must be injected into the container.
- Add the **2 variables** for deploying into an **existing** project, **or** the **2 variables** for a **new** project.
- `FOUNDRY_PROJECT_ENDPOINT` is needed not because its value is injected into the container, but because the `azd` CLI must know **where** the Foundry project is.
- ⚠️ For a **new** project you **cannot** specify the Foundry resource name — only the resource group and the project name.

**Minimal environment `.env` (grouped):**

```dotenv
# -- Pre-existing (auto-added by `azd env new`) --
AZURE_ENV_NAME="hello-world-responses02-dev"

# -- Common --
AZURE_SUBSCRIPTION_ID=eca2eddb-0f0c-4351-a634-52751499eeea
AZURE_LOCATION=swedencentral

# -- Agent-dedicated (the 9 container variables) --
KEY_VAULT_URL=https://mauromikeyvault01.vault.azure.net/
APP_OBO_TENANT_ID=3ad0b905-34ab-4116-93d9-c1dcc2d35af6
APP_OBO_CLIENT_ID=3a0fad96-b026-4f5f-914a-fc6348656f6b
APP_OBO_CLIENT_SECRET_NAME=APP-OBO-CLIENT-SECRET
GRAPH_SCOPES=["https://graph.microsoft.com/Files.Read"]
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.4-mini
CLIENT_USER_TOKEN_HEADER=x-client-user-token
AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
ENABLE_SENSITIVE_DATA=true

# -- For deploy into an EXISTING project --
FOUNDRY_PROJECT_ENDPOINT=https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project
AZURE_AI_PROJECT_ID=/subscriptions/eca2eddb-0f0c-4351-a634-52751499eeea/resourceGroups/rg-aifoundry7159/providers/Microsoft.CognitiveServices/accounts/foundry7159/projects/aif7159-standard-agent-project

# -- For deploy into a NEW project (instead of the two above) --
AZURE_RESOURCE_GROUP="rg-mauromi0001-foundry-dev"
AZURE_AI_PROJECT_NAME="mm-foundry-account0001-project01"
```

### 15.3 Do we always provision? It depends…

Inside `azure.yaml`, under `services:`, there are **two services**: **a)** `ai-project` (`host: azure.ai.project`) and **b)** `hello-world-python-responses` (`host: azure.ai.agent`):

```yaml
name: hello-world-python-responses
services:
  ai-project:
    host: azure.ai.project
    deployments:
      - name: gpt-5.4-mini
        model:
          format: OpenAI
          name: gpt-5.4-mini
          version: '2026-03-17'
        sku:
          name: GlobalStandard
          capacity: 10
  hello-world-python-responses:
    host: azure.ai.agent
    metadata:
      tags:
        - AI Agent Hosting
        - Responses Protocol
        - Bring Your Own
        - Python
    project: src/hello-world-python-responses
    language: python
    codeConfiguration:
      runtime: python_3_13
      entryPoint: main.py
    uses:
      - ai-project
    kind: hosted
```

Two cases:

| | Deploy into an **existing** Foundry project | Deploy into a **new** Foundry project |
|---|---|---|
| **`azure.yaml`** | **Remove** the `ai-project` service (everything from `ai-project:` to `capacity: 10`) **and** the `uses: - ai-project` reference at the bottom of the agent service | **Keep** both services |
| **Env vars** | (use the existing‑project vars) | add `AZURE_SUBSCRIPTION_ID` and `AZURE_LOCATION` |
| **Provision** | **No** `azd provision` | Run `azd provision` |

For the **new‑project** path, `azd provision` creates everything:

```console
mauromi@mauromistudio01:~/git_repos/hosted_agents/agents/hello-world-responses01$ azd provision
Provisioning Azure resources (azd provision)
Provisioning Azure resources can take some time.

Subscription: MngEnvMCAP883652-mauromi (eca2eddb-0f0c-4351-a634-52751499eeea)
Location: Sweden Central

SUCCESS: Your application was provisioned in Azure in 1 minute 43 seconds.
You can view the resources created under the resource group rg-mm-hello-world-responses01-dev in Azure Portal:
https://portal.azure.com/#@/resource/subscriptions/eca2eddb-0f0c-4351-a634-52751499eeea/resourceGroups/rg-mm-hello-world-responses01-dev/overview
```

> **Practical rule — one environment ≈ one deploy target.** A reused environment carries over the values already in its `.env` (subscription, endpoint, previous deploy output). To continue/update a deployment, reuse the environment; to start clean (e.g. change the target project), create a new env or overwrite values with `azd env set`. Don't mix two targets in one environment.

### 15.4 And now — Deployment!

**1. Verify the environment `.env`.** Provision or not, confirm the variables and the project you are about to deploy to:

```bash
azd env get-values
# must see your existing project
azd ai project show --output json
```

```json
{
  "endpoint": "https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project",
  "source": "azdEnv",
  "sourceDetail": "azd env",
  "azdEnv": "hello-world-responses02-dev"
}
```

**2. Verify `.agentignore` and `.azdignore` (in the root).** Because `project: .` zips the **entire** folder and this project was born with the old flow (without an ignore file), **without them** `azd` would also package `.venv`, `__pycache__`, and — above all — `.azure`, which contains your **secrets**. So creating these files is **indispensable**. `.agentignore` is read by the **agents extension's code deploy**; `.azdignore` by **`azd` core**. Keep them **identical**:

```gitignore
# Allowlist model: exclude everything, then re-include ONLY what the agent
# needs at runtime. This mirrors the COPY set of the Dockerfile
# (requirements.txt + main.py + utils.py + monitoring.py).
#
# To add a runtime file, add another `!<file>` line below.
/*
!main.py
!monitoring.py
!utils.py
!requirements.txt
```

**3. `azd deploy` ties `azure.yaml` + environment.** It reads `azure.yaml` (the *what*), takes the active environment (`.azure/<env>/.env`: the *where* + the `${...}` values), resolves the placeholders, and publishes to the target.

**4. How it picks the files: NOT from the Dockerfile.** We use **code deploy** (`codeConfiguration` in `azure.yaml`), so the **Dockerfile is ignored**. `azd` zips the service folder (`project: .`), excludes what `.agentignore` lists, uploads the ZIP; **Foundry builds the image server‑side**, installs from `requirements.txt`, and runs `entryPoint: main.py`.

#### Deploy method: Code or Docker Container?

Decided by the presence of `codeConfiguration` in `azure.yaml`, **not** by the Dockerfile:

- **Code deploy:** active when the `codeConfiguration` branch is present:

  ```yaml
  codeConfiguration:
    runtime: python_3_13
    entryPoint: main.py
  ```

- **Container deploy:** active when `codeConfiguration` is **absent** — `azd` builds the Dockerfile and pushes it to the Foundry project's ACR.

> If you ever see `Packaging container` in the logs while expecting a code deploy, `azd` took the container path by mistake → check that `codeConfiguration` is present and correct.

#### Run the deployment

```console
mauromi@mauromistudio01:~/git_repos/hosted_agents/agents/hello-world-responses01$ azd deploy

Service                         Status        Duration
──────────────────────────────  ────────────  ──────────
● hello-world-python-responses  Done          1m25s

- Agent playground (portal): https://ai.azure.com/nextgen/r/7KLt2w8MQ1GmNFJ1FJnu6g,rg-aifoundry7159,,foundry7159,aif7159-standard-agent-project/build/agents/hello-world-python-responses/build?version=1
- Agent endpoint (responses): https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project/agents/hello-world-python-responses/endpoint/protocols/openai/responses?api-version=v1

Next:
  azd ai agent show hello-world-python-responses
  verify it's running

  see src/hello-world-python-responses/README.md
  find the sample-specific payload

  azd ai agent invoke hello-world-python-responses '<payload>'
  test with the sample-specific payload

SUCCESS: Your application was deployed to Azure in 1 minute 25 seconds.
```

#### What the deploy adds to the environment `.env`

After `azd deploy` (into an existing Foundry project), the environment `.env` gains the published agent's endpoints, name, and version:

```dotenv
# -- added after the deployment --
AGENT_HELLO_WORLD_PYTHON_RESPONSES_ENDPOINT="https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project/agents/hello-world-python-responses/versions/1"
AGENT_HELLO_WORLD_PYTHON_RESPONSES_NAME="hello-world-python-responses"
AGENT_HELLO_WORLD_PYTHON_RESPONSES_RESPONSES_ENDPOINT="https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project/agents/hello-world-python-responses/endpoint/protocols/openai/responses?api-version=v1"
AGENT_HELLO_WORLD_PYTHON_RESPONSES_VERSION=1
```

### 15.5 Granting the deployed agent access to Key Vault

The agent's **Egress identity** (see [Chapter 6](#6-storing-secrets-key-vault-and-managed-identity)) only exists **after** the deployment. Now that the agent is deployed, retrieve its **Entra agent identity** from the Foundry portal → select the agent → **Details** → copy the ID:

![Microsoft Foundry portal — agent hello-world-python-responses (Running, Version 1), Details tab → Agent configuration. Under "Identity & access", the "Entra agent identity" ID (fd5d65ea-b2ec-4fcf-…) is highlighted with a copy button, alongside the "Entra agent blueprint" ID.](images/16-deployed-agent-identity-details.png)

Then, on the **Key Vault** → Access control (IAM) → **Add role assignment**, grant that identity the **Key Vault Secrets User** role: pick the role, choose *User, group, or service principal*, search by the identity's object ID, select the agent's service identity, and confirm:

![Azure portal — Key Vault mauromikeyvault01, Add role assignment. Selected role: Key Vault Secrets User; "Assign access to: User, group, or service principal"; the Select members panel is filtered by the agent identity (fd5d65ea-b2ec-4fcf-b6f1-0f687dd585f2) and its ServiceIdentity (foundry7159-aif7159-standard-age…) is selected, ready to click Select.](images/17-keyvault-grant-deployed-agent.png)

### 15.6 What if I need to re‑deploy?

The short answer is **`azd deploy` for almost everything**:

| What we changed | Command |
|---|---|
| Code (`main.py`, `utils.py`, …) | `azd deploy` |
| `requirements.txt` | `azd deploy` (the remote build reinstalls) |
| Value of an env var in the `azd` environment (`azd env set …`) | `azd deploy` |
| `azure.yaml`: add/remove an env var, cpu/memory | `azd deploy` |
| `azure.yaml`: model/infra (deployments, sku, capacity) | `azd provision` → then `azd deploy` |

> **Rule:** `azd deploy` covers code, dependencies, and env‑var values. You need `azd provision` only if you touch the **infrastructure** (model, capacity, resources). Every `azd deploy` creates a **new immutable version** of the agent.

#### ⚠️ There are TWO `.env` files (a typical source of confusion)

| File | What it is for | Effect on the deploy |
|---|---|---|
| `.env` in the project root | Local run only (`python main.py`, via `python-dotenv`) | **None.** Editing it does NOT change the agent on Foundry |
| `.azure/<env>/.env` (`azd` environment) | Source of the `${...}` in `azure.yaml` at deploy | Change here + `azd deploy` → the container gets the new values |

To change a value in the container, put it in the **`azd` environment**:

```bash
azd env set NAME_VAR new_value
azd deploy
```

> **Note:** if you change only the endpoint/agent‑card (not env, not code), there is the shortcut `azd ai agent endpoint update`, which does **not** create a new version.

### 15.7 Invoking the hosted agent on Foundry

First, recall that the agent must **read from Key Vault**, and to do so we must assign the RBAC role using the **agent's identity** — as described in [Chapter 6, plane 2 (Egress)](#6-storing-secrets-key-vault-and-managed-identity) — *which we obtain only after the deployment*.

At that point we can invoke the agent from a client able to pass it **both** tokens: the **authorization token for Foundry** *plus* the **user‑delegated token** for the app registration that performs the token exchange to obtain the MS Graph user token. Here is the result — the deployed agent answering a question about the user's own OneDrive, end‑to‑end:

![The end-to-end result in VS Code: main.py (left) with the handler that reads x-client-user-token, stores it in the per-request ContextVar, and runs the MAF agent with the OneDrive tool; on the right, the successful HTTP 200 Response from invoking the deployed hosted agent on Foundry.](images/18-final-invocation-result.png)

### Appendix — Python packages and dependencies

**Basic principle.** `requirements.txt` is the input we manage by hand. It is used **locally** by `uv` (to create the virtual environment) and **at deploy time** by the hosted‑agent build in Foundry (installed with `pip` inside the container). So it must be resolvable by **both `uv` and `pip`**; `pyproject.toml` and `uv.lock` are generated by `uv` from it.

**Two mandatory rules:**

1. **Use the sub‑packages you import, NOT the `agent-framework` meta‑package.** The meta drags in all integrations (openai, anthropic, bedrock, redis, hyperlight…). `hyperlight` requires `hyperlight-sandbox-backend-wasm`, which `pip` **cannot** install in the container (`uv` locally can, `pip` in the build cannot → deploy fails).

   | Import in code | Package in `requirements.txt` |
   |---|---|
   | `from agent_framework import ...` | `agent-framework-core` |
   | `from agent_framework_foundry import ...` | `agent-framework-foundry` |

2. **No comments (`#`) in `requirements.txt`.** The install script uses `uv add $(cat requirements.txt)`: every line becomes an argument, so a comment line would be read as a package name → error.

**Current `requirements.txt`:**

```text
azure-ai-agentserver-responses==1.0.0b8
azure-ai-projects==2.0.1
azure-identity==1.25.3
debugpy==1.8.21
python-dotenv==1.2.2
azure-monitor-opentelemetry==1.8.9
agent-framework-core==1.10.0
agent-framework-foundry==1.0.1
```

`--prerelease=allow` is necessary because some versions are pre‑release (e.g. `azure-ai-agentserver-responses==1.0.0b8`).

**Local environment creation (script):**

```bash
# 1. mkdir the new folder and cd into it
# 2. initialize the uv project (creates pyproject.toml)
uv init . --python 3.13
# 3. create the local virtual environment
uv venv
# 4. activate the environment:
source .venv/bin/activate         # Linux/macOS
# .\.venv\Scripts\activate.ps1    # Windows
# 5. add the libraries (--active is ESSENTIAL: uses the active venv):
uv add --active $(cat requirements.txt) --prerelease=allow   # in bulk (NO comments in the file!)
uv add --active <package-name> --prerelease=allow            # single manual add
# 6. verify the installed packages
uv pip list
# 7. sync the structure (only with a pre-existing pyproject.toml)
uv sync --active --prerelease=allow
# 8. deactivate
deactivate
```

> If a package installs locally with `uv` but fails in the build with `pip`, the cause is almost always a package `pip` cannot fetch (like `hyperlight-sandbox-backend-wasm`): the fix is to declare only the specific sub‑packages you actually use, never the meta.

[↑ Back to top](#table-of-contents)

---

*Document generated from the source Word document “2026-07-12-A Microsoft Foundry Hosted Agents.docx”, translated from Italian to English and reorganized into chapters for publication. All screenshots are the original captures from the source document.*
