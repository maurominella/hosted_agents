FROM python:3.13-slim

WORKDIR /app

COPY . user_agent/

WORKDIR /app/user_agent

# Install agentserver packages first (they pull in older agent-framework versions that are compatible with agentserver)
# then upgrade agent-framework-* to the required rc versions
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

CMD ["python", "main.py"]