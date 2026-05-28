# Using the pure OpenAI SDK to call the /responses endpoint exposed by the Agent Server.
from openai import AsyncOpenAI
import asyncio   

base_url = "http://localhost:8088"
api_key = "unexisting_openai_key"
model = "undexisting_model_id"
query = "Can you help me find available hotels in Seattle for a stay from April 25th to April 28th with a budget of $200 per night?" 

client = AsyncOpenAI(base_url=base_url, api_key=api_key)

response = asyncio.run(client.responses.create(
        model=model,
        input=query,
    ))

print(f"Response: {response.output_text}")