FROM python:3.14-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for package management
RUN pip install --no-cache-dir --upgrade pip uv

# Create non-root user
RUN useradd -m -u 1000 cache-manager

# Copy project files
COPY pyproject.toml ./
COPY uv.lock ./
COPY README.md ./
COPY main.py ./
COPY src ./src

# Install dependencies and package with uv
RUN uv sync --frozen --no-dev

# Set ownership
RUN chown -R cache-manager:cache-manager /app

# Switch to non-root user
USER cache-manager

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8080), timeout=5)"

ENTRYPOINT ["uv", "run", "--no-dev", "pylinode-node-cache-manager"]
