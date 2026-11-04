#!/usr/bin/env python3
"""Simple ICT Short — 5m trigger (IFVG or MSS), 2R, risk modes."""
from __future__ import annotations

import sys

from simple_ict import cli_main

if __name__ == "__main__":
    raise SystemExit(cli_main("short", sys.argv[1:]))
