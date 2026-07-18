# Building a Microsoft Foundry Hosted Agent That Calls Microsoft Graph *On Behalf of the User*

*An end‑to‑end story: from the "bring‑your‑own" hosting decision to a deployed agent that reads your own OneDrive — as you — through an On‑Behalf‑Of flow.*

Most "hello world" agent tutorials stop at *"the model answered."* The interesting problems start right after: **how does an agent, running as a managed workload in the cloud, act on behalf of the human who is talking to it?** If a user asks *"what's the biggest folder in my OneDrive?"*, the agent must call Microsoft Graph **as that user** — not as itself, and not as a shared service account.

This article is the condensed story of building exactly that on **Microsoft Foundry**: a Python **Hosted Agent** that receives the caller's delegated token, exchanges it On‑Behalf‑Of (OBO), and answers using the user's own Graph data. The full, reproducible walkthrough — every command, every file, and all 24 screenshots — lives in the companion GitHub repository linked at the bottom.

## What we're building

A **Foundry Hosted Agent** is an agent whose code runs as a dedicated workload on Foundry's infrastructure — either as a container or, newer, straight from **code**. Foundry turns your Python into an HTTP service that speaks its container protocol, then hosts and scales it behind a standard endpoint (Playground, Teams, or a raw API).

Our agent has one non‑negotiable requirement: it must **read the custom `x-client-*` request headers**, because that's how the signed‑in user's **assertion token** is passed in. That single requirement drives almost every early design choice.

## Two identities do the heavy lifting

The scenario relies on two Microsoft Entra ID app registrations, each with a clear job:

- **`svc-foundry-dataplane-access-dev`** — authenticates to the Foundry *project*. Its service principal holds the **Foundry Agent Consumer** role (the new least‑privilege *invoke* role introduced in July 2026). The Foundry Gateway uses this token only to *let the caller in* — it is never forwarded inside the agent.
- **`svc-agent-obo-downstream-dev`** — the OBO app. It can take an existing **user** token (minted for an approved client such as Microsoft Teams) and **exchange** it for a Microsoft Graph token (`Files.Read`) scoped to that same user.

Keep these two planes separate in your head: one governs *who can invoke the agent*; the other governs *with which identity the agent reaches out to downstream services*.

## The decision that shapes everything: Bring‑Your‑Own

Foundry ships hosting libraries for three styles — **Agent Framework**, **LangGraph**, and **Bring‑Your‑Own (BYO)**. They're not agent frameworks; they build the *server* that exposes an agent and speaks Foundry's container protocol.

I picked **Bring‑Your‑Own**, for one blunt reason: the Agent Framework adapter doesn't expose the raw invocation headers, and I needed `x-client-*`. With BYO I write the request handler myself — a little more code, but full access to `context`. (I still use the **Microsoft Agent Framework** for the *agent* itself; it's additive.)

![Listing the available samples with `azd ai agent sample list` — the minimal "Hello World (Responses, without a framework, Python)" is the bring‑your‑own starting point.](https://raw.githubusercontent.com/<GH_USER>/<GH_REPO>/main/images/07-agent-sample-list.png)
*Choosing the host, not the framework: the bring‑your‑own Responses sample.*

## The payoff: one handler, the user's token, and a tool

Once the sample is upgraded to the Microsoft Agent Framework, the handler is almost boring — which is the point. It grabs the user assertion from the header, stashes it in a per‑request `ContextVar` (so it never becomes an LLM‑visible tool parameter), and lets the framework drive the model‑and‑tools loop:

```python
@app.response_handler
async def handler(request, context, _cancel):
    user_input = await context.get_input_text() or "Hello!"
    # the user's delegated token arrives in a custom header — stash it for the tool
    _current_user_assertion.set(
        context.client_headers.get(os.environ["CLIENT_USER_TOKEN_HEADER"], "")
    )
    result = await _agent.run(user_input)   # MAF drives model + tool-calling
    return TextResponse(context, request, text=result.text)
```

The OneDrive tool never sees that token as an argument. It reads it from the `ContextVar` and performs the **On‑Behalf‑Of** exchange — turning the user's token (*Token C*) into a real Microsoft Graph bearer (*Token D*):

```python
# Confidential-client OBO: exchange the user's token for a Graph token
app = msal.ConfidentialClientApplication(client_id, client_credential=secret, authority=...)
result = app.acquire_token_on_behalf_of(user_assertion=token_c, scopes=graph_scopes)
graph_token = result["access_token"]  # aud = https://graph.microsoft.com
```

## Secrets stay out of the code

The OBO client secret never lives in `.env` or in the image. It sits in **Azure Key Vault**, read at runtime with `DefaultAzureCredential`. The twist that trips people up: **locally** the code reads the vault with your `az login` identity; **in the container**, it reads it with the agent's own **Agent Identity (Microsoft Entra Agent ID)** — a per‑instance service principal you can only see *after* deployment, and to which you grant **Key Vault Secrets User**.

![The agent's own Entra Agent ID, visible in the Foundry portal only after deployment.](https://raw.githubusercontent.com/<GH_USER>/<GH_REPO>/main/images/12-agent-identity-foundry-portal.png)
*Egress identity: the agent reaches Key Vault and Graph under its own Entra Agent ID — not the caller's, not a shared account.*

## The result

Deployed with a single `azd deploy` (code deploy — no Docker build), the agent goes live as an immutable version. Invoked with the Foundry auth token **plus** the user‑delegated token, it does the full round trip: reads the header, runs the MAF agent, calls the OneDrive tool, exchanges the token On‑Behalf‑Of, and answers using the user's own files.

![The deployed agent answering a OneDrive question end‑to‑end, using On‑Behalf‑Of access to Microsoft Graph.](https://raw.githubusercontent.com/<GH_USER>/<GH_REPO>/main/images/24-final-invocation-result.png)
*The full round trip working: create → test locally → deploy → invoke as the user.*

## Read the full, step‑by‑step guide

This article is the map; the **complete hands‑on guide** is the territory — 16 chapters with every command, the full `main.py` / `utils.py` / `monitoring.py`, the Key Vault + RBAC setup, Application Insights observability, the `azure.yaml` and `azd` provisioning/deployment flow, and all 24 screenshots:

👉 **[Microsoft Foundry Hosted Agents — End‑to‑End Guide on GitHub](https://github.com/<GH_USER>/<GH_REPO>)**

If you're evaluating agent hosting on Foundry — or you just need delegated (OBO) access from an agent to Microsoft Graph — clone it, follow along, and you'll have a working, deployed agent by the end.

---

*Written by a Microsoft Senior Cloud Solution Architect (Cloud Apps & AI). Level: L400 — assumes familiarity with Azure, Python, and OAuth 2.0 / Entra ID.*
