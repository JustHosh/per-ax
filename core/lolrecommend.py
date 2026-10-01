#!/usr/bin/env python3
"""lolrecommend.py - the NEXT-ITEM recommender, learned from our own match-v5 data (phase 1).

op.gg answers "what does this champion usually build". The widget asks a sharper question in
the middle of a game: with THIS champion, against THIS lane opponent and THIS enemy damage
profile, which legendary should I finish NEXT? This module answers it from the ranked games
tools/collector.py gathers into a local SQLite file - one row per COMPLETED LEGENDARY, with the
context it was bought in. (The schema lives here too, so writer and reader can't drift.)

PHASE 1: conditional win rates with hierarchical Bayesian smoothing. For every candidate item
at your next slot (your 1st, 2nd, 3rd... finished legendary):

    L2  your champ + role + slot                       shrunk toward the champ's baseline
    L1  ... + the enemy damage profile (AD/mixed/AP)   shrunk toward L2
    L0  ... + your exact lane opponent                 shrunk toward L1

Each level is (weighted wins + M x prior) / (weighted games + M): a thin sample barely moves
off the broader estimate, a deep one speaks for itself - that is the "relax the filter when
data is thin" step, done smoothly instead of with cliffs. Recent patches weigh more: the newest
patch in the data counts 1.0, each older one half as much. It stays SILENT (returns []) unless
the champ + role has a real sample at that slot, and then the widget keeps op.gg's path.

The enemy damage profile comes from the data itself: each champion's share of MAGIC damage to
champions across every collected game, averaged over the five enemies.

Honest limit: an item's win rate is not causal. Players who are ahead buy earlier and buy
differently; conditioning on the slot absorbs only part of that. Phase 2 (a model that also
sees the gold/level state each row already stores) is where it gets addressed.

    python core\\lolrecommend.py Ahri mid --vs Zed --enemies "Zed,Lee Sin,Jinx,Thresh,Darius"
"""
import os
import sqlite3
import threading
from collections import namedtuple

import smitepaths as sp

DB_PATH = os.environ.get("PERAX_MATCH_DB") or sp.data("matches.sqlite")

M_PRIOR = 25.0            # pseudo-games of the broader estimate every level starts from
MIN_SLOT_GAMES = 150      # champ + role + slot sample below which the recommender stays silent
MIN_ITEM_GAMES = 12       # an item needs this many games at that slot to be a candidate...
MIN_ITEM_SHARE = 0.03     # ...and this share of the slot's purchases (no one-off oddities)
MIN_SCOPE_GAMES = 30      # games a narrower scope needs before the explanation cites it
PATCH_DECAY = 0.5         # weight of each older patch relative to the next newer one
AP_EDGES = (0.35, 0.55)   # enemy magic-damage share: below = "AD", above = "AP", between = mixed

SCHEMA = """
CREATE TABLE IF NOT EXISTS seeds (
    puuid TEXT PRIMARY KEY, tier TEXT, division TEXT, added_at INTEGER, ids_at INTEGER);
CREATE TABLE IF NOT EXISTS ladder_pages (
    tier TEXT, division TEXT, page INTEGER, fetched_at INTEGER, n INTEGER,
    PRIMARY KEY (tier, division, page));
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'queued', tier TEXT,
    patch TEXT, game_start INTEGER, duration INTEGER, note TEXT, done_at INTEGER);
CREATE INDEX IF NOT EXISTS matches_status ON matches(status);
CREATE TABLE IF NOT EXISTS participants (
    match_id TEXT, pid INTEGER, team INTEGER, champ INTEGER, role TEXT, opp INTEGER,
    win INTEGER, phys INTEGER, magic INTEGER, true_dmg INTEGER, patch TEXT,
    PRIMARY KEY (match_id, pid));
CREATE INDEX IF NOT EXISTS participants_champ ON participants(champ);
CREATE TABLE IF NOT EXISTS decisions (
    match_id TEXT, pid INTEGER, seq INTEGER, slot INTEGER, champ INTEGER, role TEXT,
    opp INTEGER, enemies TEXT, item INTEGER, minute REAL, prev TEXT, opp_items TEXT,
    enemy_items TEXT, gold_diff INTEGER, level_diff INTEGER, win INTEGER, patch TEXT,
    PRIMARY KEY (match_id, pid, seq));
CREATE INDEX IF NOT EXISTS decisions_champ_role ON decisions(champ, role);
CREATE TABLE IF NOT EXISTS jungle_paths (
    match_id TEXT, pid INTEGER, team INTEGER, champ INTEGER, opp INTEGER, win INTEGER,
    path TEXT, first_gank TEXT, patch TEXT, PRIMARY KEY (match_id, pid));
"""

Rec = namedtuple("Rec", "item score games scope why")


# ---------- shared definitions (the collector uses these too) ----------
def legendary_ids(dd):
    """Summoner's Rift legendaries: purchasable on map 11, finished (builds into nothing), 2000g+,
    not boots / consumables / champion-locked. Ids >= 10000 are Arena duplicates ddragon also
    flags for map 11 - a real SR game never reports them."""
    out = set()
    for iid, it in (dd.get("item_data") or {}).items():
        g = it.get("gold") or {}
        tags = it.get("tags") or []
        if (int(iid) < 10000 and g.get("purchasable") and (it.get("maps") or {}).get("11")
                and not it.get("into") and (g.get("total") or 0) >= 2000
                and "Boots" not in tags and "Consumable" not in tags
                and not it.get("requiredChampion") and not it.get("requiredAlly")
                and it.get("inStore", True) is not False):
            out.add(int(iid))
    return frozenset(out)


def damage_bucket(ap_share):
    """'AD' / 'mixed' / 'AP' for an enemy team's magic-damage share, or None if unknown."""
    if ap_share is None:
        return None
    lo, hi = AP_EDGES
    return "AD" if ap_share < lo else ("AP" if ap_share > hi else "mixed")


def patch_key(patch):
    """'16.19' -> (16, 19) so patches sort numerically ('16.9' < '16.19')."""
    try:
        return tuple(int(x) for x in str(patch).split(".")[:2])
    except ValueError:
        return (0, 0)


def open_db(path=None, write=False):
    """A connection to the match database. Writers create it (WAL mode, so the app can keep
    reading while the collector writes); readers open it read-only and get None if it isn't
    there yet."""
    path = path or DB_PATH
    if write:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        con = sqlite3.connect(path, timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        return con
    if not os.path.exists(path):
        return None
    uri = "file:" + os.path.abspath(path).replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5, check_same_thread=False)


# ---------- the read side: cached per process ----------
class _Data:
    """Everything recommend_next needs from one database file, loaded lazily and kept for the
    life of the process (a widget session). Per champion + role it holds weighted
    (games, wins) counts at the three levels, keyed by slot."""

    def __init__(self, con):
        self.con = con
        self.lock = threading.Lock()
        self._profiles = None
        self._weights = None
        self._tables = {}

    def profiles(self):
        """{champ_id: share of its damage to champions that is magic}."""
        if self._profiles is None:
            rows = self.con.execute("SELECT champ, SUM(phys), SUM(magic) FROM participants "
                                    "GROUP BY champ").fetchall()
            self._profiles = {c: (m / float(p + m)) for c, p, m in rows if (p or 0) + (m or 0) > 0}
        return self._profiles

    def weights(self):
        """{patch: weight}: the newest patch in the data 1.0, each older one PATCH_DECAY less."""
        if self._weights is None:
            pats = [r[0] for r in self.con.execute("SELECT DISTINCT patch FROM decisions")]
            pats.sort(key=patch_key, reverse=True)
            self._weights = {p: PATCH_DECAY ** i for i, p in enumerate(pats)}
        return self._weights

    def enemy_share(self, champs):
        prof = self.profiles()
        vals = [prof[c] for c in champs if c in prof]
        return sum(vals) / len(vals) if vals else None

    def table(self, champ, role):
        key = (champ, role)
        with self.lock:
            if key in self._tables:
                return self._tables[key]
            w = self.weights()
            t = {"slot": {}, "bucket": {}, "opp": {}, "n": {}}
            rows = self.con.execute("SELECT slot, item, opp, enemies, patch, win FROM decisions "
                                    "WHERE champ = ? AND role = ?", (champ, role)).fetchall()
            for slot, item, opp, enemies, patch, win in rows:
                wt = w.get(patch, 0.0)
                if wt <= 0:
                    continue
                ids = [int(x) for x in (enemies or "").split(",") if x]
                b = damage_bucket(self.enemy_share(ids))
                for tab, k in (("slot", slot), ("bucket", (slot, b)), ("opp", (slot, b, opp))):
                    cell = t[tab].setdefault(k, {}).setdefault(item, [0.0, 0.0, 0])
                    cell[0] += wt
                    cell[1] += wt * (1 if win else 0)
                    cell[2] += 1
                t["n"][slot] = t["n"].get(slot, 0) + 1
            self._tables[key] = t
            return t


_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _data(path):
    path = os.path.abspath(path or DB_PATH)
    with _CACHE_LOCK:
        if path not in _CACHE:
            con = open_db(path)
            _CACHE[path] = _Data(con) if con else None
        return _CACHE[path]


def recommend_next(dd, champ, role, opp=None, enemies=(), owned=(), db_path=None, top=3):
    """The best legendaries to finish next, best first, as Rec(item, score, games, scope, why);
    [] whenever the local data can't speak (no database, champ + role not collected, thin slot).
    `owned` is every item id you hold now; your legendaries among them set the slot."""
    data = _data(db_path)
    if data is None or not champ or not role:
        return []
    legend = legendary_ids(dd)
    held = [i for i in owned if i in legend]
    slot = min(6, len(held) + 1)
    try:
        t = data.table(int(champ), role)
    except sqlite3.Error:
        return []
    if t["n"].get(slot, 0) < MIN_SLOT_GAMES:
        return []
    by_slot = t["slot"].get(slot) or {}
    total_g = sum(c[0] for c in by_slot.values())
    total_n = sum(c[2] for c in by_slot.values())
    if total_g <= 0:
        return []
    base = sum(c[1] for c in by_slot.values()) / total_g
    bucket = damage_bucket(data.enemy_share([int(e) for e in enemies if e]))
    by_bucket = (t["bucket"].get((slot, bucket)) or {}) if bucket else {}
    by_opp = (t["opp"].get((slot, bucket, int(opp))) or {}) if (bucket and opp) else {}
    names = dd.get("id2name") or {}

    def shrink(cell, prior):
        return (cell[1] + M_PRIOR * prior) / (cell[0] + M_PRIOR) if cell else prior

    out = []
    for item, c2 in by_slot.items():
        if item in owned or item not in legend:
            continue
        if c2[2] < MIN_ITEM_GAMES or c2[2] < MIN_ITEM_SHARE * total_n:
            continue
        p2 = shrink(c2, base)
        c1, c0 = by_bucket.get(item), by_opp.get(item)
        p1 = shrink(c1, p2) if bucket else p2
        p0 = shrink(c0, p1) if (bucket and opp) else p1
        if c0 and c0[2] >= MIN_SCOPE_GAMES:
            games, scope = c0[2], f"vs {names.get(int(opp), 'your opponent')}"
        elif c1 and c1[2] >= MIN_SCOPE_GAMES:
            games, scope = c1[2], f"vs {bucket} comps"
        else:
            games, scope = c2[2], f"as {names.get(int(champ), 'this champion')} {role}"
        out.append(Rec(item, p0, games, scope, f"{p0:.0%} in {games} games {scope}"))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top]


def reset_cache():
    """Forget loaded databases (tests; or after the collector rewrote the file)."""
    with _CACHE_LOCK:
        for d in _CACHE.values():
            if d is not None:
                try:
                    d.con.close()
                except Exception:
                    pass
        _CACHE.clear()


if __name__ == "__main__":                 # python lolrecommend.py Ahri mid [--vs X] [--enemies ...]
    import argparse
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lolbuild as lb
    ap = argparse.ArgumentParser(description="Next legendary from the local match data.")
    ap.add_argument("champ")
    ap.add_argument("role", choices=("top", "jungle", "mid", "adc", "support"))
    ap.add_argument("--vs", default="", help="your lane opponent")
    ap.add_argument("--enemies", default="", help="comma-separated enemy champions")
    ap.add_argument("--owned", default="", help="comma-separated items you already finished")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    dd = lb.ddragon()
    cid = lambda n: dd["name2id"].get(dd["norm"](n)) if n else None
    by_name = {dd["norm"](v): k for k, v in dd["items"].items()}
    owned = [by_name.get(dd["norm"](x)) for x in a.owned.split(",") if x.strip()]
    recs = recommend_next(dd, cid(a.champ), a.role, opp=cid(a.vs),
                          enemies=[cid(x) for x in a.enemies.split(",") if x.strip()],
                          owned=[o for o in owned if o], db_path=a.db)
    if not recs:
        print("no recommendation: the local data is too thin for this champion / role / slot "
              f"(database: {a.db or DB_PATH})")
    for r in recs:
        print(f"  {dd['items'].get(r.item, r.item):28} {r.why}")
