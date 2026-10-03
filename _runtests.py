"""Run every check file in tests/ and report a total.

Each tests/check_*.py is a standalone script built on tests/_harness.py; it
prints its own "==== name: N/M checks passed ====" line and exits non-zero when
something failed. This runner drives them all and adds up the numbers.

Rebuilt after an accidental deletion: the original was never tracked by git
(only its four .ps1/.txt siblings are), so it could not be recovered.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "tests"

SUMMARY = re.compile(r"(\d+)/(\d+) checks passed")

# A check prints names that are not ASCII. The child writes UTF-8 (PYTHONIOENCODING)
# and the parent has to decode the same way: with text=True alone, Python decodes
# using the locale code page, and on a GBK console that raises inside subprocess
# and silently loses that file's whole total.
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def check_files():
    return sorted(TESTS.glob("check_*.py"))


def run(path):
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
        env=CHILD_ENV,
    )
    output = (result.stdout or "") + (result.stderr or "")

    found = SUMMARY.findall(output)

    if not found:
        return path.name, 0, 0, output, result.returncode

    ok, all_checks = (int(value) for value in found[-1])

    return path.name, ok, all_checks, output, result.returncode


def main():
    files = check_files()

    if not files:
        print("no check files found in tests/")
        return 1

    passed = 0
    total = 0
    failures = []

    for path in files:
        name, ok, all_checks, output, code = run(path)

        passed += ok
        total += all_checks

        # a file that produced no summary at all is a failure, not a zero
        if all_checks == 0:
            failures.append(name)
            print(f"  FAIL  {name}  (no summary line)")
            continue

        if code != 0 or ok != all_checks:
            failures.append(name)
            print(f"  FAIL  {name}  ({ok}/{all_checks})")
            for line in output.splitlines():
                if "[FAIL]" in line or "Error" in line or "Traceback" in line:
                    print(f"        {line.strip()}")

    print()
    print("#" * 10 + f" {passed}/{total} checks passed " + "#" * 10)
    print(f"files: {len(files) - len(failures)}/{len(files)}")

    if failures:
        print("failing files: " + ", ".join(failures))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
