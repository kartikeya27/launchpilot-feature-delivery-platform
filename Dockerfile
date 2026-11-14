FROM node:22-alpine AS frontend
WORKDIR /work/frontend
ARG VITE_AUTH_MODE=demo
ARG VITE_OIDC_AUTHORITY
ARG VITE_OIDC_CLIENT_ID=launchpilot-web
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
# Install patched Debian packages available at image build time.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /work
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATABASE_URL=sqlite:////data/launchpilot.db
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && mkdir -p /data
COPY backend/app ./backend/app
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/migrations ./backend/migrations
COPY --from=frontend /work/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /data /work
USER appuser
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
