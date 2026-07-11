"""
SSRF guards for LLM provider Base URL validation.

validate_provider_url / validate_resolved_host must reject loopback, private,
link-local (incl. cloud metadata 169.254.169.254), reserved, and multicast
targets for every DNS result (IPv4 + IPv6). DNS failure must hard-fail.
"""

from __future__ import annotations

import socket

import pytest

import app as app_module
from app import validate_provider_url, validate_resolved_host


def _assert_rejected(url: str):
    errors = validate_provider_url(url)
    assert errors, f"expected SSRF rejection for {url!r}, got no errors"
    # Must not be only a format/scheme complaint when host is well-formed http(s)
    joined = " ".join(errors)
    assert (
        "内网" in joined
        or "本机" in joined
        or "链路本地" in joined
        or "保留" in joined
        or "无法解析" in joined
    ), f"unexpected error text for {url!r}: {errors}"


def _assert_allowed(url: str):
    errors = validate_provider_url(url)
    assert errors == [], f"expected allow for {url!r}, got: {errors}"


class TestValidateProviderUrlSsrf:
    def test_rejects_localhost(self):
        _assert_rejected("http://localhost/v1")
        _assert_rejected("https://localhost:443/v1/chat/completions")

    def test_rejects_127_0_0_1(self):
        _assert_rejected("http://127.0.0.1/v1")
        _assert_rejected("https://127.0.0.1:8443/chat/completions")

    def test_rejects_rfc1918_private(self):
        _assert_rejected("http://10.0.0.1/v1")
        _assert_rejected("https://192.168.1.50/v1")
        _assert_rejected("http://172.16.0.5/v1")

    def test_rejects_cloud_metadata_link_local(self):
        # 169.254.169.254 is link-local (and private); no hard-coded list needed
        _assert_rejected("http://169.254.169.254/latest/meta-data/")
        _assert_rejected("https://169.254.169.254/v1")

    def test_rejects_ipv6_loopback(self):
        _assert_rejected("http://[::1]/v1")

    def test_allows_public_ip_literal(self):
        # 8.8.8.8 is a public address — SSRF check should pass (connectivity not required)
        _assert_allowed("https://8.8.8.8/v1")

    def test_allows_public_api_hostname(self, monkeypatch):
        """
        api.openai.com should pass when all resolved A/AAAA records are public.
        Monkeypatch DNS so the test is deterministic offline / in CI.
        """

        def fake_getaddrinfo(host, port, *args, **kwargs):
            assert host == "api.openai.com"
            # Two public IPv4 results — both must be inspected; none blocked
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.1.1", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.2.2", 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        _assert_allowed("https://api.openai.com/v1")
        _assert_allowed("https://api.openai.com/v1/chat/completions")

    def test_rejects_if_any_resolved_ip_is_private(self, monkeypatch):
        """Even one private A/AAAA among several public results must reject the URL."""

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        _assert_rejected("https://evil.example/v1")

    def test_dns_failure_is_hard_error(self, monkeypatch):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        errors = validate_provider_url("https://does-not-resolve.invalid/v1")
        assert errors
        assert any("无法解析" in e for e in errors)

    def test_empty_dns_result_is_hard_error(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
        errors = validate_resolved_host("empty-results.example")
        assert errors
        assert any("无法解析" in e or "空结果" in e for e in errors)


class TestRequestTimeRevalidation:
    """parse_with_llm already re-calls validate_provider_url; cover test_llm_connection."""

    def test_test_llm_connection_rejects_private_before_request(self, monkeypatch):
        """
        Private Base URL must fail at test_llm_connection without opening a socket
        to the target (DNS rebinding defense at request time).
        """
        opened = {"called": False}

        def boom(*args, **kwargs):
            opened["called"] = True
            raise AssertionError("urlopen must not be called for blocked URL")

        monkeypatch.setattr("urllib.request.urlopen", boom)

        settings = {
            "api_key": "sk-test",
            "base_url": "http://127.0.0.1/v1",
            "model": "gpt-test",
            "parsed_params": {},
        }
        result, errors = app_module.test_llm_connection(settings)
        assert result is None
        assert errors
        assert any("内网" in e or "本机" in e for e in errors)
        assert opened["called"] is False

    def test_test_llm_connection_rechecks_dns(self, monkeypatch):
        """
        If DNS flips to a private IP after settings were saved, request-time
        revalidation must still reject.
        """

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
            ]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        def boom(*args, **kwargs):
            raise AssertionError("urlopen must not be called")

        monkeypatch.setattr("urllib.request.urlopen", boom)

        settings = {
            "api_key": "sk-test",
            "base_url": "https://looks-public.example/v1",
            "model": "gpt-test",
            "parsed_params": {},
        }
        result, errors = app_module.test_llm_connection(settings)
        assert result is None
        assert errors
        assert any("169.254.169.254" in e or "链路本地" in e or "内网" in e for e in errors)
