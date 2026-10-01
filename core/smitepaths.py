#!/usr/bin/env python3
"""smitepaths.py - the one place that decides where the app keeps its files.

Everything the app writes lives under ONE per-user folder, %APPDATA%\\Per-Ax - never in the
repo and never inside another tool's folder (it used to share ~/.claude with Claude Code):

    settings.json            the settings store (smiteconfig)
    *.json / markers         small personal state: window positions, saved-login index, your
                             Riot IDs, the behavior ledger and LP history (NOT cache - losing
                             them loses your history)
    logs\\                    one diagnostic log per surface
    cache\\                   re-downloadable data (ddragon, op.gg, Riot matches, icons) -
                             safe to delete, it's rebuilt on demand

The AHK trays can't import this, so they spell the same folder out literally
(EnvGet("APPDATA") "\\Per-Ax\\..."); keep them in sync if APP_NAME ever changes.
"""
import os

APP_NAME = "Per-Ax"

DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
LOG_DIR = os.path.join(DATA_DIR, "logs")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

for _d in (DATA_DIR, LOG_DIR, CACHE_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass


def data(*parts):
    """A file or folder of personal state, directly in the data folder."""
    return os.path.join(DATA_DIR, *parts)


def log(name):
    """A diagnostic log file."""
    return os.path.join(LOG_DIR, name)


def cache(*parts):
    """A cache file or folder (safe to delete; rebuilt on demand)."""
    return os.path.join(CACHE_DIR, *parts)


# Shared by more than one module: one constant each, so writer and readers can never drift.
LEDGER_FILE = data("behavior_ledger.json")      # every graded game's habits (lolprofile writes)
LP_HISTORY_FILE = data("lp_history.json")       # your rank snapshots over time
