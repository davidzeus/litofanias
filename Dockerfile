FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema mínimas (Pillow las necesita para algunos formatos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY static/ ./static/

EXPOSE 8000

# --workers puede subirse si el servidor tiene varios núcleos disponibles
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
