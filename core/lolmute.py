#!/usr/bin/env python3
"""lolmute.py - IN-GAME QUIET: League's own chat and ping settings, written through the client.

Writes the client's OWN settings over the LCU (ally chat hidden, all-chat hidden, ping audio
off) and VERIFIES them by reading them back. Nothing is ever typed into the game. An earlier
version also sent `/fullmute all` as synthetic keystrokes; injecting input into a live game is
the kind of automation Riot's third-party policy rules out, so that layer is gone for good and
the self-test fails if input-injection code ever comes back.

Two honest limits of the settings-only approach: ping MARKERS still draw on the minimap (the
client has no setting for them), and because these are client settings they PERSIST until you
turn them back on - `python core\\lolmute.py off`, Settings -> In-game quiet, or League's own
Audio/Interface options.
"""
import os, sys, time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("core", "ui", "tools"):
    sys.path.insert(0, os.path.join(_ROOT, _d))
for _s in ("stdout", "stderr"):
    if getattr(sys, _s, None) is None:
        try:
            setattr(sys, _s, open(os.devnull, "w"))
        except Exception:
            pass

import smiteconfig as cfg
import lolimport as limp                     # its _lcu_json is the shared, proven LCU caller

_LOG = os.path.expanduser("~/.claude/smiteless_mute.log")

SETTINGS_PATH = "/lol-game-settings/v1/game-settings"
# Every client setting that makes the game quieter, all verified writable on this client.
# ChatChannelVisibility 0 hides the chat channels outright; PingsVolume 0 belts-and-braces
# PingsMute in case a patch ever makes the mute flag advisory.
MUTED = {"HUD": {"ShowAlliedChat": False, "ShowAllChannelChat": False,
                 "ChatChannelVisibility": 0},
         "Volume": {"PingsMute": True, "PingsVolume": 0.0}}
UNMUTED = {"HUD": {"ShowAlliedChat": True, "ShowAllChannelChat": True,
                   "ChatChannelVisibility": 2},
           "Volume": {"PingsMute": False, "PingsVolume": 0.31}}


def _log(msg):
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def read_state():
    """The mute settings as the client reports them, or None if it isn't up / no longer
    exposes them."""
    try:
        cur = limp._lcu_json("GET", SETTINGS_PATH)
    except Exception:
        return None
    if not isinstance(cur, dict):
        return None
    out = {}
    for grp, keys in MUTED.items():
        for k in keys:
            if k not in (cur.get(grp) or {}):
                return None
            out[f"{grp}.{k}"] = cur[grp][k]
    return out


def apply(on=True):
    """Write the settings and VERIFY by reading back. Returns (ok, detail)."""
    want = MUTED if on else UNMUTED
    before = read_state()
    if before is None:
        return False, "client not reachable, or it no longer exposes these settings"
    try:
        limp._lcu_json("PATCH", SETTINGS_PATH, want)
    except Exception as e:
        return False, f"PATCH failed: {type(e).__name__}"
    after = read_state()
    if after is None:
        return False, "could not read the settings back"
    flat = {f"{g}.{k}": v for g, ks in want.items() for k, v in ks.items()}
    bad = [k for k, v in flat.items() if after.get(k) != v]
    if bad:
        return False, "the client did not accept: " + ", ".join(bad)
    changed = [k for k in flat if before.get(k) != after.get(k)]
    return True, ("already set" if not changed else "set " + ", ".join(changed))


def main():
    """Tray entry, spawned at champ select: apply the quiet settings once, verified, and exit.
    Self-gates on the `auto_mute` setting."""
    if not cfg.load().get("auto_mute", True):
        return
    ok, detail = apply(True)
    _log(f"settings {'OK' if ok else 'FAILED'} - {detail}")


if __name__ == "__main__":
    arg = (sys.argv[1].lower() if len(sys.argv) > 1 else "")
    if arg in ("off", "unmute"):
        print("unmuted -> %s" % (apply(False),))
    elif arg in ("state", "status"):
        st = read_state()
        print("client not reachable" if st is None else
              "\n".join(f"  {k} = {v}" for k, v in st.items()))
    else:
        main()
