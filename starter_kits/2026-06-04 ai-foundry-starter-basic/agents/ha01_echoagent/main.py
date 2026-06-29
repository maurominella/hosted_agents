import os
import logging
from dotenv import load_dotenv
load_dotenv()  # MUST be first: env vars must be set before any import reads them

# --- Azure Monitor setup ---------------------------------------------------
# We configure Azure Monitor OURSELVES at INFO level so our logger.info() traces
# reach Application Insights. The agentserver runtime also configures OpenTelemetry
# internally, so the double setup may emit two harmless one-time startup warnings:
#   "Overriding of current LoggerProvider is not allowed"
#   "Overriding of current TracerProvider is not allowed"
# These are cosmetic only: they fire once at startup and do not affect runtime.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(logging_level=logging.INFO)  # capture INFO+ in App Insights (default is WARNING)

import asyncio

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    TextResponse,
)

import msal       # On-Behalf-Of token exchange (Token C -> Microsoft Graph token)
import requests   # one-shot Microsoft Graph call

# Configure logging - WARNING for everything else, while INFO for this module only
logging.basicConfig(level=logging.WARNING)  # "father" logger at WARNING to avoid noise from other modules
logger = logging.getLogger(__name__)        # "child" logger for this module
logger.setLevel(logging.INFO)               # INFO for more detailed logs from our module
if not logger.handlers:                     # avoid duplicate handlers on reload
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    logger.addHandler(_handler)
    logger.propagate = True                 # (default) so logs also reach the root logger

# --------------------------------------------------------------------------

if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.info("Azure Monitor is active.")
else:
    logger.info("Azure Monitor is not configured. No connection string found in environment variables.")

# --------------------------------------------------------------------------
# Static On-Behalf-Of + Microsoft Graph call
# --------------------------------------------------------------------------
GRAPH_SCOPES = ["https://graph.microsoft.com/Files.Read"]
GRAPH_ROOT_CHILDREN = (
    "https://graph.microsoft.com/v1.0/me/drive/root/children"
    "?$select=name,size,folder&$top=200"
)


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def biggest_onedrive_folder(user_assertion: str) -> str:
    """Exchange the user assertion (Token C) On-Behalf-Of for a Microsoft Graph
    token, then answer the fixed question "what is the biggest folder of my
    OneDrive home directory?". Returns a human-readable status string and never
    raises (any failure is reported in the returned text).
    """
    tenant = os.environ.get("APP_OBO_TENANT_ID")
    client_id = os.environ.get("APP_OBO_CLIENT_ID")
    client_secret = os.environ.get("APP_OBO_CLIENT_SECRET")
    if not (tenant and client_id and client_secret):
        return (
            "[graph] OBO not configured "
            "(set APP_OBO_TENANT_ID / APP_OBO_CLIENT_ID / APP_OBO_CLIENT_SECRET)"
        )

    try:
        # Token D: App-OBO (confidential client) exchanges Token C for a Graph token.
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            client_credential=client_secret,
        )
        result = app.acquire_token_on_behalf_of(
            user_assertion=user_assertion, scopes=GRAPH_SCOPES
        )
        if "access_token" not in result:
            return (
                f"[graph] OBO failed: {result.get('error')}: "
                f"{str(result.get('error_description', ''))[:300]}"
            )

        # One-shot Graph call: list OneDrive root children, pick the biggest folder.
        resp = requests.get(
            GRAPH_ROOT_CHILDREN,
            headers={"Authorization": f"Bearer {result['access_token']}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return f"[graph] /me/drive/root/children -> {resp.status_code}: {resp.text[:300]}"

        folders = [it for it in resp.json().get("value", []) if "folder" in it]
        if not folders:
            return "[graph] no folders found in the OneDrive root"
        biggest = max(folders, key=lambda it: it.get("size", 0))
        return (
            f"[graph] biggest OneDrive root folder: "
            f"'{biggest.get('name')}' ({_human_size(biggest.get('size', 0))})"
        )
    except Exception as e:  # noqa: BLE001 - report any failure as text, never crash the handler
        return f"[graph] error: {type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# Responses-protocol agent
# --------------------------------------------------------------------------
# Foundry forwards client-supplied "x-client-*" headers to the agent container
# (container protocol v2.0.0). The responses SDK surfaces them on
# ResponseContext.client_headers (keys normalized to lowercase). We read the user
# assertion (Token C) from "x-client-user-token" directly — no request-body
# metadata and no chunking needed.
CLIENT_USER_TOKEN_HEADER = "x-client-user-token"

app = ResponsesAgentServerHost()


# === TEMP DIAGNOSTIC MIDDLEWARE ============================================
# Pure-ASGI middleware that logs the NAMES (not values) of every inbound HTTP
# header on POST requests. This reveals exactly what the Foundry gateway
# forwards to the container — in particular whether any "x-client-*" headers
# survive and whether platform protocol-2.0.0 headers (x-agent-foundry-call-id,
# x-agent-user-id) are present. Remove once the passthrough is confirmed.
class _HeaderDiagMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("method") == "POST":
            keys = sorted(k.decode("latin-1") for k, _ in scope.get("headers", []))
            logger.info("[HDRDIAG] %s inbound header keys: %s", scope.get("path", "/"), keys)
        await self.app(scope, receive, send)


app.add_middleware(_HeaderDiagMiddleware)


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
) -> TextResponse:
    text = await context.get_input_text()
    logger.info("[INPUT] %s", text)

    if text:
        response_text = f"🔊 Echo: {text}"
    else:
        response_text = "Hello! I'm a custom echo agent. Send me a message and I'll echo it back."

    # === TEMP DIAGNOSTIC: read the forwarded user assertion (Token C) ===
    # Primary (and only) channel now: the "x-client-user-token" header, forwarded
    # by Foundry and exposed via context.client_headers.
    logger.info("[DIAG] client_headers keys: %s", sorted(context.client_headers.keys()))
    # platform_context signals which container protocol the gateway negotiated:
    # call_id (x-agent-foundry-call-id) and user_id (x-agent-user-id) are present
    # only under container protocol 2.0.0 — the same protocol that enables
    # x-client-* passthrough. If call_id is None, the gateway treats us as 1.0.0.
    logger.info(
        "[DIAG] platform_context call_id=%r user_id_key=%r",
        getattr(context.platform_context, "call_id", None),
        getattr(context.platform_context, "user_id_key", None),
    )
    assertion = context.client_headers.get(CLIENT_USER_TOKEN_HEADER, "")
    logger.info("[DIAG] user assertion present=%s len=%d", bool(assertion), len(assertion))

    if assertion:
        response_text += (
            f"\n\n[diag] user assertion (Token C): FOUND via {CLIENT_USER_TOKEN_HEADER} "
            f"(len={len(assertion)})"
        )
        # === STATIC OBO + GRAPH CALL ===
        # msal/requests are blocking; run off the event loop for this one-shot test.
        graph_answer = await asyncio.to_thread(biggest_onedrive_folder, assertion)
        logger.info("[GRAPH] %s", graph_answer)
        response_text += f"\n{graph_answer}"
    else:
        response_text += "\n\n[diag] user assertion (Token C): NOT present in x-client-* headers"

    logger.info("[OUTPUT] %s", response_text)
    return TextResponse(context, request, text=response_text)


if __name__ == "__main__":
    app.run()
