#!/usr/bin/env python3
"""Rebuild the approved-report site after a report is explicitly confirmed."""

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parent.parent
module = runpy.run_path(str(ROOT / "site/build.py"))
module["build_site"](ROOT, ROOT / "site/public", base_path="/beauty-intel")
print("Published site/public from the approved report manifest.")
