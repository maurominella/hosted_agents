"""
DESCRIPTION:
    This sample demonstrates how to retrieve a Hosted Agent, create a session, and invoke the OpenAI Responses API
    against that agent endpoint using the synchronous AIProjectClient.

    Sessions only work with Hosted Agents.

    Session operations are currently preview features.
    In the Python SDK, you access these operations via
    `project_client.beta.agents`.

USAGE:

    Before running the sample:

    pip install "azure-ai-projects>=2.1.0"

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in the Overview
       page of your Microsoft Foundry portal.
"""

import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import VersionRefIndicator

endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "https://foundry7159.services.ai.azure.com/api/projects/aif7159-standard-agent-project")
agent_name = "ha02-azureopenaiagent" # "ha01-echoagent", "ha02-azureopenaiagent"
isolation_key = "my-isolation-key"

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(
        endpoint=endpoint,
        credential=credential,
        allow_preview=True,
    ) as project_client,
):
    # Get the agent to find the latest version
    agent = project_client.agents.get(agent_name=agent_name)
    latest_version = agent.versions["latest"].version
    print(f"Agent: {agent.name}, version: {latest_version}")

    # Create a session for conversation state
    session = project_client.beta.agents.create_session(
        agent_name=agent_name,
        isolation_key=isolation_key,
        version_indicator=VersionRefIndicator(agent_version=latest_version),
    )
    print(f"Created session: {session.agent_session_id}")

    # Create an OpenAI client bound to the agent endpoint
    openai_client = project_client.get_openai_client(agent_name=agent_name)

    # --- NON-STREAMING ---
    response = openai_client.responses.create(
        input="Can you help me find available hotels in Seattle for a stay from April 25th to April 28th with a budget of $180 per night?",
        extra_body={
            "agent_session_id": session.agent_session_id,
        },
    )
    print(f"[non-streaming] Response: {response.output_text}")

    # --- STREAMING ---
    with openai_client.responses.stream(
        model="gpt-4o-UNEXSISTING-MODEL",  # model is required for streaming, but will be ignored by the agent endpoint
        input="Can you help me find available hotels in Seattle for a stay from April 25th to April 28th with a budget of $250 per night?",
        extra_body={
            "agent_session_id": session.agent_session_id,
        },
    ) as stream:
        print("[streaming] Response: ", end="", flush=True)
        for event in stream:
            # ResponseTextDeltaEvent carries incremental text
            if hasattr(event, "delta") and event.delta:
                print(event.delta, end="", flush=True)
        print()  # newline after stream ends

    # Clean up the session when done
    project_client.beta.agents.delete_session(
        agent_name=agent_name,
        session_id=session.agent_session_id,
        isolation_key=isolation_key,
    )