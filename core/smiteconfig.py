#!/usr/bin/env python3
"""smiteconfig.py - tiny shared settings store for Smiteless.

Settings live in %APPDATA%\\Smiteless\\settings.json (smitepaths; read live by the
overlay and edited by smitesettings.py). Auto-open is a marker file (so it can be toggled
without parsing JSON), and "start with Windows" is a registry Run key.
"""
import os, sys, json
import smitepaths as sp

PATH = sp.data("settings.json")


# ---------- tie every surface's lifetime to the tray (no orphan windows on force-close) ----------
# The tray (AHK or pystray) holds the "Global\SmitelessTray" mutex for its whole life. Each
# surface polls it: seen-alive-then-gone => the tray was force-closed/crashed => close myself.
_TRAY_MUTEX = "Global\\SmitelessTray"
_tray_seen = [False]


def _tray_alive():
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenMutexW(0x00100000, False, _TRAY_MUTEX)     # SYNCHRONIZE
        if h:
            k.CloseHandle(h)                                 # never RETAIN it (that'd keep it alive)
            return True
    except Exception:
        return True                                          # can't tell -> never false-kill a window
    return False


def tray_gone():
    """True only once the tray has been seen alive and has since vanished. Always False when
    there was never a tray (a surface launched standalone in dev), so `python ui/x.py` still runs."""
    if _tray_alive():
        _tray_seen[0] = True
        return False
    return _tray_seen[0]


def watch_tray(root, interval=700):
    """Tk helper: self-close `root` within ~<1s of the Smiteless tray going away, so no
    overlay/widget is left orphaned when you force-close Smiteless. Call once after the window
    is built. Snappy and cheap (a single OpenMutex probe per tick)."""
    def tick():
        if tray_gone():
            try:
                root.destroy()
            except Exception:
                pass
            return
        try:
            root.after(interval, tick)
        except Exception:
            pass
    tray_gone()                                              # latch 'seen' now — tray is up at spawn
    try:
        root.after(interval, tick)
    except Exception:
        pass
NOAUTO = sp.data("noautoopen")      # presence = auto-open OFF (the AHK trays read it too)
NOHOME = sp.data("nohomeonstart")   # presence = open profile/home at startup OFF
HERE = os.path.dirname(os.path.abspath(__file__))

# streak_influence: 0..100, 50 = the original/default behavior (a multiplier m = value/50
#   scales the enemy form weight, the streak compounding, and the extreme override).
# gank_threshold: |score| cut for GANK / TOUGH (lower = more lanes tagged).
# scout_games: recent ranked games pulled per player.
DEFAULTS = {"streak_influence": 50, "gank_threshold": 6.0, "scout_games": 10, "profile_games": 30,
            "dragon_volume": 30, "board_size": 70}
RANGES = {"streak_influence": (0, 100), "gank_threshold": (3.0, 12.0), "scout_games": (5, 20),
          "profile_games": (5, 60), "dragon_volume": (0, 100), "board_size": (40, 100)}
# Feature toggles (read live by the relevant module).
BOOLS = {"matchup_tips": True,    # generate the AI lane tip in champ-select/in-game
         "gank_kit": True,        # factor YOUR champ's CC/engage into the gank ratings
         "item_widget": True,     # the floating in-game item helper
         "game_intel": True,      # widget: live win read + objective timers + spike alerts
         "tempo_coach": True,     # widget: TEMPO engine — objective-setup directives (farm/base/move/take-give)
         "free_alarm": True,      # widget: FREE — alarm when the enemy jungler provably can't contest an objective
         "tempo_voice": True,     # widget: spoken TEMPO callouts (Windows TTS: "Base now", "Take it", ...)
         "dragon_audio": True,    # widget: audio beeps 45/30/15s before a drake spawns
         "respawn_plan": True,    # widget: RESPAWN — death screen becomes countdown + comeback plan
         "re_entry": True,        # widget: RE-ENTRY — the 90s-after-respawn guard (core/lolreentry)
         "bleed_guard": True,     # widget: BLEED — the first-14-minutes health guard (core/lolbleed)
         "closer": True,          # widget: CLOSER — the post-20:00 win-conversion director (core/lolclose)
         "gold_clock": True,      # widget: GOLD CLOCK — first-ten farm pace vs the real wave schedule (core/lolgold)
         "ward_clock": True,      # widget: WARD CLOCK — the live vision war, jungle/support only (core/lolward)
         "the_out": True,         # widget: THE OUT — the losing game from 15:00: is there a path? (core/lolout)
         "death_brief": True,     # fullscreen see-through DEATH BRIEF overlay while you're dead
         "loading_scout": True,     # fullscreen LOADING SCOUT: ten splash cards (rank, form, KDA,
                                    #   profile-read tags, damage lean) while the game loads. FRESH
                                    #   key, default ON — a stale `loading_overlay:false` from when
                                    #   the native overlay was retired must not suppress the rebuilt
                                    #   card board, so the gate reads this key, not the old one.
         "loading_overlay": False,  # LEGACY / ignored — superseded by `loading_scout` above.
         "queue_call": True,      # LOBBY: the pre-queue stop/go verdict card (core/lolqueue)
         "dodge_alerts": True,    # champ select: high-confidence "consider dodging" banner
         "dock_champ_select": True,  # champ select helper docks as a tall panel LEFT of the client
         "board_topmost": True,   # live board/scoreboard stays above other windows (untick to allow covering)
         "auto_import": False,    # import runes+summs AUTOMATICALLY when you lock a champ
         "auto_mute": True,       # in-game quiet: League's own chat/ping settings, written
                                  #   through the client and read back, nothing typed — core/lolmute
         "flash_on_d": True,      # import puts Flash on D (off = put Flash on F)
         "solo_coaching": True,   # profile/climb/session coaching from RANKED SOLO games only
         "draft_link": True,      # champ select: publish the live draft board + post the link in chat
         "draft_autoopen": True,  # champ select: also OPEN the draft board in your own browser
         "max_elo": False,        # CLIMB MODE: every climb read on + your pool reminded in draft
         "legend_seen": False}    # widget: LEGEND card already auto-opened once (state, not a toggle)

# CLIMB MODE (the old "MAX ELO" switch, keys kept for compatibility) — arming it turns on every
# surface that shortens the climb and nothing that doesn't, and names your champion pool
# (max_elo_main + max_elo_backup). Champ select then puts the pool first in the suggestion strip
# and flags a hover off it — but it NEVER accepts, bans, picks or locks for you: those decisions
# stay your clicks (Riot's third-party policy rules out automating them). Anything NOT in this
# list is deliberately absent — `flash_on_d` is not a climb lever at all, and `board_topmost`
# is taste.
MAX_ELO_ON = ("auto_import", "auto_mute",
              "item_widget", "game_intel", "tempo_coach", "free_alarm", "re_entry",
              "bleed_guard", "closer", "gold_clock", "ward_clock", "the_out", "respawn_plan", "death_brief", "loading_scout",
              "queue_call",
              "dodge_alerts", "matchup_tips", "dock_champ_select",
              "draft_link", "draft_autoopen", "solo_coaching", "gank_kit")

# Free-text settings (trimmed strings, no validation beyond str()).
# draft_db: the user's own Firebase RTDB url ('' = draft link feature dormant); see docs/DRAFTLINK.md.
# draft_page: where the static draft board is hosted (GitHub Pages serves /docs on main).
# draft_msg: the champ-select chat line the link is posted with ('' = the branded default).
# Settings keys belonging to features that have been CUT. save() drops them, so a retired
# surface leaves nothing behind in the user's settings file.
RETIRED = ("fav_champs", "ghost_race", "duo_detection",
           # champ-select autopilot, removed for policy reasons (never auto-decide for you)
           "auto_ban", "auto_accept", "ban_list", "auto_swap_roles", "auto_pick_swap")

# Riot platform id -> (regional route for match-v5, the op.gg / League of Graphs / Porofessor
# site code, label). account-v1 has no "sea" cluster; lolscout sends SEA account lookups to
# "asia". The default is LAN: this fork plays on la1.
REGIONS = {
    "la1": ("americas", "lan", "LAN - Latin America North"),
    "la2": ("americas", "las", "LAS - Latin America South"),
    "na1": ("americas", "na", "NA - North America"),
    "br1": ("americas", "br", "BR - Brazil"),
    "euw1": ("europe", "euw", "EUW - Europe West"),
    "eun1": ("europe", "eune", "EUNE - Europe Nordic & East"),
    "tr1": ("europe", "tr", "TR - Turkey"),
    "ru": ("europe", "ru", "RU - Russia"),
    "me1": ("europe", "me", "ME - Middle East"),
    "kr": ("asia", "kr", "KR - Korea"),
    "jp1": ("asia", "jp", "JP - Japan"),
    "oc1": ("sea", "oce", "OCE - Oceania"),
    "sg2": ("sea", "sg", "SEA - Southeast Asia"),
    "tw2": ("sea", "tw", "TW - Taiwan"),
    "vn2": ("sea", "vn", "VN - Vietnam"),
}
DEFAULT_REGION = "la1"

STRINGS = {"max_elo_main": "",      # CLIMB MODE: the champion you queue for ('' = not chosen)
           "max_elo_backup": "",    # ... and the one you go to when the main is banned/taken
           "region": DEFAULT_REGION,  # Riot platform id, a key of REGIONS (Settings -> Region)
           "draft_db": "",
           "draft_page": "",       # YOUR GitHub Pages copy of docs/draft/ ('' = dormant)
           "draft_msg": ""}


def load():
    s = dict(DEFAULTS)
    s.update(BOOLS)
    s.update(STRINGS)
    try:
        raw = json.load(open(PATH, encoding="utf-8"))
        for k in DEFAULTS:
            if k in raw:
                v = type(DEFAULTS[k])(raw[k])
                lo, hi = RANGES[k]
                s[k] = min(hi, max(lo, v))
        for k in BOOLS:
            if k in raw:
                s[k] = bool(raw[k])
        for k in STRINGS:
            if k in raw:
                s[k] = str(raw[k]).strip()
    except Exception:
        pass
    return s


def region():
    """The configured Riot platform id ('la1' unless changed in Settings; junk falls back)."""
    r = str(load().get("region") or "").strip().lower()
    return r if r in REGIONS else DEFAULT_REGION


def routing(platform=None):
    """(platform, regional, site_code) for `platform`, or for the configured region."""
    p = platform if platform in REGIONS else region()
    regional, site, _label = REGIONS[p]
    return p, regional, site


def arm_max_elo(main, backup=""):
    """Arm CLIMB MODE: every climb feature on, the champion pool set to main (+ backup), saved.
    Returns the written settings dict. Deliberately a WRITE, not a read-time override — the
    checkboxes must show the truth, and un-arming must not silently undo choices you made."""
    upd = {k: True for k in MAX_ELO_ON}
    upd.update(max_elo=True, max_elo_main=str(main or "").strip(),
               max_elo_backup=str(backup or "").strip())
    return save(upd)


def stand_down_max_elo():
    """Turn the champion-pool reminder off and nothing else. The features CLIMB MODE switched
    on stay on — they were good ideas before you armed it and they still are."""
    return save({"max_elo": False})


def save(s):
    # MERGE onto whatever's already on disk: only keys present in `s` are updated, everything
    # else is preserved. Rebuilding from DEFAULTS used to mean a save that didn't carry every
    # key (e.g. a partial update) silently reverted the rest — that's how Flash-on-D kept
    # coming back. Missing-from-both keys fall back to their default.
    try:
        cur = json.load(open(PATH, encoding="utf-8"))
        if not isinstance(cur, dict):
            cur = {}
    except Exception:
        cur = {}
    clean = dict(cur)
    for k in DEFAULTS:
        if k in s:
            try:
                v = type(DEFAULTS[k])(s[k])
            except Exception:
                v = cur.get(k, DEFAULTS[k])
            lo, hi = RANGES[k]
            clean[k] = min(hi, max(lo, v))
        elif k not in clean:
            clean[k] = DEFAULTS[k]
    for k in BOOLS:
        if k in s:
            clean[k] = bool(s[k])
        elif k not in clean:
            clean[k] = BOOLS[k]
    for k in STRINGS:
        if k in s:
            clean[k] = str(s[k]).strip()
        elif k not in clean:
            clean[k] = STRINGS[k]
    for k in RETIRED:                       # a cut feature must not leave its key behind
        clean.pop(k, None)
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = f"{PATH}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2)
        os.replace(tmp, PATH)
    except Exception:
        pass
    return clean


def auto_open_enabled():
    return not os.path.exists(NOAUTO)


def set_auto_open(on):
    try:
        if on:
            if os.path.exists(NOAUTO):
                os.remove(NOAUTO)
        else:
            open(NOAUTO, "w").close()
    except Exception:
        pass


def home_on_start_enabled():
    return not os.path.exists(NOHOME)


def set_home_on_start(on):
    try:
        if on:
            if os.path.exists(NOHOME):
                os.remove(NOHOME)
        else:
            open(NOHOME, "w").close()
    except Exception:
        pass


# ---------- start with Windows (registry Run key) ----------
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP = "Smiteless"


def autostart_command():
    """The command Windows runs at login. Prefer the AutoHotkey tray (the reliable shell);
    fall back to the pure-Python tray if AutoHotkey isn't installed."""
    ahk = os.path.expanduser(r"~/AppData/Local/Programs/AutoHotkey/v2/AutoHotkey64.exe")
    ahk_script = os.path.join(HERE, "smiteless.ahk")
    if os.path.exists(ahk) and os.path.exists(ahk_script):
        return f'"{ahk}" "{ahk_script}"'
    pyw = sys.executable
    cand = os.path.join(os.path.dirname(pyw), "pythonw.exe")
    if os.path.exists(cand):
        pyw = cand
    return f'"{pyw}" "{os.path.join(HERE, "smiteless_tray.py")}"'


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _APP)
        return True
    except Exception:
        return False


def set_autostart(on):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, _APP, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, _APP)
                except FileNotFoundError:
                    pass
    except Exception:
        pass
