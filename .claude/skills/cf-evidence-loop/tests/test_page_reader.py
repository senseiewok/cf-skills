"""Tests for polite PageReader and evidence read-page command.

Validates all 8 lab network conduct rules with scripted fake sessions:
  R1: HTTPS only
  R2: robots.txt first with robots_allows RFC 9309 matching
  R3: Crawl-delay honoured
  R4: Refused or unreadable robots.txt (401, 403, 5xx, redirects, network failures) means no fetch
  R5: Redirects followed only within same site, HTTPS only, and target re-checked against robots.txt
  R6: Certificate verification strictly enabled (verify=True)
  R7: 5 MB cap on declared and streamed bodies
  R8: Single request for target, no retries
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from evidence.cli import main
from evidence.page_reader import (
    BodyTooLargeError,
    HTMLToTextParser,
    NonHttpsError,
    PageReader,
    PageReaderError,
    RedirectViolationError,
    RobotsRefusedError,
    extract_pdf_text,
    html_to_clean_text,
    same_site,
)


class ScriptedResponse:
    """Mock requests.Response for unit testing network conduct without sockets."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "https://example.org/page",
        encoding: str = "utf-8",
    ):
        self.status_code = status_code
        self.url = url
        self.encoding = encoding
        self.headers = headers or {}
        if content:
            self._content = content
        elif text:
            self._content = text.encode(encoding)
        else:
            self._content = b""
        self.text = self._content.decode(encoding, errors="replace")
        self.closed = False

    def iter_content(self, chunk_size: int = 65536):
        data = self._content
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def close(self):
        self.closed = True


class ScriptedSession:
    """Mock requests.Session recording every call, parameter, and verifying conduct."""

    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs):
        call_info = {"method": "GET", "url": url, "kwargs": kwargs}
        self.calls.append(call_info)
        if not self.responses:
            raise RuntimeError(f"ScriptedSession ran out of responses for {url}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ==============================================================================
# Helper / Unit Tests
# ==============================================================================

def test_same_site_apex_and_www():
    assert same_site("https://example.org/a", "https://example.org/b")
    assert same_site("https://www.example.org/a", "https://example.org/b")
    assert same_site("https://example.org/a", "https://www.example.org/b")
    assert not same_site("https://example.org/a", "https://other.org/b")
    assert not same_site("https://sub.example.org/a", "https://example.org/b")


def test_html_to_clean_text_strips_scripts_styles_and_extracts_links():
    html = """
    <html>
      <head><title>Test Terms</title><style>.hidden { display: none; }</style></head>
      <body>
        <h1>Terms of Use</h1>
        <script>alert('malicious script');</script>
        <p>Welcome to our <a href="/about">About Page</a> for research.</p>
        <div>
          <span>Line 1</span>
          <p>Line 2 with <a href="https://example.org/privacy">Privacy Policy</a></p>
        </div>
        <noscript>Turn on JS</noscript>
      </body>
    </html>
    """
    text, links = html_to_clean_text(html)
    assert "Terms of Use" in text
    assert "Welcome to our About Page for research." in text
    assert "alert" not in text
    assert "Turn on JS" not in text
    assert links == [("/about", "About Page"), ("https://example.org/privacy", "Privacy Policy")]


def test_extract_pdf_text_header_check():
    # Invalid PDF returns empty string
    assert extract_pdf_text(b"Not a PDF file content") == ""


# ==============================================================================
# Conduct Rule Tests
# ==============================================================================

def test_rule_1_https_only():
    reader = PageReader()
    with pytest.raises(NonHttpsError, match="HTTPS only"):
        reader.read_page("http://example.org/terms")

    with pytest.raises(NonHttpsError, match="HTTPS only"):
        reader.check_robots("ftp://example.org/robots.txt")


def test_rule_2_robots_txt_first_allowed():
    robots = "User-agent: *\nDisallow: /private/\nAllow: /terms\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<html><body>Valid Terms Content</body></html>", url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 2
    assert session.calls[0]["url"] == "https://example.org/robots.txt"
    assert session.calls[1]["url"] == "https://example.org/terms"
    assert result.robots_allowed is True
    assert result.status_code == 200
    assert "Valid Terms Content" in result.text


def test_rule_2_robots_txt_disallowed_aborts_without_fetching_page():
    robots = "User-agent: *\nDisallow: /secret-terms\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/secret-terms")

    # Only robots.txt was fetched; target page was never requested
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == "https://example.org/robots.txt"
    assert result.robots_allowed is False
    assert "disallowed" in (result.error or "").lower()
    assert result.text == ""


def test_rule_3_crawl_delay_honoured():
    robots = "User-agent: *\nCrawl-delay: 5\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<p>Page Content</p>", url="https://example.org/terms"),
    ])
    slept = []
    reader = PageReader(session=session, sleep_func=lambda s: slept.append(s))
    result = reader.read_page("https://example.org/terms")

    assert slept == [5.0]
    assert reader.last_delay_slept == 5.0
    assert result.crawl_delay == 5.0
    assert result.status_code == 200


@pytest.mark.parametrize("status_code", [401, 403, 500, 502, 503])
def test_rule_4_refused_or_server_error_robots_means_no_fetch(status_code):
    session = ScriptedSession([
        ScriptedResponse(status_code, text="Error", url="https://example.org/robots.txt"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 1
    assert result.robots_allowed is False
    assert result.status_code is None
    assert f"status {status_code}" in (result.error or "")


def test_rule_4_redirect_on_robots_txt_refused_no_fetch():
    session = ScriptedSession([
        ScriptedResponse(302, headers={"Location": "https://example.org/login"}, url="https://example.org/robots.txt"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    # Robots redirect is not followed; page is not fetched
    assert len(session.calls) == 1
    assert result.robots_allowed is False


def test_rule_4_transport_error_on_robots_txt_refused_no_fetch():
    session = ScriptedSession([
        requests.exceptions.ConnectTimeout("Connection timed out"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 1
    assert result.robots_allowed is False


def test_rule_4_rfc9309_404_or_410_robots_permits_fetch():
    session = ScriptedSession([
        ScriptedResponse(404, text="Not Found", url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<p>Public terms</p>", url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 2
    assert result.robots_allowed is True
    assert result.robots_status == 404
    assert result.status_code == 200
    assert "Public terms" in result.text


def test_rule_5_redirect_same_site_followed_and_rechecked():
    robots = "User-agent: *\nDisallow: /admin/\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(301, headers={"Location": "/new-terms"}, url="https://example.org/terms"),
        ScriptedResponse(200, text="<p>Updated Terms</p>", url="https://example.org/new-terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 3
    assert session.calls[1]["url"] == "https://example.org/terms"
    assert session.calls[2]["url"] == "https://example.org/new-terms"
    assert result.final_url == "https://example.org/new-terms"
    assert "Updated Terms" in result.text


def test_rule_5_redirect_off_site_refused():
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(302, headers={"Location": "https://external-tracker.com/landing"}, url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 2
    assert "redirect to another site not followed" in (result.error or "")


def test_rule_5_redirect_to_non_https_refused():
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(301, headers={"Location": "http://example.org/terms"}, url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert "redirect to non-HTTPS not followed" in (result.error or "")


def test_rule_5_redirect_disallowed_by_robots_recheck_refused():
    robots = "User-agent: *\nDisallow: /restricted/\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(302, headers={"Location": "https://example.org/restricted/doc"}, url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert len(session.calls) == 2  # Did not fetch the restricted target
    assert "redirect target disallowed by robots.txt" in (result.error or "")


def test_rule_6_certificate_checks_on():
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<p>Certified</p>", url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    reader.read_page("https://example.org/terms")

    for call in session.calls:
        assert call["kwargs"].get("verify") is True, f"Verify check missing on {call['url']}"


def test_rule_7_body_cap_declared_content_length():
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, headers={"Content-Length": "6000000"}, text="Oversized", url="https://example.org/huge"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/huge")

    assert "exceeds 5 MB cap" in (result.error or "")
    assert result.text == ""


def test_rule_7_body_cap_streamed_bytes():
    robots = "User-agent: *\nAllow: /\n"
    huge_bytes = b"X" * (5_000_001)
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, content=huge_bytes, url="https://example.org/huge"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/huge")

    assert "body exceeded 5000000 bytes cap" in (result.error or "")
    assert result.text == ""


def test_rule_8_single_request_no_retries():
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(500, text="Server Error", url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    # Exactly 1 robots.txt call and 1 page call; no retry loop
    assert len(session.calls) == 2
    assert result.status_code == 500
    assert result.error == "HTTP status 500"


# ==============================================================================
# CLI Integration Tests
# ==============================================================================

def test_cli_read_page_https_validation(capsys):
    rc = main(["read-page", "http://insecure.test/terms"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "refused: HTTPS only" in err


def test_cli_read_page_success(monkeypatch, capsys, tmp_path):
    robots = "User-agent: *\nAllow: /\n"
    fake_session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<h1>Terms Title</h1><p>Our terms paragraph.</p>", url="https://example.org/terms"),
    ])

    monkeypatch.setattr("evidence.page_reader.requests.Session", lambda: fake_session)

    out_file = tmp_path / "out.json"
    rc = main(["read-page", "https://example.org/terms", "--json", "--out", str(out_file)])
    assert rc == 0

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data["status_code"] == 200
    assert "Terms Title" in data["text"]
    assert "Our terms paragraph." in data["text"]
    assert out_file.exists()


def test_ssrf_guard_resolves_dns_and_blocks_internal_names_and_private_ips(monkeypatch):
    from evidence import page_reader
    from evidence.page_reader import PrivateHostError, is_forbidden_host, pdftotext_enabled

    # Internal hostnames refused by name before DNS lookup
    called = []
    monkeypatch.setattr(page_reader, "_resolve", lambda host, port: (called.append(host), ["1.1.1.1"])[1])
    for name in (
        "localhost",
        "sub.localhost",
        "metadata.google.internal",
        "service.internal",
        "printer.local",
        "router.home.arpa",
    ):
        assert is_forbidden_host(name) is True
    assert called == []

    # Literal private/loopback/link-local/multicast/reserved IPs refused without DNS
    for ip_lit in ("127.0.0.1", "[::1]", "10.0.0.1", "169.254.169.254", "192.168.1.1", "224.0.0.1", "240.0.0.1"):
        assert is_forbidden_host(ip_lit) is True

    # Hostname resolving to any non-public IP (even mixed with a public IP) is refused
    for bad_addrs in (
        ["127.0.0.1"],
        ["10.0.0.5"],
        ["169.254.169.254"],
        ["::ffff:169.254.169.254"],
        ["224.0.0.1"],
        ["240.0.0.1"],
        ["1.1.1.1", "10.0.0.1"],
        [],
    ):
        monkeypatch.setattr(page_reader, "_resolve", lambda host, port, addrs=bad_addrs: addrs)
        assert is_forbidden_host("rebind.example.org") is True

    # DNS failure is refused
    def _raise_dns(host, port):
        raise OSError("NXDOMAIN")

    monkeypatch.setattr(page_reader, "_resolve", _raise_dns)
    assert is_forbidden_host("unresolvable.example.org") is True

    # Redirect hop re-resolves and refuses when DNS flips to private IP
    answers = [["1.1.1.1"], ["1.1.1.1"], ["169.254.169.254"]]
    monkeypatch.setattr(page_reader, "_resolve", lambda host, port: answers.pop(0))
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(302, headers={"Location": "https://example.org/step2"}, url="https://example.org/terms"),
    ])
    with pytest.raises(PrivateHostError, match="redirect to private or loopback host"):
        PageReader(session=session).read_page("https://example.org/terms")

    # pdftotext CLI fallback is opt-in via EVIDENCE_ALLOW_PDFTOTEXT
    monkeypatch.delenv("EVIDENCE_ALLOW_PDFTOTEXT", raising=False)
    assert pdftotext_enabled() is False
    monkeypatch.setenv("EVIDENCE_ALLOW_PDFTOTEXT", "0")
    assert pdftotext_enabled() is False
    monkeypatch.setenv("EVIDENCE_ALLOW_PDFTOTEXT", "1")
    assert pdftotext_enabled() is True

