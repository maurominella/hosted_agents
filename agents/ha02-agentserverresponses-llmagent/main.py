# Copyright (c) Microsoft. All rights reserved.

"""Hello World — Bring Your Own Responses agent.

Forwards user input to a Foundry model via the Responses API and streams
the reply back through the Responses protocol. See README.md for setup.
"""

from monitoring import logger # this has to stay here so that the Azure Monitor setup in init.py runs before any other imports
import asyncio
import os
import contextvars

# Microsoft Agent Framework (MAF) and Foundry libraries
from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
    TextResponse,
)


# my own utility functions
from utils import onedrive_root_folders

logger.info("Agent starts")

_kv = SecretClient(vault_url=os.environ["KEY_VAULT_URL"], credential=DefaultAzureCredential())

# Retrieve the APP_OBO_CLIENT_SECRET from Azure Key Vault and set it in the environment variable
os.environ["APP_OBO_CLIENT_SECRET"]=_kv.get_secret(os.environ["APP_OBO_CLIENT_SECRET_NAME"]).value

_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Be concise and informative. "
    "When the user asks about their own OneDrive files or folders, use the available tool."
)
maf_agent_name = "BYO Responses Agent" # this is the MAF agent created within the hosted agent

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]


# Agent Framework Client is a wrapper around the Foundry ChatClient that implements the Responses protocol.
_chat_client = FoundryChatClient(
    project_endpoint=_endpoint,
    model=_model,
    credential=DefaultAzureCredential(),
)

# Per-request user assertion (Token C), exposed to tools via a ContextVar so it is
# NOT an LLM-visible tool parameter. The handler sets it; the tool reads it.
_current_user_assertion: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_assertion", default=""
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
    _chat_client,            # 1º positional = client
    _SYSTEM_PROMPT,          # 2º positional = instructions
    name=maf_agent_name,
    tools=[onedrive_root_folders_async],
)

app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(default_fetch_history_count=20),
)


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    _cancellation_signal: asyncio.Event,
):
    """Forward user input to the model with conversation history."""
    user_assertion = context.client_headers.get(os.environ["CLIENT_USER_TOKEN_HEADER"], "")
    logger.info("User assertion present: %s (len=%d)", bool(user_assertion), len(user_assertion))
    _current_user_assertion.set(user_assertion)   # make Token C available to the OneDrive tool
    user_input = await context.get_input_text() or "Hello!"

    result = await _agent.run(user_input)
    return TextResponse(context, request, text=result.text)


app.run()