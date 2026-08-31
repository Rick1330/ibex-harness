#!/usr/bin/env sh
# Docker HEALTHCHECK — Celery worker liveness via inspect ping.
set -eu

celery -A app.celery_app:celery_app inspect ping --timeout=5 2>/dev/null | grep -q OK
