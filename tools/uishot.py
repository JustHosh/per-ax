#!/usr/bin/env python3
"""uishot.py - render the main surfaces to PNGs so a UI change can be LOOKED at, not assumed.

    python tools\\uishot.py [settings] [champselect] [widget] [draftboard] [--out DIR]

No League client or game needed: champ select and the widget are drawn from demo data through
the real render functions; Settings is the real Tk window, opened invisibly (alpha 0, no focus
steal) and captured viewport by viewport with PrintWindow; the DraftBoard page is screenshot in
headless Edge in its #demo mode. With no surface named it renders all four. Output defaults to
%APPDATA%\\Smiteless\\cache\\uishot.
"""
import ctypes
import os
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("core", "ui", "tools"):
    sys.path.insert(0, os.path.join(_ROOT, _d))

import smitepaths as sp

SURFACES = ("settings", "champselect", "widget", "draftboard")


def _sheet(images, out_path, gap=8):
    from PIL import Image
    W = sum(i.width for i in images) + gap * (len(images) - 1)
    sheet = Image.new("RGB", (W, max(i.height for i in images)), (60, 60, 60))
    x = 0
    for i in images:
        sheet.paste(i, (x, 0))
        x += i.width + gap
    sheet.save(out_path)
    return out_path


def champselect(out):
    """The docked champ-select panel: a demo draft with the CLIMB MODE pool reminder."""
    import lolbuild as lb
    import smitecard as sc
    dd = lb.ddragon()
    cid = lambda n: dd["name2id"][dd["norm"](n)]
    me = cid("Sett")
    allies = [(me, "top"), (cid("Vi"), "jungle"), (cid("Ahri"), "mid"), (0, "adc"),
              (cid("Thresh"), "support")]
    enemies = [cid("Darius"), cid("LeeSin")]
    taken = {c for c, _ in allies if c} | set(enemies)
    pool = [cid("Garen"), cid("Darius")]
    sugg = sc.suggest_champs(dd, "top", [c for c, _ in allies if c and c != me], enemies,
                             topn=12, fam=None)
    first = [c for c in pool if c not in taken]
    sugg = (first + [c for c in sugg if c not in first])[:5]
    ideas = sc.team_bans(dd, allies, taken=taken, self_cid=me) or sc.general_bans(dd, "top", taken)
    img = sc.render_cs_vertical(dd, me, "top", allies, sc.pick_rune(sc.build_data(dd, me, "top")),
                                suggestions=sugg, bans=([cid("Zed")], [cid("Yasuo")]),
                                enemy_picks=enemies, ban_ideas=ideas, auto_import=True,
                                note="⚠ off your pool — you queue for Garen / Darius")
    p = os.path.join(out, "champselect.png")
    img.save(p)
    return [p]


def widget(out):
    """The in-game widget's reference view, once per enemy-jungler state."""
    import lolbuild as lb
    import smitewidget as sw
    dd = lb.ddragon()
    rec = {"champ": "Ahri", "lines": [("core", "Luden's ✓  →  ▸ Shadowflame  →  Rabadon")],
           "summary": "enemy 120 AD / 80 AP", "no_pool": False}
    base = {"objectives": [{"label": "Drake", "secs": 75, "up": False, "urgent": False,
                            "setup": True}],
            "spike": None, "winprob": None, "gank": None, "lead": 800}
    states = [{"state": "seen", "side": "botside", "what": "kill", "ago": 9},
              {"state": "stale", "side": "topside", "what": "grubs", "ago": 70},
              {"state": "unknown", "side": None, "what": None, "ago": None},
              {"state": "dead", "side": None, "what": None, "ago": None, "respawn": 22}]
    imgs = [sw._render_body(dd, rec, dict(base, jungle={"champ": "Kha'Zix", "respawn": 0, **s}),
                            None, ref=True) for s in states]
    return [_sheet(imgs, os.path.join(out, "widget_jungle.png"), gap=10)]


def settings(out):
    """The real Settings window, opened invisibly and captured one viewport at a time."""
    from ctypes import wintypes
    import tkinter as tk
    from PIL import Image
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    u32.GetAncestor.restype = wintypes.HWND

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    def grab(hwnd):
        r = wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        hdc = u32.GetWindowDC(hwnd)
        mdc = g32.CreateCompatibleDC(hdc)
        bmp = g32.CreateCompatibleBitmap(hdc, w, h)
        g32.SelectObject(mdc, bmp)
        u32.PrintWindow(hwnd, mdc, 2)                     # PW_RENDERFULLCONTENT
        bi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        g32.DeleteObject(bmp)
        g32.DeleteDC(mdc)
        u32.ReleaseDC(hwnd, hdc)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)

    paths = []
    real_init, real_loop = tk.Tk.__init__, tk.Misc.mainloop

    def quiet_init(self, *a, **k):
        real_init(self, *a, **k)
        self.attributes("-alpha", 0.0)                    # invisible, still rendered
        self.attributes("-toolwindow", True)

    def capture_loop(self, n=0):
        self.update()
        canvas = next(w for w in self.winfo_children()[0].winfo_children()
                      if isinstance(w, tk.Canvas))
        hwnd = u32.GetAncestor(self.winfo_id(), 2)        # GA_ROOT
        shots, seen, f = [], set(), 0.0
        while True:
            canvas.yview_moveto(f)
            for _ in range(4):
                self.update()
                time.sleep(0.05)
            top, bot = canvas.yview()
            if round(top, 3) in seen:
                break
            seen.add(round(top, 3))
            shots.append(grab(hwnd))
            if bot >= 0.999:
                break
            f = bot
        self.destroy()
        paths.append(_sheet(shots, os.path.join(out, "settings.png")))

    tk.Tk.__init__, tk.Misc.mainloop = quiet_init, capture_loop
    try:
        import smitesettings
        smitesettings.main()
    finally:
        tk.Tk.__init__, tk.Misc.mainloop = real_init, real_loop
    return paths


def draftboard(out):
    """docs/draft/index.html in its #demo mode, screenshot by headless Edge."""
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.exists(edge):
        print("draftboard: Microsoft Edge not found, skipped")
        return []
    page = os.path.join(_ROOT, "docs", "draft", "index.html").replace("\\", "/")
    p = os.path.join(out, "draftboard.png")
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={os.path.join(out, 'edge-profile')}",
                    "--virtual-time-budget=10000", "--window-size=1100,1500",
                    f"--screenshot={p}", f"file:///{page}#demo"],
                   capture_output=True, timeout=90)
    # msedge.exe hands off to a child browser process and returns before the screenshot is
    # written, so wait for the file to land and stop growing.
    last, deadline = -1, time.time() + 45
    while time.time() < deadline:
        size = os.path.getsize(p) if os.path.exists(p) else -1
        if size > 0 and size == last:
            return [p]
        last = size
        time.sleep(1.0)
    print("draftboard: Edge produced no screenshot")
    return []


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    out = sp.cache("uishot")
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    os.makedirs(out, exist_ok=True)
    unknown = [a for a in args if a not in SURFACES]
    if unknown:
        sys.exit(f"unknown surface(s): {unknown}; choose from {', '.join(SURFACES)}")
    for name in (args or SURFACES):
        for p in globals()[name](out):
            print(p)


if __name__ == "__main__":
    main()
