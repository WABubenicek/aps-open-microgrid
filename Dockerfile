# APS Open Microgrid hosted API + MCP. Public config only; private config is never copied.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/engine:/app/service
WORKDIR /app
COPY service/requirements.txt service/requirements.txt
RUN pip install --no-cache-dir -r service/requirements.txt
COPY aps-config.v0.1.json ./
COPY engine/aps_engine engine/aps_engine
COPY service/app.py service/app.py
RUN test ! -e /app/aps-config.private.json
USER nobody
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'
