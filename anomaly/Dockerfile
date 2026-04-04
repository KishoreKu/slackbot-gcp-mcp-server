FROM python:3.12-slim

RUN useradd -m -u 1000 anomaly

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV GCP_PROJECT_ID=slb-ai-agent-prod
ENV GCP_REGION=us-central1

USER anomaly

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]