import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# A public address from Cloudflare's resolver range: the SSRF guard accepts it, and no test ever opens DNS.
FAKE_PUBLIC_ADDRESS = "1.1.1.1"


@pytest.fixture(autouse=True)
def _offline_dns(monkeypatch):
    """page_reader resolves host names before fetching (SSRF guard). Tests never touch real DNS:
    every name resolves to one public address unless a test replaces page_reader._resolve itself."""
    from evidence import page_reader

    monkeypatch.setattr(page_reader, "_resolve", lambda host, port: [FAKE_PUBLIC_ADDRESS])


@pytest.fixture(autouse=True)
def _scite_usage_ledgers(monkeypatch, tmp_path):
    """The Scite quota caps need a usage ledger (no default path exists). Each test gets fresh, empty ledgers
    in its own temporary folder, unless it sets the variables itself."""
    monkeypatch.setenv("SCITE_MCP_USAGE_LOG", str(tmp_path / "scite_mcp_usage.jsonl"))
    monkeypatch.setenv("SCITE_REST_USAGE_LOG", str(tmp_path / "scite_rest_usage.jsonl"))
    monkeypatch.delenv("SCITE_MCP_OAUTH_FILE", raising=False)
