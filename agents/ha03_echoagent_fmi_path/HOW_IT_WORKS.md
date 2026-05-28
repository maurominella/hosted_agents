# How It Works — User Identity via `fmi_path`

This document explains how this hosted agent extracts caller identity information (`oid` and `tid`) from an incoming request, first in **local simulation** and then in **real Microsoft Foundry** execution.

---

## The Identity Information: `oid` and `tid`

When a user calls an agent, two pieces of identity are typically available:

| Field | Meaning | Source |
|-------|---------|--------|
| `oid` | **Object ID** — the unique identifier of the calling user (or service principal) in Azure AD / Entra ID | JWT claim `oid` |
| `tid` | **Tenant ID** — the Azure AD tenant that issued the token | JWT claim `tid` |

Inside the agent code, these are accessed via:

```python
from azure.ai.agentserver.core.tools import ContextVarUserProvider

user_info = ContextVarUserProvider.default_user_info_context.get(None)
oid = user_info.object_id if user_info else "n/a"
tid = user_info.tenant_id if user_info else "n/a"
```

`ContextVarUserProvider.default_user_info_context` is a Python `contextvars.ContextVar`. The **Azure AI AgentServer** framework (the host process that wraps your agent) is responsible for populating it on every request, before `run()` is called.

---

## Local Simulation — Injecting Identity via HTTP Headers

When running the agent locally with `python main.py` (or inside a container on port 8088), the AgentServer reads two custom HTTP headers and uses them to populate the context variable:

| HTTP Header | Maps to |
|-------------|---------|
| `x-aml-oid` | `user_info.object_id` |
| `x-aml-tid` | `user_info.tenant_id` |

This means you can simulate any caller identity without a real token. Using the **VS Code REST Client** extension, the call looks like this:

```http
@baseUrl = http://localhost:8088
@access_token = <your_access_token>
@user_oid    = <caller_object_id>
@tenant_id   = <caller_tenant_id>

### Call without identity (oid and tid will be "n/a")
POST {{baseUrl}}/responses
Content-Type: application/json

{
    "input": "Where is Sydney? What is the current time there?"
}


### Call with simulated identity
POST {{baseUrl}}/responses
Content-Type: application/json
x-aml-oid: {{user_oid}}
x-aml-tid: {{tenant_id}}

{
    "input": "Where is Sydney? What is the current time there?"
}
```

In the first call, `user_info` will be `None` inside the agent, and both `oid` and `tid` will fall back to `"n/a"`.  
In the second call, the AgentServer parses the two headers, builds a `UserInfo` object, and stores it in the context variable — so the agent sees real values.

### What the agent returns

The `EchoAgent` in `main.py` reflects both the original input and the resolved identity back to the caller:

```
🔊 Echo: Where is Sydney? What is the current time there?

oid=<object_id>
tid=<tenant_id>
```

---

## From Local Simulation to Real Microsoft Foundry Execution

When the agent is deployed as a **Foundry Hosted Agent**, the flow changes: the user authenticates via **Entra ID (Azure AD)** before reaching the agent, and Foundry itself injects the identity — you no longer need to pass `x-aml-oid` / `x-aml-tid` manually.

### The `fmi_path` flow

```
User / Client app
      │
      │  HTTPS request  +  Bearer token (Entra ID JWT)
      ▼
Microsoft Foundry Gateway
      │
      │  Validates the JWT
      │  Extracts  oid  and  tid  from token claims
      │  Injects   x-aml-oid  and  x-aml-tid  into the internal request
      ▼
AgentServer (your container)
      │
      │  Reads the headers → populates ContextVarUserProvider
      ▼
EchoAgent.run()
      │
      └─ user_info.object_id  ✓  (real caller OID)
         user_info.tenant_id  ✓  (real caller TID)
```

The key insight is that the **same header mechanism** is used in both cases. The difference is:

| Environment | Who injects `x-aml-oid` / `x-aml-tid` |
|-------------|----------------------------------------|
| Local | You (manually in the HTTP request) |
| Microsoft Foundry | The Foundry Gateway (automatically, after JWT validation) |

This means your agent code does **not need to change** between local development and production — `ContextVarUserProvider.default_user_info_context.get(None)` works identically in both environments.

### Calling the deployed agent from Foundry

Once deployed, clients call the agent through the Foundry endpoint and must present a valid Entra ID Bearer token:

```http
POST https://<foundry_account>.services.ai.azure.com/api/projects/<project>/responses
Content-Type: application/json
Authorization: Bearer <entra_id_access_token>

{
    "input": "Where is Sydney? What is the current time there?"
}
```

Foundry validates the token, then forwards the request to your container with the resolved `x-aml-oid` and `x-aml-tid` headers already set. The agent receives the exact same `user_info` object it would have received locally when you passed the headers manually.
