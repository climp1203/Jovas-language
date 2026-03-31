#!/usr/bin/env python3
# ─────────────────────────────────────────
#   JOVAS LAUNCHER
#   Boots the Jovas runtime from jovas.jo
#
#   Usage:
#     python run.py run app.jovas
#     python run.py repl
#     python run.py check app.jovas
#     python run.py version
# ─────────────────────────────────────────
import sys, os

# Load and execute the Jovas engine
engine = os.path.join(os.path.dirname(__file__), "jovas.jo")
with open(engine) as f:
    exec(compile(f.read(), engine, "exec"), {"__name__": "__main__"})
