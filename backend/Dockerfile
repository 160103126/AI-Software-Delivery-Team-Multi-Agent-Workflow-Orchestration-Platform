FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 appuser

# 1. Copy the configuration file
COPY pyproject.toml .

# 2. FIXED: Copy the src directory BEFORE running pip install
COPY src ./src
COPY frontend ./frontend

# 3. Now pip install will succeed because the 'src' directory exists
RUN pip install --no-cache-dir -e .

# Switch to non-root user
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "ai_sdlc.api:app", "--host", "0.0.0.0", "--port", "8080", "--app-dir", "src"]
