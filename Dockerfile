###############################################
# Stage 1: Builder – install all dependencies
###############################################
FROM python:3.12-slim-bookworm AS builder

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

# Install system packages needed for building Python deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    python3-dev \
    libjpeg-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project first for dependency resolution
COPY deploy/docker/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy project source
COPY . /tmp/project/

# Install the Crawl4AI project
RUN pip install --user --no-cache-dir /tmp/project/

###############################################
# Stage 2: Runtime – slim & fast
###############################################
FROM python:3.12-slim-bookworm AS final

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers \
    PYTHON_ENV=production

# Install only minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libcups2 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libgbm1 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libxkbcommon0 \
    redis-server \
    supervisor \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install gunicorn globally so it is available for the non-root runtime user
RUN pip install --no-cache-dir gunicorn

###############################################
# Copy Python dependencies from builder stage
###############################################
COPY --from=builder /root/.local /root/.local
ENV PATH="/root/.local/bin:${PATH}"

# Ensure psutil is present/updated in the runtime image
RUN pip install --no-cache-dir --upgrade psutil

###############################################
# Copy application files
###############################################
COPY deploy/docker/supervisord.conf ${APP_HOME}/supervisord.conf
COPY deploy/docker/static ${APP_HOME}/static
COPY deploy/docker/* ${APP_HOME}/

###############################################
# Install Playwright browsers (prod only)
###############################################
RUN playwright install --with-deps

###############################################
# Setup non-root user
###############################################
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser && \
    mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser
USER appuser

###############################################
# Expose the correct port for DigitalOcean
###############################################
EXPOSE 8080

###############################################
# Start via supervisord (Gunicorn + Redis)
###############################################
CMD ["supervisord", "-c", "supervisord.conf"]
