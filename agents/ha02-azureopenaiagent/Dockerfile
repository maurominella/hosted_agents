FROM python:3.13-slim

WORKDIR /app

COPY main.py agent.yaml requirements.txt .env ./

RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

    # Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

EXPOSE 8088

CMD ["python", "main.py"]