import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_scripts_dir = str(_here.parent / "scripts")
_tests_dir = str(_here)

if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)
