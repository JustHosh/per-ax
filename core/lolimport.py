#!/usr/bin/env python3
"""lolimport.py - write the op.gg runes + summoners into the League client (LCU).

Shared by the champ-select panel's Import button and the AUTO-IMPORT path (imports the
moment you lock a champion, when the toggle is on). POSTs a fresh "Per-Ax ..." rune
page (recycling an old Per-Ax page / the current editable one when the page limit is
hit) and PATCHes the summoner picks, honoring the Flash-on-D/F preference.

It never makes a champ-select DECISION for you: no auto-lock, no auto-ban, no ready-check
accept, no role or pick-order swap requests - Riot's third-party policy rules out automating
those, and the self-test fails if any of them comes back. The only other champ-select write
is hover_champ(), and it runs only when you click a suggestion.
"""
import json
import ssl
import time
import urllib.request

import lolgame as lg
import smiteconfig as cfg


def _lcu_json(method, path, payload=None, timeout=5):
    lc = lg._lcu()
    if not lc:
        raise RuntimeError("League client not found")
    port, hdr = lc
    headers = dict(hdr)
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"https://127.0.0.1:{port}{path}", headers=headers,
                                 data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as r:
        raw = r.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def hover_champ(cid):
    """HOVER (select, not lock) a champion in champ select via the LCU: PATCH your in-progress
    pick action with the championId and no 'completed' flag. The client then shows it as your
    intent, and the overlay re-renders to that champ. Returns "hovered"; raises RuntimeError
    with a friendly message on anything expected. Never locks — that's a separate action."""
    if not cid:
        raise RuntimeError("no champion")
    try:
        sess = _lcu_json("GET", "/lol-champ-select/v1/session")
    except Exception:
        raise RuntimeError("not in champ select")
    if not isinstance(sess, dict) or sess.get("localPlayerCellId") is None:
        raise RuntimeError("not in champ select")
    cell = sess.get("localPlayerCellId")
    action_id = None
    for group in (sess.get("actions") or []):
        for a in group:
            if (a.get("actorCellId") == cell and a.get("type") == "pick"
                    and not a.get("completed")):
                action_id = a.get("id")               # your current (un-locked) pick slot
    if action_id is None:
        raise RuntimeError("can't hover yet — wait for your turn (or you've already locked)")
    _lcu_json("PATCH", f"/lol-champ-select/v1/session/actions/{action_id}",
              {"championId": int(cid)})
    return "hovered"


# Riot summoner-spell ids. The mobility spells, in priority order: whichever of these a build
# carries goes on your preferred key (Settings -> Flash key). spell1Id is D, spell2Id is F.
FLASH_ID, GHOST_ID = 4, 6
MOBILITY_SPELLS = (FLASH_ID, GHOST_ID)

_PICKABLE = {"ids": None, "ts": 0.0}


def pickable_ids(ttl=5.0):
    """Champion ids you can ACTUALLY pick right now, or None if the client won't say.

    The recommender ranks champions on merit alone, which includes champions you don't own;
    the suggestion strip filters on this so it never offers one the client would refuse.
    `pickable-champion-ids` is the honest answer during champ select (it accounts for free
    rotation and bans too); owned-champions-minimal is the fallback outside it."""
    now = time.monotonic()
    if _PICKABLE["ids"] is not None and (now - _PICKABLE["ts"]) < ttl:
        return _PICKABLE["ids"]
    ids = None
    for path in ("/lol-champ-select/v1/pickable-champion-ids",
                 "/lol-champions/v1/owned-champions-minimal"):
        try:
            r = _lcu_json("GET", path)
        except Exception:
            continue
        if isinstance(r, list) and r:
            got = {c if isinstance(c, int) else c.get("id") for c in r}
            got = {int(c) for c in got if c}
            if got:
                ids = got
                break
    _PICKABLE.update(ids=ids, ts=now)
    return ids


def import_build(dd, cid, role, build):
    """Push `build`'s runes + summoners for cid/role into the client. Returns a status
    string; raises RuntimeError with a friendly message on anything expected."""
    if not cid:
        raise RuntimeError("lock a champion first")
    if not build:
        raise RuntimeError("no op.gg build for this champ/role yet")
    perks = (build.get("primary_ids") or []) + (build.get("secondary_ids") or []) + (build.get("stat_mod_ids") or [])
    if len(perks) < 9:
        raise RuntimeError("rune data incomplete")
    page = {
        "name": f"Per-Ax {dd['id2name'].get(cid, 'Champ')} {str(role or '').title()}",
        "primaryStyleId": int(build.get("primary_page_id") or 0),
        "subStyleId": int(build.get("secondary_page_id") or 0),
        "selectedPerkIds": [int(x) for x in perks[:9]],
        "current": True,
    }
    try:
        _lcu_json("POST", "/lol-perks/v1/pages", page)
    except Exception:
        pages = _lcu_json("GET", "/lol-perks/v1/pages") or []
        editable = [p for p in pages if p.get("isEditable", True)]
        target = None
        for p in editable:
            if (p.get("name") or "").startswith("Per-Ax "):
                target = p
                break
        if target is None:
            target = next((p for p in editable if p.get("current")), None)
        if target is None and editable:
            target = editable[0]
        if not target or not target.get("id"):
            raise RuntimeError("rune page limit reached and no editable page is available")
        up = dict(page)
        up["id"] = int(target["id"])
        _lcu_json("PUT", f"/lol-perks/v1/pages/{int(target['id'])}", up)
    sums = build.get("summoner_ids") or []
    if len(sums) >= 2:
        s1, s2 = int(sums[0]), int(sums[1])
        flash_on_d = cfg.load().get("flash_on_d", True)
        # Your ESCAPE key never moves. Flash owns the preferred slot; on a build that has no
        # Flash, GHOST inherits it — same finger, same panic button. Ghost-only builds used to
        # land wherever op.gg happened to order them, which is the one spell you cannot afford
        # to hunt for. If a build somehow runs both, Flash wins and Ghost takes the other slot.
        key_spell = next((sp for sp in MOBILITY_SPELLS if sp in (s1, s2)), None)
        if key_spell is not None and (s1 == key_spell) != bool(flash_on_d):
            s1, s2 = s2, s1
        _lcu_json("PATCH", "/lol-champ-select/v1/session/my-selection",
                  {"spell1Id": s1, "spell2Id": s2})
    return f"imported for {dd['id2name'].get(cid, '?')} ({role})"
