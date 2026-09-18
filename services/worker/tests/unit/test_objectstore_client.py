"""Unit tests for S3-compatible objectstore_client helpers."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app import objectstore_client as osc


def _clear_s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "S3_ENDPOINT",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_BUCKET_SESSIONS",
        "S3_REGION",
        "S3_MASTER_KEY_B64",
        "OBJECTSTORE_MASTER_KEY_B64",
        "S3_ENCRYPTION_KEY_ID",
        "S3_ALLOW_INSECURE_HTTP",
    ):
        monkeypatch.delenv(key, raising=False)


def _allow_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ALLOW_INSECURE_HTTP", "1")


def test_cfg_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://minio:9000/")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET_SESSIONS", "sessions")
    monkeypatch.setenv("S3_REGION", "eu-west-1")
    monkeypatch.setenv("S3_MASTER_KEY_B64", "mk")
    monkeypatch.setenv("S3_ENCRYPTION_KEY_ID", "v2")
    cfg = osc._cfg()
    assert cfg["endpoint"] == "http://minio:9000"
    assert cfg["access_key"] == "ak"
    assert cfg["secret_key"] == "sk"
    assert cfg["bucket"] == "sessions"
    assert cfg["region"] == "eu-west-1"
    assert cfg["master_key_b64"] == "mk"
    assert cfg["key_id"] == "v2"


def test_cfg_from_settings_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://env:9000")
    settings = SimpleNamespace(
        s3_endpoint="http://settings:9000/",
        s3_access_key="sak",
        s3_secret_key=SimpleNamespace(get_secret_value=lambda: "ssk"),
        s3_bucket_sessions="sb",
        s3_region="us-west-2",
        s3_master_key_b64="smk",
        s3_encryption_key_id="v9",
    )
    cfg = osc._cfg(settings)
    assert cfg["endpoint"] == "http://settings:9000"
    assert cfg["access_key"] == "sak"
    assert cfg["secret_key"] == "ssk"
    assert cfg["bucket"] == "sb"
    assert cfg["region"] == "us-west-2"
    assert cfg["master_key_b64"] == "smk"
    assert cfg["key_id"] == "v9"


def test_cfg_empty_secretstr_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty SecretStr must not block env fallback (str(SecretStr('')) is truthy)."""
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://env:9000")
    monkeypatch.setenv("S3_SECRET_KEY", "from-env")
    from pydantic import SecretStr

    settings = SimpleNamespace(
        s3_endpoint=SecretStr(""),
        s3_access_key=None,
        s3_secret_key=SecretStr(""),
        s3_bucket_sessions=None,
        s3_region=None,
        s3_master_key_b64=None,
        s3_encryption_key_id=None,
    )
    cfg = osc._cfg(settings)
    assert cfg["endpoint"] == "http://env:9000"
    assert cfg["secret_key"] == "from-env"


def test_cfg_defaults_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    cfg = osc._cfg()
    assert cfg["endpoint"] == ""
    assert cfg["bucket"] == "ibex-sessions"
    assert cfg["region"] == "us-east-1"
    assert cfg["key_id"] == "v1"


def test_delete_org_prefix_raises_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    with pytest.raises(RuntimeError, match="S3_ENDPOINT unset"):
        osc.delete_org_prefix("org-1")


def test_delete_uri_unsupported() -> None:
    with pytest.raises(ValueError, match="unsupported uri"):
        osc.delete_uri("https://example/x")


def test_delete_uri_malformed() -> None:
    with pytest.raises(ValueError, match="malformed uri"):
        osc.delete_uri("s3://nobucket")


def test_delete_uri_empty_key() -> None:
    with pytest.raises(ValueError, match="empty object key"):
        osc.delete_uri("s3://ibex-sessions/")


def test_delete_uri_bucket_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    _allow_http(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_BUCKET_SESSIONS", "ibex-sessions")
    with pytest.raises(ValueError, match="bucket mismatch"):
        osc.delete_uri("s3://other-bucket/key")


def test_delete_uri_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    _allow_http(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET_SESSIONS", "ibex-sessions")
    mock_resp = MagicMock(status_code=204)
    with patch.object(osc.httpx, "request", return_value=mock_resp) as req:
        osc.delete_uri("s3://ibex-sessions/org/a.json")
    assert req.called
    assert req.call_args.args[0] == "DELETE"


def test_put_encrypted_json_seals_and_puts(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    _allow_http(monkeypatch)
    master = secrets_key_b64()
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET_SESSIONS", "ibex-sessions")
    monkeypatch.setenv("S3_MASTER_KEY_B64", master)
    mock_resp = MagicMock(status_code=200)
    with patch.object(osc.httpx, "request", return_value=mock_resp) as req:
        uri = osc.put_encrypted_json("org/blob.json", b'{"x":1}')
    assert uri == "s3://ibex-sessions/org/blob.json"
    assert req.call_args.args[0] == "PUT"
    body = req.call_args.kwargs["content"]
    envelope = json.loads(body)
    assert "ciphertext_b64" in envelope
    assert "wrapped_dek_b64" in envelope
    assert envelope["key_id"] == "v1"


def secrets_key_b64() -> str:
    return base64.b64encode(b"0" * 32).decode()


def test_parse_list_xml_not_truncated() -> None:
    xml = "<ListBucketResult><Key>a</Key><Key>b/c</Key><IsTruncated>false</IsTruncated></ListBucketResult>"
    keys, cont = osc._parse_list_xml(xml)
    assert keys == ["a", "b/c"]
    assert cont == ""


def test_parse_list_xml_truncated_with_continuation() -> None:
    xml = (
        "<ListBucketResult><Key>k1</Key><IsTruncated>true</IsTruncated>"
        "<NextContinuationToken>tok-99</NextContinuationToken></ListBucketResult>"
    )
    keys, cont = osc._parse_list_xml(xml)
    assert keys == ["k1"]
    assert cont == "tok-99"


def test_parse_list_xml_truncated_missing_token() -> None:
    xml = "<ListBucketResult><Key>k</Key><IsTruncated>true</IsTruncated></ListBucketResult>"
    with pytest.raises(RuntimeError, match="NextContinuationToken"):
        osc._parse_list_xml(xml)


def test_extract_xml_keys_unescapes_entities() -> None:
    xml = "<ListBucketResult><Key>a&amp;b</Key><IsTruncated>false</IsTruncated></ListBucketResult>"
    keys, cont = osc._parse_list_xml(xml)
    assert keys == ["a&b"]
    assert cont == ""


def test_canonical_query_sorts_and_escapes_slash() -> None:
    q = osc._canonical_query({"prefix": "a/b", "list-type": "2"})
    assert q == "list-type=2&prefix=a%2Fb"


def test_require_endpoint_rejects_http_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.delenv("S3_ALLOW_INSECURE_HTTP", raising=False)
    cfg = _s3_cfg("http://minio.example:9000")
    with pytest.raises(RuntimeError, match="HTTPS"):
        osc._require_endpoint(cfg)


@pytest.mark.parametrize(
    ("endpoint", "allow_insecure", "via_settings"),
    [
        ("http://127.0.0.1:9000", True, False),
        ("http://127.0.0.1:9000", False, False),
        ("http://127.0.0.1:9000", False, True),
    ],
)
def test_require_endpoint_allows_loopback_or_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    allow_insecure: bool,
    via_settings: bool,
) -> None:
    _clear_s3_env(monkeypatch)
    if allow_insecure:
        monkeypatch.setenv("S3_ALLOW_INSECURE_HTTP", "1")
    else:
        monkeypatch.delenv("S3_ALLOW_INSECURE_HTTP", raising=False)
    if via_settings:
        from app.config import Settings

        settings = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            s3_endpoint=endpoint,
        )
        assert settings.s3_endpoint == endpoint
        cfg = osc._load_cfg(settings)
    else:
        cfg = _s3_cfg(endpoint)
    osc._require_endpoint(cfg)


def _s3_cfg(endpoint: str) -> osc._S3Cfg:
    return osc._S3Cfg(
        endpoint=endpoint,
        access_key="ak",
        secret_key="sk",
        bucket="b",
        region="us-east-1",
        master_key_b64="",
        key_id="v1",
    )


def test_extract_xml_keys_unterminated_raises() -> None:
    xml = "<ListBucketResult><Key>partial-only"
    with pytest.raises(RuntimeError, match="unterminated"):
        osc._extract_xml_keys(xml)


def test_secret_key_preserves_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("S3_SECRET_KEY", "sk/")
    cfg = osc._cfg()
    assert cfg["secret_key"] == "sk/"


def test_put_rejects_failed_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    master = secrets_key_b64()
    monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
    monkeypatch.setenv("S3_ALLOW_INSECURE_HTTP", "1")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_MASTER_KEY_B64", master)
    mock_resp = MagicMock(status_code=403)
    with (
        patch.object(osc.httpx, "request", return_value=mock_resp),
        pytest.raises(RuntimeError, match="s3 put"),
    ):
        osc.put_encrypted_json("org/blob.json", b'{"x":1}')


def test_escape_key_path() -> None:
    assert osc._escape_key_path("a/b c/d") == "a/b%20c/d"
    assert osc._escape_key_path("/leading") == "leading"
    assert osc._escape_key_path("plain") == "plain"


def test_parse_master_key_missing() -> None:
    with pytest.raises(RuntimeError, match="required"):
        osc._parse_master_key("")


def test_parse_master_key_wrong_length() -> None:
    short = base64.b64encode(b"short").decode()
    with pytest.raises(RuntimeError, match="32 bytes"):
        osc._parse_master_key(short)


def test_parse_master_key_invalid_encoding() -> None:
    with (
        pytest.raises(RuntimeError, match="invalid master key encoding"),
        patch.object(osc.base64, "b64decode", side_effect=ValueError("bad")),
    ):
        osc._parse_master_key("!!!!")


def test_delete_org_prefix_lists_and_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_s3_env(monkeypatch)
    _allow_http(monkeypatch)
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    list_xml = (
        "<ListBucketResult><Key>org-1/a</Key><Key>org-1/b</Key>"
        "<IsTruncated>false</IsTruncated></ListBucketResult>"
    )
    list_resp = MagicMock(status_code=200, text=list_xml)
    del_resp = MagicMock(status_code=204)

    def _request(method, url, **kwargs):
        del kwargs
        if method == "GET":
            return list_resp
        return del_resp

    with patch.object(osc.httpx, "request", side_effect=_request) as req:
        osc.delete_org_prefix("org-1")
    methods = [c.args[0] for c in req.call_args_list]
    assert methods[0] == "GET"
    assert methods.count("DELETE") == 2
