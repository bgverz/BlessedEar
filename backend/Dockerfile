# backend/Dockerfile — production image
# Build: docker build -t blessedear-backend:latest .

FROM python:3.11-slim

# Install curl (for HEALTHCHECK) and gcc (for C extensions in scipy/numpy).
# Remove package lists afterward to keep the layer small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only the requirements first so Docker cache reuses this layer on
# code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.  .dockerignore excludes venv, tests, .env, etc.
COPY . .

# Run as a non-root user so a container escape does not grant root on the host.
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Probe the /health endpoint.  Container is marked unhealthy if it fails
# 3 times in a row, at which point the orchestrator will restart it.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production: no --reload, fixed number of workers.
# Override CMD in docker-compose.prod.yml if you need to adjust worker count.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
