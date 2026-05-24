# Azure Cost Optimization Advisor — Python 3.11 slim
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim-bookworm

LABEL maintainer="finops-team@example.com"
LABEL description="AI-Powered Azure Cost Optimization Advisor — Streamlit Dashboard"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATA_RAW_DIR=/app/data/raw \
    DATA_PROCESSED_DIR=/app/data/processed \
    DATA_EMBEDDINGS_DIR=/app/data/embeddings \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

COPY --from=builder /install /usr/local
COPY requirements.txt .
COPY src/ ./src/
COPY data/ ./data/
COPY .env.example .env.example

RUN mkdir -p data/raw data/processed data/embeddings/faiss_index \
    && useradd --create-home --shell /bin/bash --uid 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "src/dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
