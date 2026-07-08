FROM python:3.13-slim

WORKDIR /app

# Copy only the application files — do NOT copy .env (secrets must be
# injected at runtime via environment variables or --env-file).

# Copy requirements first to leverage Docker layer caching:
# pip install is re-executed only when requirements.txt changes,
# not on every source code change.
COPY requirements.txt user_agent/

WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt; \
    fi

# Copy source code after dependencies. Changes here only invalidate this layer.
COPY main.py utils.py monitoring.py ./

EXPOSE 8088

CMD ["python", "main.py"]