ARG PYTHON_IMAGE=python:3.12-slim
ARG FRONTEND_IMAGE=node:22-alpine
FROM ${FRONTEND_IMAGE} AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt
COPY app ./app
COPY web ./web
COPY --from=frontend-build /web/dist ./web/dist
RUN mkdir -p /app/data/artifacts

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
