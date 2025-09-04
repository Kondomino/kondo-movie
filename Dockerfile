FROM --platform=linux/amd64 python:3.13-slim-bookworm AS builder

RUN pip install poetry==1.8.3

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY poetry.lock pyproject.toml README.md ./

# Install system dependencies for building the project
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create the cache directory
RUN mkdir -p $POETRY_CACHE_DIR

RUN poetry install --only main --no-root

# Install Playwright Python package (but not browsers) in builder
RUN pip install playwright

FROM --platform=linux/amd64 python:3.13-slim-bookworm AS runner

# Install system dependencies including Chrome
RUN apt-get update && \
    apt-get install -y \
        ffmpeg \
        wget \
        gnupg \
        unzip \
        xvfb \
        libasound2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libxss1 \
        libnss3 \
        libx11-xcb1 && \
    wget -q -O /tmp/google-chrome.gpg https://dl.google.com/linux/linux_signing_key.pub && \
    gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg /tmp/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/google-chrome.gpg

# Set up Chrome for headless operation
ENV CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome \
    DISPLAY=:99

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Install Playwright browsers in the runner stage
RUN playwright install --with-deps

# Copy source code and tests
COPY src src
COPY tests tests

# Copy fonts and update font cache
COPY library/fonts/ /usr/share/fonts/
COPY library/notification/ /library/notification/
RUN fc-cache -fv

ENV PYTHONPATH='src'
ENV PORT=8080
EXPOSE $PORT

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]