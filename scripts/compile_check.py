"""Compile every .py under the repo (verification helper, not shipped)."""
import compileall
import sys
from pathlib import Path

SKIP = {".venv", ".git", "__pycache__", ".pytest_cache", "third_party"}

ok = True
for py in Path(".").rglob("*.py"):
    if any(part in SKIP for part in py.parts):
        continue
    if not compileall.compile_file(str(py), quiet=1, force=True):
        print(f"FAILED {py}")
        ok = False
print("COMPILE_ALL_OK" if ok else "COMPILE_FAILED")
sys.exit(0 if ok else 1)
