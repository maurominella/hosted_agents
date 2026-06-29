import os
import logging
from dotenv import load_dotenv
load_dotenv()  # MUST be first: env vars must be set before any import reads them

# --- Azure Monitor setup ---------------------------------------------------
# We call configure_azure_monitor() OURSELVES first (with default INFO+ logging)
# because agent_framework also calls it internally during import — but at WARNING level,
# which would prevent our logger.info() traces from reaching App Insights.
# The double call causes OTel to emit two harmless startup warnings:
#   "Overriding of current LoggerProvider is not allowed"
#   "Overriding of current TracerProvider is not allowed"
# These are cosmetic only: they fire once at startup, do not affect runtime behaviour,
# and are not worth working around with extra complexity.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(logging_level=logging.INFO)  # capture INFO+ in App Insights (default is WARNING)

from typing import Any, AsyncGenerator

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
    Role,
    normalize_messages,
)
from azure.ai.agentserver.agentframework import from_agent_framework

import msal       # On-Behalf-Of token exchange (Token C -> Microsoft Graph token)
import requests   # one-shot Microsoft Graph call
from contextvars import ContextVar

# Per-request user assertion (Token C), captured from the "x-client-user-token"
# HTTP header. Foundry forwards this custom header to the agent container as-is
# (only the Authorization header is stripped), so the assertion no longer needs
# to be chunked into request-body metadata.
_client_user_token: ContextVar[str] = ContextVar("client_user_token", default="")


class ClientUserTokenMiddleware:
    """Pure-ASGI middleware that reads the forwarded user assertion from the
    'x-client-user-token' header and stores it in a ContextVar, so run() can read
    it without LLM involvement. Pure-ASGI (not BaseHTTPMiddleware) keeps the value
    in the same task/context as the agent execution.
    """

    HEADER = b"x-client-user-token"

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            raw_headers = scope.get("headers", [])
            # TEMP DIAGNOSTIC: log only header NAMES (never values) to discover
            # which headers Foundry actually forwards to the container.
            try:
                names = sorted(k.decode("latin-1") for k, _ in raw_headers)
                logging.getLogger(__name__).info(
                    "[DIAG] incoming header names (%d): %s", len(names), names
                )
            except Exception:  # noqa: BLE001 - diagnostics must never break the request
                pass
            for key, value in raw_headers:
                if key.lower() == self.HEADER:
                    _client_user_token.set(value.decode("latin-1"))
                    break
        await self.app(scope, receive, send)
# --------------------------------------------------------------------------

# Configure logging - WARNING for everything else, while INFO for this module only
logging.basicConfig(level=logging.WARNING) # this is the "father" logger, set to WARNING to avoid too much noise from other modules
logger = logging.getLogger(__name__) # this is the "child" logger for our module (this module)
logger.setLevel(logging.INFO) # we set the child logger to INFO to get more detailed logs from our module
if not logger.handlers: # avoid adding multiple handlers if this code is reloaded multiple times (e.g. during development)
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    logger.addHandler(_handler)
    logger.propagate = True # (default) so logs also reach the root logger

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
    except Exception as e:  # noqa: BLE001 - report any failure as text, never crash run()
        return f"[graph] error: {type(e).__name__}: {e}"


class EchoAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix.

    This demonstrates how to create a fully custom agent by extending BaseAgent
    and implementing the required run() method.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        custom_member: str = "Echo: ",
        **kwargs: Any,
    ) -> None:
        """Initialize the EchoAgent.

        Args:
            name: The name of the agent.
            description: The description of the agent.
            custom_member: A custom member variable for the agent.
            **kwargs: Additional keyword arguments passed to BaseAgent.
        """
        self.echo_prefix = custom_member
        super().__init__(
            name=name,
            description=description,
            **kwargs,
        )

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse | AsyncGenerator[AgentResponseUpdate, None]:
        """Execute the agent and return a complete response or a streaming generator.

        Args:
            messages: The message(s) to process.
            stream: If True, return an async generator of AgentResponseUpdate. If False, return AgentResponse.
            session: The conversation session (optional).
            **kwargs: Additional keyword arguments.

        Returns:
            When stream=False: An AgentResponse containing the agent's reply.
            When stream=True: An async generator yielding AgentResponseUpdate chunks.
        """
        normalized = normalize_messages(messages)

        # this is written to stderr, which is visible in the agent logs in Foundry - useful for debugging
        logger.info("run() called: stream=%s, messages=%d", stream, len(normalized) if normalized else 0)

        if not normalized:
            response_text = "Hello! I'm a custom echo agent. Send me a message and I'll echo it back."
        else:
            last_message = normalized[-1]
            if last_message.text:
                logger.info("[INPUT] %s", last_message.text)
                response_text = f"{self.echo_prefix}{last_message.text}"
            else:
                response_text = f"{self.echo_prefix}[Non-text message received]"

        # === TEMP DIAGNOSTIC: read the forwarded user assertion (Token C) ===
        # Primary channel: the "x-client-user-token" header, forwarded by Foundry
        # and captured by ClientUserTokenMiddleware into a ContextVar (no chunking).
        # Fallback: legacy chunked request-body metadata (ua_n + ua_0..ua_{n-1}),
        # kept for local/back-compat tests.
        assertion = _client_user_token.get("")
        source = "header"
        if not assertion:
            meta = getattr(self, "_request_headers", {}) or {}
            try:
                n = int(meta.get("ua_n", "0") or 0)
            except (TypeError, ValueError):
                n = 0
            assertion = "".join(meta.get(f"ua_{i}", "") for i in range(n))
            source = "metadata" if assertion else "none"
        logger.info("[DIAG] user assertion source=%s present=%s len=%d", source, bool(assertion), len(assertion))
        header_status = (
            f"[diag] user assertion (Token C): FOUND via {source} (len={len(assertion)})"
            if assertion
            else "[diag] user assertion (Token C): NOT present (header or metadata)"
        )
        response_text = f"{response_text}\n\n{header_status}"

        # === STATIC OBO + GRAPH CALL ===
        # If the user assertion (Token C) is present, exchange it On-Behalf-Of for
        # a Microsoft Graph token and answer the fixed question:
        # "what is the biggest folder of my OneDrive home directory?".
        # NOTE: msal/requests are blocking; acceptable here for a one-shot test.
        if assertion:
            graph_answer = biggest_onedrive_folder(assertion)
            logger.info("[GRAPH] %s", graph_answer)
            response_text = f"{response_text}\n{graph_answer}"

        logger.info("[OUTPUT] %s", response_text)

        # --- NON-STREAMING MODE ------------------------------------------------
        if not stream:
            async def _respond():
                ai = AgentResponse(messages=[Message(role="assistant", text=response_text)])
                return ai
            return _respond()

        # --- STREAMING MODE ----------------------------------------------------
        elif stream:
            async def generator():
                words = response_text.split()
                for i, word in enumerate(words):
                    chunk_text = f" {word}" if i > 0 else word
                    yield AgentResponseUpdate(
                        contents=[Content(type="text", text=chunk_text)],
                        role="assistant",
                    )

            # Return a valid async generator for streaming mode
            return ResponseStream(generator(), finalizer=AgentResponse.from_updates) # return generator()
            

def create_agent() -> EchoAgent:
    agent = EchoAgent(
        name="mauromi_agent_echo",
        description="A simple agent that echoes user messages",
        custom_member="🔊 Echo: ",
    )
    return agent

if __name__ == "__main__":
    MyEchoAgent = create_agent()
    server = from_agent_framework(MyEchoAgent)
    # Capture the forwarded user assertion from the x-client-user-token header.
    server.app.add_middleware(ClientUserTokenMiddleware)
    server.run()