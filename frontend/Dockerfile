FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 appuser

COPY pyproject.toml .

# Copy your streamlit application script BEFORE running pip install
COPY streamlit_app.py ./streamlit_app.py

# Install dependencies from your toml file
RUN pip install --no-cache-dir -e .

ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8080

# Switch to non-root user
USER appuser

# Added --server.headless=true so Streamlit runs smoothly in the cloud
CMD ["streamlit", "run", "streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8080", "--server.headless=true"]
