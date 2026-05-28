FROM python:3.13-slim

WORKDIR /app

# Copy only the application files — do NOT copy .env (secrets must be
# injected at runtime via environment variables or --env-file)

# Copy requirements first to leverage Docker layer caching:
# pip install is re-executed only when requirements.txt changes,
# not on every source code change.
COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code after dependencies — changes here only invalidate this layer.
COPY main.py .env ./

EXPOSE 8088

CMD ["python", "main.py"]