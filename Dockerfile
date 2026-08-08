FROM python:3.13-alpine3.22

ARG BUILD_VERSION

LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="aarch64|amd64" \
      org.opencontainers.image.source="https://github.com/rkobrle-alt/price-watch"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "tzdata==2026.3"

COPY applications /app/applications
COPY core /app/core
COPY infrastructure /app/infrastructure

CMD ["python", "-m", "applications.homeassistant"]
