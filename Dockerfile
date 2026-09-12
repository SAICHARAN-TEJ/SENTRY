FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Rasterio wheels include GDAL for the supported Python versions. Keep the
# image deliberately CPU-safe; GPU deployments can extend it with CUDA/PyTorch.
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY worker ./worker
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY pyproject.toml README.md ./

RUN mkdir -p /app/data/artifacts
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
