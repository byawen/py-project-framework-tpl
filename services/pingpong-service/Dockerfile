# pingpong Service Dockerfile
FROM python:3.12-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY services/pingpong-service/pyproject.toml /app/

# Install dependencies
RUN uv pip install --system -e .

# Copy source code
COPY services/pingpong-service/src /app/src

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "pingpong_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
