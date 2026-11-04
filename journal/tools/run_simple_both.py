#!/usr/bin/env python3
"""Simple ICT one book — daily bias picks direction (bull: long, bear: short, uncertain: flat)."""
from __future__ import annotations

import sys

from simple_ict import cli_main

if __name__ == "__main__":
    raise SystemExit(cli_main("both", sys.argv[1:]))
