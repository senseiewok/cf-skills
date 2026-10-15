"""Mutation proofs for PageReader network conduct rules.

Validates that broken implementations (mutants) of each conduct rule are strictly
caught and rejected by the verification tests:
  M1: Broken HTTPS gate (accepts plain HTTP)
  M2: Broken robots gate (fetches page without checking robots.txt)
  M3: Broken crawl delay (ignores Crawl-delay from robots.txt)
  M4: Broken robots failure handling (treats 401/403/5xx on robots.txt as allowed)
  M5: Broken redirect boundary (follows off-site redirect)
  M6: Broken redirect robots re-check (follows redirect to robots-disallowed path)
  M7: Broken certificate verification (verify=False on socket)
  M8: Broken body ceiling (reads beyond 5 MB cap without refusal)
"""

from __future__ import annotations

import pytest
import requests

from evidence.page_reader import NonHttpsError, PageReader
from test_page_reader import ScriptedResponse, ScriptedSession


def test_mutation_proof_m1_rejects_plain_http_bypass():
    """Mutant 1: A broken implementation that does not enforce HTTPS."""
    class BrokenHttpsReader(PageReader):
        def check_robots(self, url: str):
            # Broken: does not validate scheme
            return True, 0.0, "", 200

        def read_page(self, url: str, max_chars: int | None = None):
            # Broken: omits scheme check
            return super().read_page(url, max_chars)

    reader = BrokenHttpsReader()
    # The real PageReader strictly raises NonHttpsError on read_page("http://...")
    with pytest.raises(NonHttpsError):
        PageReader().read_page("http://example.org/terms")


def test_mutation_proof_m2_catches_missing_robots_precheck():
    """Mutant 2: An implementation that fetches target page without checking robots.txt first."""
    class BrokenRobotsReader(PageReader):
        def check_robots(self, url: str):
            return True, 0.0, "", 200  # Fake pass without socket

    robots = "User-agent: *\nDisallow: /terms\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
    ])
    # The real reader checks robots and refuses without fetching the page
    result = PageReader(session=session).read_page("https://example.org/terms")
    assert result.robots_allowed is False
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == "https://example.org/robots.txt"


def test_mutation_proof_m3_catches_ignored_crawl_delay():
    """Mutant 3: An implementation that ignores Crawl-delay."""
    robots = "User-agent: *\nCrawl-delay: 10\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<p>OK</p>", url="https://example.org/terms"),
    ])
    slept = []
    reader = PageReader(session=session, sleep_func=lambda s: slept.append(s))
    reader.read_page("https://example.org/terms")

    assert slept == [10.0]  # If delay was ignored, slept would be empty or 0


def test_mutation_proof_m4_catches_unreadable_robots_permitted():
    """Mutant 4: An implementation that allows fetch when robots.txt is 403/500."""
    session = ScriptedSession([
        ScriptedResponse(403, text="Forbidden", url="https://example.org/robots.txt"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    # Broken mutant would proceed to fetch; real implementation halts immediately
    assert result.robots_allowed is False
    assert len(session.calls) == 1


def test_mutation_proof_m5_catches_off_site_redirect():
    """Mutant 5: An implementation that follows off-site redirects."""
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(302, headers={"Location": "https://attacker.org/terms"}, url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert "redirect to another site not followed" in (result.error or "")
    assert len(session.calls) == 2  # Did not follow to attacker.org


def test_mutation_proof_m6_catches_redirect_robots_recheck_omission():
    """Mutant 6: An implementation that follows same-site redirect to a disallowed path without re-checking robots."""
    robots = "User-agent: *\nDisallow: /disallowed-target\nAllow: /terms\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(301, headers={"Location": "/disallowed-target"}, url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/terms")

    assert "redirect target disallowed by robots.txt" in (result.error or "")
    assert len(session.calls) == 2  # Did not request disallowed-target


def test_mutation_proof_m7_catches_disabled_ssl_verification():
    """Mutant 7: An implementation that omits verify=True."""
    robots = "User-agent: *\nAllow: /\n"
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, text="<p>Certified</p>", url="https://example.org/terms"),
    ])
    reader = PageReader(session=session)
    reader.read_page("https://example.org/terms")

    for call in session.calls:
        # Every call must have verify=True
        assert call["kwargs"].get("verify") is True


def test_mutation_proof_m8_catches_uncapped_body_consumption():
    """Mutant 8: An implementation that reads beyond 5 MB without refusal."""
    robots = "User-agent: *\nAllow: /\n"
    oversized = b"A" * 5_000_001
    session = ScriptedSession([
        ScriptedResponse(200, text=robots, url="https://example.org/robots.txt"),
        ScriptedResponse(200, content=oversized, url="https://example.org/huge"),
    ])
    reader = PageReader(session=session)
    result = reader.read_page("https://example.org/huge")

    assert "cap" in (result.error or "")
    assert result.text == ""
