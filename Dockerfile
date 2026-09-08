FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
COPY uv.lock ./ 

RUN pip install --no-cache-dir uv

RUN uv pip install --system -r requirements.txt

COPY src/ ./src/
COPY models/ ./models/
COPY data/ ./data/

RUN useradd -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.models.main_api:app", "--host", "0.0.0.0", "--port", "8000"]