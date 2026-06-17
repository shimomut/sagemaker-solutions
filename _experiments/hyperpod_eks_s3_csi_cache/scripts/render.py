#!/usr/bin/env python3
"""Render a manifest template by expanding ${VAR} placeholders from the environment.

Usage:
    cat template.yaml | python3 render.py
    python3 render.py template.yaml

Only ${VAR} / $VAR style placeholders are expanded (via os.path.expandvars).
Required variables that are unset are reported so the customer gets a clear
error instead of applying a half-rendered manifest.
"""

import os
import re
import sys

# Placeholders we expect callers to provide. If any are still present and unset
# after expansion, we fail loudly.
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def main() -> int:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    rendered = os.path.expandvars(text)

    # Detect any placeholders that were not substituted (i.e. unset env vars).
    missing = sorted(
        {m.group(1) or m.group(2) for m in PLACEHOLDER_RE.finditer(rendered)}
    )
    if missing:
        sys.stderr.write(
            "ERROR: the following variables are not set in the environment:\n"
            + "".join(f"  - {name}\n" for name in missing)
        )
        return 1

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
