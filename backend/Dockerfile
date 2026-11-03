# Orchestrator image. Talks to the host Docker daemon (socket mounted in
# docker-compose) to launch sandbox containers. Holds the Inference API key.
FROM python:3.11-slim

WORKDIR /srv

RUN pip install --no-cache-dir docker-cli || true
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
