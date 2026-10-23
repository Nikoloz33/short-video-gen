# InstructVid: API + built web UI + render worker in one image.
#   docker build -t instructvid .
#   docker run -p 8000:8000 --env-file .env -v %APPDATA%\gcloud:/root/.config/gcloud:ro \
#     -v instructvid-data:/app/data instructvid
# Credentials: mount Application Default Credentials (above) or set GOOGLE_APPLICATION_CREDENTIALS
# to a mounted service-account key. Never bake credentials into the image.

FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
COPY video/package.json video/package.json
COPY web/package.json web/package.json
RUN npm ci
COPY video video
COPY web web
RUN npm run build -w web

FROM node:22-bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive \
    UV_PYTHON_PREFERENCE=only-managed \
    FFMPEG_DIR=/usr/bin \
    PYTHONUNBUFFERED=1
# ffmpeg for post-processing/validation, Chromium runtime libraries for Remotion's headless shell.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg ca-certificates curl libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 \
      libxkbcommon0 libxfixes3 libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 \
      libcairo2 libcups2 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY package.json package-lock.json ./
COPY video/package.json video/package.json
COPY web/package.json web/package.json
RUN npm ci --omit=dev -w video
COPY . .
COPY --from=web /app/web/dist web/dist
RUN uv sync --frozen --no-dev \
    && npx --yes remotion browser ensure --dir video || true

EXPOSE 8000
HEALTHCHECK CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uv", "run", "--no-dev", "uvicorn", "agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
