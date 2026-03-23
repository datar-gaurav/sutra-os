FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git openssh-server \
    && rm -rf /var/lib/apt/lists/*

# Configure SSH
RUN mkdir -p /var/run/sshd && \
    echo 'PermitRootLogin prohibit-password' >> /etc/ssh/sshd_config && \
    mkdir -p /root/.ssh && \
    chmod 700 /root/.ssh && \
    echo ". /etc/profile.d/docker_env.sh" >> /root/.bashrc

# Install Google Cloud CLI for Web Auth
RUN curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts
ENV PATH=$PATH:/root/google-cloud-sdk/bin

# Install Python dependencies
COPY pyproject.toml .
# Copy source FIRST so setuptools can find packages
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers and dependencies
RUN playwright install chromium
RUN playwright install-deps chromium

# Make entrypoint executable
RUN chmod +x start.sh

EXPOSE 8000
ENTRYPOINT ["./start.sh"]
