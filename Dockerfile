# Google Analytics MCP (official analytics-mcp) behind a shared-secret gateway.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY ga_mcp_gateway ./ga_mcp_gateway

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8080

# --no-access-log keeps the ?key= secret out of the container's own logs.
CMD ["sh", "-c", "exec uvicorn ga_mcp_gateway.app:app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers"]
