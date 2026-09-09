"""Unit tests for request_id logging helpers."""

from __future__ import annotations

import logging

from app.logutil import RequestIdLogFilter, install_request_id_log_filter, request_id_for_log
from app.reqid import set_current


def test_request_id_for_log_uses_context() -> None:
    set_current("11111111-1111-4111-8111-111111111111")
    assert request_id_for_log() == "11111111-1111-4111-8111-111111111111"


def test_request_id_log_filter_attaches_attribute(caplog) -> None:
    set_current("22222222-2222-4222-8222-222222222222")
    log = logging.getLogger("app.test_logutil")
    install_request_id_log_filter(log)
    install_request_id_log_filter(log)  # idempotent
    with caplog.at_level(logging.INFO, logger="app.test_logutil"):
        log.info("hello request_id=%s", request_id_for_log())
    assert "request_id=22222222-2222-4222-8222-222222222222" in caplog.text
    assert isinstance(log.filters[0], RequestIdLogFilter)
    assert caplog.records[-1].request_id == "22222222-2222-4222-8222-222222222222"
