# hosted_agents
Microsoft Foundry Hosted Agents


## Python environmanet installation (just for testing)
```
uv init . --python 3.13
source .venv/bin/activate
uv add --active $(cat requirements.txt)
uv sync --active
```

# Docker tests locally
```
# build the image
docker build -t user-agent .

# run the container, mapping external 8089 to internal 8088
docker run -p 8089:8080 user-agent
```
