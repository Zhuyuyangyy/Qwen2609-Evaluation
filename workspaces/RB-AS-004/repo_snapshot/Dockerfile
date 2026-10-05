FROM python:3.12-slim

LABEL maintainer="AgentShield Team"
LABEL description="AgentShield V3 - Behavior-chain risk governance for multi-agent systems"

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create data directory for SQLite storage
RUN mkdir -p /data

# Environment variable defaults
ENV AGENTSHIELD_STORAGE=sqlite \
    AGENTSHIELD_DB_PATH=/data/agentshield.db \
    AGENTSHIELD_SESSION_TTL=86400 \
    AGENTSHIELD_AUTH_DISABLED=true \
    AGENTSHIELD_CORS_ORIGINS=* \
    AGENTSHIELD_DEFAULT_TENANT=default

# Expose the API port
EXPOSE 8011

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8011/health')" || exit 1

# Production entry point using uvicorn.
#
# The app package lives at /app/backend/app, so uvicorn must run with
# /app/backend on sys.path. Running from /app would make `app` unimportable
# (the earlier CMD `uvicorn backend.app.main:app` failed with
# "ModuleNotFoundError: No module named 'app'" in the Docker smoke test).
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8011", "--workers", "1"]
