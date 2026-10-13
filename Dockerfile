# ---- Builder: Debian 12, same Python (3.11.2) as distroless python3-debian12 ----
FROM debian:12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && /opt/venv/bin/pip check

# ---- Runtime stage: distroless ----
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

COPY --from=builder /opt/venv/lib/python3.11/site-packages /app/deps
COPY --chown=nonroot:nonroot . .

ENV PYTHONPATH=/app/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# # ---- Builder stage ----
# FROM python:3.11-slim AS builder

# WORKDIR /app

# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc \
#     && rm -rf /var/lib/apt/lists/*

# COPY requirements.txt .
# RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# # ---- Runtime stage: distroless ----
# FROM gcr.io/distroless/python3-debian12:nonroot

# WORKDIR /app

# COPY --from=builder /deps /app/deps
# COPY --chown=nonroot:nonroot . .

# ENV PYTHONPATH=/app/deps \
#     PYTHONUNBUFFERED=1 \
#     PYTHONDONTWRITEBYTECODE=1

# EXPOSE 8000

# ENTRYPOINT ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]