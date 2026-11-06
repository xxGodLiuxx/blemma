#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UserPromptSubmit / Stop: one short status POST, no output or decisions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _client
except Exception:
    sys.exit(0)


def main() -> None:
    _client.state(_client.read_input())


if __name__ == "__main__":
    _client.run_hook(main)
