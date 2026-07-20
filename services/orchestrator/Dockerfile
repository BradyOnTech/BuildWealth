FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl nodejs npm \
  && npm install -g @openai/codex@0.142.5 \
  && npm cache clean --force \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 8090

CMD ["uvicorn", "buildwealth_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8090"]
