# Copyright (c) Microsoft. All rights reserved.

"""Hello World — Bring Your Own Responses agent.

Forwards user input to a Foundry model via the Responses API and streams
the reply back through the Responses protocol. See README.md for setup.
"""
from monitoring import logger
import asyncio
import os

from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient

from azure.identity import DefaultAzureCredential

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)

from utils import onedrive_root_folders
import contextvars

# Per-request user assertion (Token C), exposed to tools via a ContextVar so it is
# NOT an LLM-visible tool parameter. The handler sets it; the tool reads it.
_current_user_assertion: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_assertion", default=""
)

from azure.keyvault.secrets import SecretClient
os.environ["APP_OBO_CLIENT_SECRET"] = SecretClient(
    vault_url=os.environ["KEY_VAULT_URL"],
    credential=DefaultAzureCredential()
).get_secret(os.environ["APP_OBO_CLIENT_SECRET_NAME"]).value

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)

_SYSTEM_PROMPT = "You are a helpful AI assistant. Be concise and informative."

_chat_client = FoundryChatClient(
    project_endpoint=_endpoint,
    model=_model,
    credential=DefaultAzureCredential(),
)

async def onedrive_root_folders_async() -> str:
    """Return the name and size of all folders in the signed-in user's
    OneDrive root. Use ONLY for questions about the user's own OneDrive files or
    folders (e.g. "what is the biggest folder in my OneDrive?")."""
    assertion = _current_user_assertion.get()
    if not assertion:
        return "No user token is available, so I cannot access the user's OneDrive."
    # token_exchange + Graph REST are blocking -> run off the event loop.
    return await asyncio.to_thread(onedrive_root_folders, assertion)

_agent = Agent(
    _chat_client,        # 1º posizionale = client
    _SYSTEM_PROMPT,      # 2º posizionale = instructions
    name="BYO Responses Agent",
    tools=[onedrive_root_folders_async],       # <-- qui aggiungerai i tool MAF
)




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



app.run()
