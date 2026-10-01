#!/usr/bin/env python3
"""perax_main.py - single entry point for the bundled app.

One frozen exe (PerAxApp.exe) covers every window/tool; the first CLI arg picks which:

    PerAxApp.exe overlay        the scoreboard overlay (default)
    PerAxApp.exe widget         the floating item widget
    PerAxApp.exe dead           the fullscreen see-through DEATH BRIEF (while you're dead)
    PerAxApp.exe load           the LOADING-SCREEN matchup overlay (champ tags + game plan)
    PerAxApp.exe queue          the QUEUE CALL card (lobby only: should you play this one?)
    PerAxApp.exe mute           IN-GAME QUIET: League's own chat/ping settings (no typing)
    PerAxApp.exe settings       the settings window
    PerAxApp.exe phase <file>   write the LCU gameflow phase to <file> (for the tray watcher)
    PerAxApp.exe login <name>   one-click Riot login: swap to a saved account SESSION (no pw)
    PerAxApp.exe accounts ...   saved-session admin (list / save <name> / remove <name>)
    PerAxApp.exe update [--apply]  check GitHub for a newer release (notify / one-click)
    PerAxApp.exe selftest       dependency health check (dev)

Kept tiny on purpose so PyInstaller has a clean root to analyse.
"""
import os
import sys

# Dev (not frozen): make the flat imports resolve from the source folders. When frozen,
# every module is bundled into the exe, so these inserts are harmless no-ops.
if not getattr(sys, "frozen", False):
    _R = os.path.dirname(os.path.abspath(__file__))
    for _d in ("core", "ui", "tools"):
        sys.path.insert(0, os.path.join(_R, _d))


for _s in ("stdout", "stderr"):                # pythonw / bundled exe: no console -> stdio is None
    if getattr(sys, _s, None) is None:
        try:
            setattr(sys, _s, open(os.devnull, "w"))
        except Exception:
            pass


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "overlay").lower()
    rest = sys.argv[2:]
    sys.argv = [sys.argv[0]] + rest                  # downstream sees only its own flags

    if cmd == "overlay":
        import smiteoverlay
        smiteoverlay.main()
    elif cmd == "widget":
        import smitewidget
        smitewidget.main()
    elif cmd == "dead":
        import smitedead
        smitedead.main()
    elif cmd == "load":
        import smiteload
        smiteload.main()
    elif cmd == "settings":
        import smitesettings
        smitesettings.main()
    elif cmd == "profile":
        import smiteprofile
        smiteprofile.main()
    elif cmd == "notes":
        import smitenotes
        smitenotes.main()
    elif cmd == "queue":
        import smitequeue
        smitequeue.main()
    elif cmd == "mute":
        import lolmute
        lolmute.main()
    elif cmd == "phase":
        import tempfile
        import phasecheck
        out = rest[0] if rest else os.path.join(tempfile.gettempdir(), "perax_phase.txt")
        try:
            # DETAILED: the loading screen reports as 'Loading', so the AHK watcher can open
            # the loading scout there while holding the in-game widget back until the match
            # actually starts (see phasecheck.phase_detailed).
            with open(out, "w", encoding="utf-8") as f:
                f.write(phasecheck.phase_detailed() or "")
        except Exception:
            pass
    elif cmd == "login":
        import lolaccounts
        lolaccounts.main(["login", *rest])
    elif cmd == "accounts":
        import lolaccounts
        lolaccounts.main(rest)
    elif cmd == "keycheck":
        import smitekeycheck
        smitekeycheck.main()
    elif cmd == "update":
        import smiteupdate
        smiteupdate.main(rest)
    elif cmd == "selftest":
        import selftest
        selftest.main()
    else:
        sys.stderr.write("usage: PerAxApp.exe [overlay|widget|dead|load|queue|mute|settings|"
                         "phase|login <name>|accounts|update|"
                         "selftest]\n")


if __name__ == "__main__":
    main()
