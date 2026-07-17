# Changelog

All notable changes to this documentation are recorded in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-17

Initial public release of the **Microsoft Foundry Hosted Agents — End‑to‑End Guide**,
translated to English and reorganized into 16 chapters. It is meant to take a reader
from zero to a working, deployed agent, while also serving as reference documentation.
Derived from the source material "2026-07-17-A Microsoft Foundry Hosted Agents".

### Added

- **Objective and scenario** — the three framework choices (infrastructure, agentic,
  AZD publishing) and the two Entra ID registered applications
  (`svc-foundry-dataplane-access-dev` for Foundry project access, and
  `svc-agent-obo-downstream-dev` for the On‑Behalf‑Of exchange toward Microsoft Graph).
- **Creating the tokens** — the `refresh-tokens.sh` + `token-mapping.json` → `settings.json`
  flow for the VS Code REST Client, with the real‑scenario Bot Framework note.
- **Terminology** — hosted vs prompt agents, container‑based vs code‑based publishing,
  the three key concepts, and a comparison table of **Agent Framework / LangGraph /
  Bring‑Your‑Own** with the reasoned choice (Bring‑Your‑Own).
- **Sample selection** — `azd ai agent sample list`, the *Hello World (Responses,
  bring‑your‑own, Python)* sample, and a Bring‑Your‑Own vs Agent‑Framework
  `requirements.txt` comparison.
- **Schema change (July 6, 2026)** — `0.1.0-preview` → `1.0.0-beta.4`, from split
  manifests to a single native `azure.yaml`.
- **Local setup** — cloning, the uv environment, import verification, and the runtime
  `.env` (including the unquoted `APPLICATIONINSIGHTS_CONNECTION_STRING` caveat).
- **Secrets** — Azure Key Vault + Managed Identity, the ingress/egress identity planes,
  and assigning the **Key Vault Secrets User** role to the agent identity.
- **Customization** — `monitoring.py` (with the `main.py` logger fix), `utils.py`, and
  the bring‑your‑own handler.
- **First local test** — breakpoint + REST Client requests, verifying the
  `x-client-user-token` header reaches the handler.
- **Optional Dockerfile**, **migration to the Microsoft Agent Framework (MAF)**,
  **Application Insights observability** (dedicated cloud role name + `log_source`
  custom dimension), and notes on **real vs simulated streaming**.
- **Microsoft Graph tool via OBO** — per‑request `ContextVar`, the OBO `token_exchange`,
  and reading the client secret from Key Vault.
- **AZD extensions** and **provisioning / deployment / invocation** — existing vs new
  Foundry project, code deploy, granting the deployed agent access to Key Vault, the
  re‑deploy table, and the end‑to‑end invocation result.
- 24 original screenshots embedded throughout, a linked table of contents, and a
  Final Result preview.
