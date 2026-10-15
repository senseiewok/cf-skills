#!/usr/bin/env python3
"""Launcher for reading one HTTPS web page or PDF under lab conduct rules.

Usage:
    python scripts/read_page.py https://example.org/terms [--out file] [--json]

This tool exists for human-started reading of terms pages before a catalog entry exists,
not for bulk automated data collection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence.cli import main  # noqa: E402

if __name__ == "__main__":
    argv = ["read-page"] + sys.argv[1:]
    raise SystemExit(main(argv))
