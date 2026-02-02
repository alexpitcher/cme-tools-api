FROM python:3.12-slim AS base

# System deps: git (for backup service) + openssh-client (for scrapli system transport fallback)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

# Create data directory for git backup working directory
RUN mkdir -p /data/backup-workdir

# Non-root user
RUN useradd -r -m appuser && \
    chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
