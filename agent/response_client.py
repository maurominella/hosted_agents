import asyncio

# requires `uv add --active agent-framework``
from agent_framework.openai import OpenAIChatClient
from agent_framework import Agent

azure_endpoint = "http://localhost:8089"
api_key = "whatever key"
model = "whatever model"

openai_chat_client = OpenAIChatClient(
    base_url=azure_endpoint,
    api_key=api_key,
    model=model
)

agent = Agent(
    client=openai_chat_client,
    instructions="You are a helpful AI Agent.",
)

response = asyncio.run(agent.run("Plan me a day trip"))

print(response.messages[-1].text)
