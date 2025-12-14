# Multi-stage build for AI ETF Trader
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY . .

# Install Python dependencies
RUN uv sync --frozen

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 aiuser

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/decisions /app/trades /app/tmp && \
    chown -R aiuser:aiuser /app

# Switch to non-root user
USER aiuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/api/performance || exit 1

# Expose port
EXPOSE 5000

# Default command: start web server
CMD ["python", "-m", "src.web_app"]


