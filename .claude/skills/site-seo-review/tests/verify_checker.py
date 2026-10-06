"""Run the whole test suite against one checker and print a short verdict. Usage:

    python tests/verify_checker.py <candidate seo_audit.py>

Runs test_seo_audit.py and test_seo_audit_extra.py against the candidate (SEO_AUDIT_PATH is set here) and prints:
  FAIL <Class.test_name>: <first line of the failure>      one per failing test, at most 12, foundations first
  PASS n tests (n / n passed)                              only when every test passed; exit 0
  FAILED k of n tests (n-k / n passed)                     otherwise; exit 1
Exit 2 for a usage error. A candidate that does not compile gets one FAIL line and exit 1.

Useful when someone (or some model) writes or changes a checker: the tests decide, not the author's own claim.
Optional: SEO_VERIFY_CLASSES=TestGoodSite,TestInterface runs only those test classes (a pass on a subset is a
milestone, never acceptance). A checker that prints zero findings must fail this script; try it once to see.
"""
import io
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_LINES = 12
MODULES = ["test_seo_audit", "test_seo_audit_extra"]
# The order to fix things in: if the good site fails, every other failure is noise.
ORDER = ["TestGoodSite", "TestInterface", "TestPageMetadata", "TestPageContent", "TestSiteLevel", "TestRobustness",
         "TestSideEffects", "TestAddresses", "TestCanonicalWithoutBase", "TestOddFiles", "TestNotFoundPage", "TestParsing", "TestStructuredData",
         "TestSitemapExtra", "TestRobotsExtra"]


def first_line(traceback_text):
    """The exception line of a unittest traceback: the first unindented line after the header."""
    lines = traceback_text.splitlines()
    for ln in lines[1:]:
        if ln and not ln.startswith((" ", "\t", "Traceback")):
            return ln.strip()[:300]
    return (lines[-1].strip() if lines else "no message")[:300]


def short_name(test):
    tid = test.id()
    parts = tid.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else tid


def rank(name):
    cls = name.split(".")[0]
    return (ORDER.index(cls) if cls in ORDER else len(ORDER), name)


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if len(argv) != 2:
        print("usage: python verify_checker.py <candidate seo_audit.py>")
        return 2
    cand = Path(argv[1]).resolve()
    if not cand.is_file():
        print(f"FAIL candidate not found: {cand.name}")
        print("FAILED 1 of 1 tests (0 / 1 passed)")
        return 1

    compiled = subprocess.run([sys.executable, "-m", "py_compile", str(cand)], capture_output=True, text=True)
    if compiled.returncode != 0:
        msgs = [ln for ln in (compiled.stderr + compiled.stdout).splitlines() if ln.strip()]
        where = next((m.group(0) for ln in msgs for m in [re.search(r"line \d+", ln)] if m), "")
        last = msgs[-1].strip() if msgs else "syntax error"
        print(f"FAIL does not compile: {last} ({where})" if where else f"FAIL does not compile: {last}")
        print("FAILED 1 of 1 tests (0 / 1 passed)")
        return 1

    os.environ["SEO_AUDIT_PATH"] = str(cand)
    sys.path.insert(0, str(HERE))
    modules = [__import__(name) for name in MODULES]  # each reads SEO_AUDIT_PATH at import

    loader = unittest.defaultTestLoader
    only = [c.strip() for c in os.environ.get("SEO_VERIFY_CLASSES", "").split(",") if c.strip()]
    suite = unittest.TestSuite()
    if only:
        for name in only:
            cls = next((getattr(m, name) for m in modules if hasattr(m, name)), None)
            if cls is None:
                print(f"usage: unknown test class {name}")
                return 2
            suite.addTests(loader.loadTestsFromTestCase(cls))
    else:
        for m in modules:
            suite.addTests(loader.loadTestsFromModule(m))

    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)

    problems = [(short_name(t), first_line(tb)) for t, tb in result.errors + result.failures]
    problems.sort(key=lambda p: rank(p[0]))
    for name, msg in problems[:MAX_LINES]:
        print(f"FAIL {name}: {msg}")
    if len(problems) > MAX_LINES:
        print(f"({len(problems) - MAX_LINES} more failing tests not shown)")

    total = result.testsRun
    failed = len(problems)
    n_skip = len(result.skipped)
    skipped = f", {n_skip} skipped" if n_skip else ""
    if failed == 0 and total > 0:
        suffix = " (subset only, not acceptance)" if only else ""
        print(f"PASS {total} tests ({total - n_skip} / {total} passed{skipped}){suffix}")
        return 0
    if total == 0:
        print("FAIL no tests ran")
        print("FAILED 1 of 1 tests (0 / 1 passed)")
        return 1
    print(f"FAILED {failed} of {total} tests ({total - failed - n_skip} / {total} passed{skipped})")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
