#!/usr/bin/env python3
# ─────────────────────────────────────────
#   JOVAS LAUNCHER
#   Usage:
#     python run.py run app.jovas
#     python run.py repl
#     python run.py check app.jovas
#     python run.py version
# ─────────────────────────────────────────
import sys, os

# Always work relative to THIS file's directory.
# Fixes Windows cross-drive errors (C:\ vs D:\) and
# ensures jovas_modules.py and jovasdb_data/ are always found.
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

# Load and execute the Jovas engine
engine = os.path.join(HERE, "jovas.jo")
with open(engine, encoding="utf-8") as f:
    exec(compile(f.read(), engine, "exec"), {"__name__": "__main__"})
