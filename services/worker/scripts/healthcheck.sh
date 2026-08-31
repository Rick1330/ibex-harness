#!/usr/bin/env sh
# Docker HEALTHCHECK — Celery worker liveness via inspect ping to this container's nodename.
set -eu

NODE="ibex-worker@$(hostname)"
celery -A app.celery_app:celery_app inspect ping -d "$NODE" --timeout=5 2>/dev/null | grep -q OK
