"""Compile every .py under the repo (verification helper, not shipped)."""
import compileall
import sys

ok = compileall.compile_dir(".", quiet=1, force=True, maxlevels=10)
print("COMPILE_ALL_OK" if ok else "COMPILE_FAILED")
sys.exit(0 if ok else 1)
