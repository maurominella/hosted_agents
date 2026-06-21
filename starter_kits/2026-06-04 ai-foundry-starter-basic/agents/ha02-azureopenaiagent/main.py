"""
Seattle Hotel Agent - A simple agent with a tool to find hotels in Seattle.
Uses Microsoft Agent Framework with Azure AI Foundry.
Ready for deployment to Foundry Hosted Agent service.
"""

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

import asyncio
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv

load_dotenv(override=True)

from agent_framework import Agent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import DefaultAzureCredential

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

# Configure these for your Foundry project
# Read the explicit variables present in the .env file
PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")  # e.g., "https://<project>.services.ai.azure.com"
MODEL_DEPLOYMENT_NAME = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini")  # Your model deployment name e.g., "gpt-4.1-mini"

# Simulated hotel data for Seattle
SEATTLE_HOTELS = [
    {
        "name": "Contoso Suites",
        "price_per_night": 189,
        "rating": 4.5,
        "location": "Downtown",
    },
    {
        "name": "Fabrikam Residences",
        "price_per_night": 159,
        "rating": 4.2,
        "location": "Pike Place Market",
    },
    {
        "name": "Alpine Ski House",
        "price_per_night": 249,
        "rating": 4.7,
        "location": "Seattle Center",
    },
    {
        "name": "Margie's Travel Lodge",
        "price_per_night": 219,
        "rating": 4.4,
        "location": "Waterfront",
    },
    {
        "name": "Northwind Inn",
        "price_per_night": 139,
        "rating": 4.0,
        "location": "Capitol Hill",
    },
    {
        "name": "Relecloud Hotel",
        "price_per_night": 99,
        "rating": 3.8,
        "location": "University District",
    },
    {
        "name": "Rat City Hostel",
        "price_per_night": 9,
        "rating": 2.1,
        "location": "Bronx",
    },
]


def get_available_hotels(
    check_in_date: Annotated[str, "Check-in date in YYYY-MM-DD format"],
    check_out_date: Annotated[str, "Check-out date in YYYY-MM-DD format"],
    max_price: Annotated[int, "Maximum price per night in USD (optional)"] = 500,
) -> str:
    """
    Get available hotels in Seattle for the specified dates.
    This simulates a call to a fake hotel availability API.
    """
    try:
        # Parse dates
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d")

        # Validate dates
        if check_out <= check_in:
            return "Error: Check-out date must be after check-in date."

        nights = (check_out - check_in).days

        # Filter hotels by price
        available_hotels = [
            hotel for hotel in SEATTLE_HOTELS if hotel["price_per_night"] <= max_price
        ]

        if not available_hotels:
            return (
                f"No hotels found in Seattle within your budget of ${max_price}/night."
            )

        # Build response
        result = f"Available hotels in Seattle from {check_in_date} to {check_out_date} ({nights} nights):\n\n"

        for hotel in available_hotels:
            total_cost = hotel["price_per_night"] * nights
            result += f"**{hotel['name']}**\n"
            result += f"   Location: {hotel['location']}\n"
            result += f"   Rating: {hotel['rating']}/5\n"
            result += f"   ${hotel['price_per_night']}/night (Total: ${total_cost})\n\n"

        return result

    except ValueError as e:
        return f"Error parsing dates. Please use YYYY-MM-DD format. Details: {str(e)}"


async def main():
    """Main function to run the agent as a web server."""
    async with (
        DefaultAzureCredential() as credential,
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT_NAME,
            credential=credential,
        ) as client,
    ):
        agent = Agent(
            client,
            name="SeattleHotelAgent",
            instructions="""You are a helpful travel assistant specializing in finding hotels in Seattle, Washington.

When a user asks about hotels in Seattle:
1. Ask for their check-in and check-out dates if not provided
2. Ask about their budget preferences if not mentioned
3. Use the get_available_hotels tool to find available options
4. Present the results in a friendly, informative way
5. Offer to help with additional questions about the hotels or Seattle

Be conversational and helpful. If users ask about things outside of Seattle hotels, 
politely let them know you specialize in Seattle hotel recommendations.""",
            tools=[get_available_hotels],
        )

        logger.info("Seattle Hotel Agent Server running on http://localhost:8088")
        server = from_agent_framework(agent)

        # PRIVACY WORKAROUND: the hosted agent framework hardcodes enable_sensitive_data=True
        # inside _configure_otel_providers(), ignoring the ENABLE_SENSITIVE_DATA env var that
        # agent_framework already documents and supports. This override restores the correct
        # behaviour: read ENABLE_SENSITIVE_DATA from the environment (default: false) so that
        # capturing LLM message content (prompts, completions) in App Insights is opt-in.
        # TODO: remove this once the framework reads ENABLE_SENSITIVE_DATA itself.
        def _configure_otel_providers_override(exporters):  # type: ignore[no-untyped-def]
            from agent_framework.observability import configure_otel_providers
            enable_sensitive_data = os.getenv("ENABLE_SENSITIVE_DATA", "false").lower() == "true"
            configure_otel_providers(enable_sensitive_data=enable_sensitive_data, exporters=exporters)
            return True

        server._configure_otel_providers = _configure_otel_providers_override  # type: ignore[attr-defined]

        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())