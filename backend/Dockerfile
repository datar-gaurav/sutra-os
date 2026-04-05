FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (no SSH server)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
# Copy source FIRST so setuptools can find packages
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers to a shared path accessible by all users
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium && \
    playwright install-deps chromium && \
    chmod -R a+rx /ms-playwright

# Create non-root user and hand ownership of /app
RUN groupadd -r sutra && useradd -r -g sutra -d /app -s /bin/bash sutra \
    && chown -R sutra:sutra /app

# Make entrypoint executable
RUN chmod +x start.sh

USER sutra

EXPOSE 8000
ENTRYPOINT ["./start.sh"]
