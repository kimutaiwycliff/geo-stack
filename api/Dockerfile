# Production multi-stage build.
# Stage 1 (builder): install Python deps.
# Stage 2 (runtime): slim image with only what's needed to run.

FROM python:3.12-slim AS builder
WORKDIR /build

# Install build dependencies for packages with C extensions (asyncpg, shapely)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime
WORKDIR /app

# Runtime system deps: libpq for asyncpg, gdal-bin for ogr2ogr/ogrinfo (server-side ingest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Non-root user for production security
RUN useradd -m -u 1001 geoapi && chown -R geoapi:geoapi /app
USER geoapi

# Pre-install DuckDB extensions at build time so startup has no network dependency.
# Extensions land in /home/geoapi/.duckdb/extensions/ and are baked into the image.
RUN python -c "\
import duckdb; \
c = duckdb.connect(':memory:'); \
c.execute('INSTALL spatial'); \
c.execute('INSTALL httpfs'); \
c.close() \
"

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
