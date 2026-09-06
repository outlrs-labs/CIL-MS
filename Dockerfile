FROM node:22-bookworm-slim AS workbench-build
WORKDIR /build/workbench
COPY data-formulator-main/package.json data-formulator-main/package-lock.json ./
RUN npm ci
COPY data-formulator-main/ ./
RUN npm run build

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM scratch AS frontend-export
COPY --from=frontend-build /build/frontend/dist/ /

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/cil/backend:/opt/cil/integration
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgl1 libglib2.0-0 libgomp1 tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/cil
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY data-formulator-main/requirements.txt /tmp/workbench-requirements.txt
COPY data-formulator-main/pyproject.toml data-formulator-main/README.md /opt/cil/data-formulator-main/
COPY data-formulator-main/py-src/ /opt/cil/data-formulator-main/py-src/
RUN python -m pip install --no-cache-dir -r /tmp/backend-requirements.txt \
    && cd /opt/cil/data-formulator-main \
    && python -m pip install --no-cache-dir -r /tmp/workbench-requirements.txt
COPY --from=workbench-build /build/workbench/py-src/data_formulator/dist/ /opt/cil/data-formulator-main/py-src/data_formulator/dist/
COPY backend/ /opt/cil/backend/
COPY integration/ /opt/cil/integration/
COPY scripts/ /opt/cil/scripts/
COPY report_templates/ /opt/cil/report_templates/
RUN mkdir -p /srv/cil-data/cil /srv/cil-processing
EXPOSE 8000 5567
