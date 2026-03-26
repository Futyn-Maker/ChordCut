#!/usr/bin/env python
"""Run ChordCut from the repository root without installation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from chordcut.__main__ import main

main()
