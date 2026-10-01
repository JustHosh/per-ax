#!/usr/bin/env python3
"""collector.py - gather ranked games from match-v5 into the SQLite file the next-item
recommender (core/lolrecommend.py) learns from.

    python tools\\collector.py crawl --tier EMERALD --division I II [--max-matches 3000]
    python tools\\collector.py status
    python tools\\collector.py purge --keep-patches 3

Pipeline - resumable: stop it whenever you like, the next run continues where it left off.
  1. league-v4: ladder entries for the tiers/divisions you ask for -> seed players (PUUIDs).
  2. match-v5 ids: each seed's recent ranked solo/duo games (queue 420).
  3. match-v5 match + timeline: per game, one row per player (champion, role, lane opponent,
     result, physical/magic damage to champions) and one row per COMPLETED LEGENDARY - the
     decision the recommender learns: slot, minute, what that player, their lane opponent and
     the enemy team had already finished, and the gold/level gap to the opponent then.
Nothing identifying the players in those games is stored (no names, no PUUIDs); only the seed
list keeps ladder PUUIDs, so a crawl can resume.

Rate limits: a development key allows 20 requests/s and 100 per 2 minutes (about 1,300 games
an hour at best) and expires every 24 h. The limiter follows Riot's own X-App-Rate-Limit /
X-Method-Rate-Limit headers - and their -Count twins, so the app's scout using the same key is
accounted for - and honors Retry-After on 429. When the key is rejected it stops cleanly:
paste a fresh one and run the same command again.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in ("core", "ui", "tools"):
    sys.path.insert(0, os.path.join(_ROOT, _d))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import lolbuild as lb
import lolrecommend as lr
import smiteconfig as cfg

QUEUE, QUEUE_ID = "RANKED_SOLO_5x5", 420
TIERS = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND",
         "MASTER", "GRANDMASTER", "CHALLENGER")
APEX = {"MASTER": "masterleagues", "GRANDMASTER": "grandmasterleagues",
        "CHALLENGER": "challengerleagues"}
DIVISIONS = ("I", "II", "III", "IV")
ROLE = {"TOP": "top", "JUNGLE": "jungle", "MIDDLE": "mid", "BOTTOM": "adc", "UTILITY": "support"}
MIN_DURATION = 600          # seconds: anything shorter is a remake, not a build decision
IDS_PER_SEED = 20
DEV_LIMITS = ((20, 1), (100, 120))   # a development key's app limits, until headers say otherwise
SAFETY = 0.9                # use this share of every limit: room for the app's scout on the same key


class KeyRejected(Exception):
    """Riot refused the key (expired development key, or a key for another product)."""


class Skip(Exception):
    """This match is not usable; the message says why."""


# ---------- rate limiting, driven by Riot's own headers ----------
class _Bucket:
    def __init__(self, limit, window):
        self.limit, self.window, self.q = limit, window, deque()

    def wait(self, now):
        """Seconds until one more request fits in this window (0 = now)."""
        while self.q and self.q[0] <= now - self.window:
            self.q.popleft()
        cap = max(1, int(self.limit * SAFETY))
        if len(self.q) < cap:
            return 0.0
        return self.q[len(self.q) - cap] + self.window - now + 0.05

    def sync(self, count, now):
        """The server counted more requests in this window than we did (another program on the
        same key): pad our record so the next waits are honest."""
        while len(self.q) < count:
            self.q.append(now)


class RateLimiter:
    """App-wide buckets plus one set per method (endpoint group), all from the headers."""

    def __init__(self, app=DEV_LIMITS, clock=time.monotonic, sleep=time.sleep):
        self.app = {w: _Bucket(n, w) for n, w in app}
        self.methods = {}
        self.clock, self.sleep = clock, sleep

    def _buckets(self, method):
        return list(self.app.values()) + list(self.methods.get(method, {}).values())

    def acquire(self, method):
        while True:
            now = self.clock()
            wait = max([b.wait(now) for b in self._buckets(method)] + [0.0])
            if wait <= 0:
                for b in self._buckets(method):
                    b.q.append(now)
                return
            self.sleep(wait)

    @staticmethod
    def _pairs(header):
        out = []
        for part in (header or "").split(","):
            n, _, w = part.strip().partition(":")
            if n.isdigit() and w.isdigit():
                out.append((int(n), int(w)))
        return out

    def update(self, method, headers):
        """Adopt the limits Riot reports, and its own counts of what was already spent."""
        if headers is None:
            return
        now = self.clock()
        for table, lim_h, cnt_h in ((self.app, "X-App-Rate-Limit", "X-App-Rate-Limit-Count"),
                                    (self.methods.setdefault(method, {}), "X-Method-Rate-Limit",
                                     "X-Method-Rate-Limit-Count")):
            pairs = self._pairs(headers.get(lim_h))
            if pairs:                     # the reported windows REPLACE the assumed ones (a
                keep = {w for _n, w in pairs}      # production key has 10s/600s, not 1s/120s)
                for w in [w for w in table if w not in keep]:
                    del table[w]
            for n, w in pairs:
                if w in table:
                    table[w].limit = n
                else:
                    table[w] = _Bucket(n, w)
            for c, w in self._pairs(headers.get(cnt_h)):
                if w in table:
                    table[w].sync(c, now)


# ---------- the Riot API, with retries ----------
class Riot:
    def __init__(self, key, platform, regional, limiter=None, opener=None):
        self.key, self.platform, self.regional = key, platform, regional
        self.limiter = limiter or RateLimiter()
        self.opener = opener or urllib.request.urlopen
        self.calls = 0
        self._auth_fails = 0

    def get(self, host, path, method):
        """Parsed JSON, or None for a 404 / unusable answer. Raises KeyRejected."""
        url = f"https://{host}.api.riotgames.com{path}"
        for attempt in range(6):
            self.limiter.acquire(method)
            req = urllib.request.Request(url, headers={"X-Riot-Token": self.key,
                                                       "User-Agent": lb.UA,
                                                       "Accept": "application/json"})
            self.calls += 1
            try:
                with self.opener(req, timeout=20) as r:
                    self.limiter.update(method, r.headers)
                    body = r.read()
                self._auth_fails = 0
                return json.loads(body.decode("utf-8")) if body else None
            except urllib.error.HTTPError as e:
                self.limiter.update(method, e.headers)
                if e.code == 429:
                    ra = (e.headers.get("Retry-After") if e.headers else None) or ""
                    self.limiter.sleep(float(ra) if ra.isdigit() else min(60, 2 ** attempt))
                    continue
                if e.code in (401, 403):
                    # 401 is final. A 403 can be a passing block on the regional host, so it
                    # takes three in a row (no success between) to call the key dead.
                    self._auth_fails += 1
                    if e.code == 401 or self._auth_fails >= 3:
                        raise KeyRejected(e.code)
                    self.limiter.sleep(1 + attempt)
                    continue
                if e.code >= 500:
                    self.limiter.sleep(min(30, 2 ** attempt))
                    continue
                return None                                  # 404 / 400: nothing to read
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                self.limiter.sleep(min(30, 2 ** attempt))
        raise RuntimeError(f"gave up on {path}")

    def ladder(self, tier, division, page):
        if tier in APEX:
            d = self.get(self.platform, f"/lol/league/v4/{APEX[tier]}/by-queue/{QUEUE}",
                         "league-v4.apex") if page == 1 else None
            return (d or {}).get("entries") or []
        return self.get(self.platform, f"/lol/league/v4/entries/{QUEUE}/{tier}/{division}"
                                       f"?page={page}", "league-v4.entries") or []

    def match_ids(self, puuid, start_time, count=IDS_PER_SEED):
        q = urllib.parse.urlencode({"queue": QUEUE_ID, "type": "ranked", "start": 0,
                                    "count": count, "startTime": int(start_time)})
        return self.get(self.regional, f"/lol/match/v5/matches/by-puuid/{puuid}/ids?{q}",
                        "match-v5.ids") or []

    def match(self, match_id):
        return self.get(self.regional, f"/lol/match/v5/matches/{match_id}", "match-v5.match")

    def timeline(self, match_id):
        return self.get(self.regional, f"/lol/match/v5/matches/{match_id}/timeline",
                        "match-v5.timeline")


# ---------- turning one game into rows (pure: the self-test drives it with fixtures) ----------
def patch_of(version):
    """'16.19.712.3456' -> '16.19'."""
    return ".".join(str(version or "").split(".")[:2])


def _ids(items):
    return ",".join(str(i) for i in sorted(items))


def _drop_last(seq, value):
    for k in range(len(seq) - 1, -1, -1):
        if seq[k] == value:
            del seq[k]
            return True
    return False


def precheck(match):
    """Raise Skip for a game the recommender can't learn from, BEFORE paying for its timeline."""
    info = (match or {}).get("info") or {}
    if info.get("queueId") != QUEUE_ID:
        raise Skip("not ranked solo/duo")
    if (info.get("gameDuration") or 0) < MIN_DURATION:
        raise Skip("remake / under 10 minutes")
    parts = info.get("participants") or []
    if len(parts) != 10:
        raise Skip("not 10 players")
    lanes = sorted(ROLE.values())
    for t in {p.get("teamId") for p in parts}:
        roles = [ROLE.get((p.get("teamPosition") or "").upper()) for p in parts
                 if p.get("teamId") == t]
        if None in roles or sorted(roles) != lanes:
            raise Skip("positions missing or not one per lane")
    return info


def extract(match, timeline, legend):
    """{'match', 'participants', 'decisions'} rows for one game. Raises Skip.

    The item replay follows the timeline: a legendary ITEM_PURCHASED is a decision (its slot is
    how many legendaries that player already held, +1); ITEM_UNDO takes the purchase (and its
    row) back, or a sale back; ITEM_SOLD / ITEM_DESTROYED remove it from the inventory."""
    info = precheck(match)
    mid = match["metadata"]["matchId"]
    patch = patch_of(info.get("gameVersion"))
    by_pid = {p["participantId"]: p for p in info["participants"]}
    team = {pid: p.get("teamId") for pid, p in by_pid.items()}
    role = {pid: ROLE[(p.get("teamPosition") or "").upper()] for pid, p in by_pid.items()}
    champ = {pid: int(p.get("championId") or 0) for pid, p in by_pid.items()}
    win = {pid: 1 if p.get("win") else 0 for pid, p in by_pid.items()}
    opp = {pid: next(q for q in by_pid if team[q] != team[pid] and role[q] == role[pid])
           for pid in by_pid}
    foes = {pid: [q for q in by_pid if team[q] != team[pid]] for pid in by_pid}
    enemies = {pid: _ids(champ[q] for q in foes[pid]) for pid in by_pid}
    frames = ((timeline or {}).get("info") or {}).get("frames") or []
    if not frames:
        raise Skip("no timeline")

    def stat(i, pid, k):
        return int((((frames[i].get("participantFrames") or {}).get(str(pid))) or {}).get(k) or 0)

    held = {pid: [] for pid in by_pid}
    rows = []
    for ev in (e for f in frames for e in (f.get("events") or [])):
        typ, pid = ev.get("type"), ev.get("participantId")
        if pid not in held:
            continue
        if typ == "ITEM_PURCHASED" and ev.get("itemId") in legend:
            item, ts = int(ev["itemId"]), int(ev.get("timestamp") or 0)
            i, o = min(len(frames) - 1, ts // 60000), opp[pid]
            rows.append({"match_id": mid, "pid": pid, "slot": min(6, len(held[pid]) + 1),
                         "champ": champ[pid], "role": role[pid], "opp": champ[o],
                         "enemies": enemies[pid], "item": item, "minute": round(ts / 60000.0, 2),
                         "prev": _ids(held[pid]), "opp_items": _ids(held[o]),
                         "enemy_items": _ids(x for q in foes[pid] for x in held[q]),
                         "gold_diff": stat(i, pid, "totalGold") - stat(i, o, "totalGold"),
                         "level_diff": stat(i, pid, "level") - stat(i, o, "level"),
                         "win": win[pid], "patch": patch})
            held[pid].append(item)
        elif typ == "ITEM_UNDO":
            before, after = ev.get("beforeId") or 0, ev.get("afterId") or 0
            if before in legend and _drop_last(held[pid], before):      # purchase taken back
                for k in range(len(rows) - 1, -1, -1):
                    if rows[k]["pid"] == pid and rows[k]["item"] == before:
                        del rows[k]
                        break
            if after in legend:                                          # sale taken back
                held[pid].append(after)
        elif typ in ("ITEM_SOLD", "ITEM_DESTROYED") and ev.get("itemId") in legend:
            _drop_last(held[pid], ev["itemId"])
    seq = {}
    for r in rows:
        seq[r["pid"]] = r["seq"] = seq.get(r["pid"], 0) + 1
    parts = [{"match_id": mid, "pid": pid, "team": team[pid], "champ": champ[pid],
              "role": role[pid], "opp": champ[opp[pid]], "win": win[pid],
              "phys": int(p.get("physicalDamageDealtToChampions") or 0),
              "magic": int(p.get("magicDamageDealtToChampions") or 0),
              "true_dmg": int(p.get("trueDamageDealtToChampions") or 0), "patch": patch}
             for pid, p in by_pid.items()]
    start = int(info.get("gameStartTimestamp") or info.get("gameCreation") or 0) // 1000
    return {"match": {"match_id": mid, "patch": patch, "game_start": start,
                      "duration": int(info.get("gameDuration") or 0)},
            "participants": parts, "decisions": rows}


def store(con, ex):
    """Write one extracted game and mark its match done (one transaction)."""
    m = ex["match"]
    with con:
        con.execute("DELETE FROM decisions WHERE match_id = ?", (m["match_id"],))
        con.executemany(
            "INSERT OR REPLACE INTO participants (match_id, pid, team, champ, role, opp, win, "
            "phys, magic, true_dmg, patch) VALUES (:match_id, :pid, :team, :champ, :role, :opp, "
            ":win, :phys, :magic, :true_dmg, :patch)", ex["participants"])
        con.executemany(
            "INSERT INTO decisions (match_id, pid, seq, slot, champ, role, opp, enemies, item, "
            "minute, prev, opp_items, enemy_items, gold_diff, level_diff, win, patch) VALUES "
            "(:match_id, :pid, :seq, :slot, :champ, :role, :opp, :enemies, :item, :minute, "
            ":prev, :opp_items, :enemy_items, :gold_diff, :level_diff, :win, :patch)",
            ex["decisions"])
        con.execute("INSERT INTO matches (match_id, status) VALUES (?, 'done') "
                    "ON CONFLICT(match_id) DO UPDATE SET status = 'done'", (m["match_id"],))
        con.execute("UPDATE matches SET patch = ?, game_start = ?, duration = ?, note = NULL, "
                    "done_at = ? WHERE match_id = ?",
                    (m["patch"], m["game_start"], m["duration"], int(time.time()),
                     m["match_id"]))


def _mark(con, match_id, status, note):
    with con:
        con.execute("UPDATE matches SET status = ?, note = ?, done_at = ? WHERE match_id = ?",
                    (status, note, int(time.time()), match_id))


# ---------- the crawl ----------
def _next_page(con, tiers, divisions, max_pages):
    """The next ladder page to read, round-robin over the requested tiers and divisions."""
    for page in range(1, max_pages + 1):
        for tier in tiers:
            for div in (("I",) if tier in APEX else divisions):
                if tier in APEX and page > 1:
                    continue
                got = con.execute("SELECT 1 FROM ladder_pages WHERE tier = ? AND division = ? "
                                  "AND page = ?", (tier, div, page)).fetchone()
                if not got:
                    return tier, div, page
    return None


def crawl(con, riot, legend, tiers, divisions, max_matches=0, days=21, max_pages=5,
          refresh_days=3, log=print):
    """Fill the database until max_matches new games are stored (0 = until the ladder pages
    run out). Returns the number of games stored in this run."""
    start_time = time.time() - days * 86400
    stored, t0 = 0, time.time()
    tier_sql = ",".join("?" * len(tiers))
    while not (max_matches and stored >= max_matches):
        row = con.execute("SELECT match_id FROM matches WHERE status = 'queued' "
                          "ORDER BY rowid LIMIT 1").fetchone()
        if row:
            mid = row[0]
            try:
                m = riot.match(mid)
                if not m:
                    raise Skip("not found")
                precheck(m)
                ex = extract(m, riot.timeline(mid), legend)
            except Skip as s:
                _mark(con, mid, "skipped", str(s))
                continue
            except RuntimeError as e:
                _mark(con, mid, "error", str(e)[:200])
                continue
            store(con, ex)
            stored += 1
            if stored % 10 == 0:
                rate = stored / max(1e-6, (time.time() - t0) / 3600.0)
                log(f"  {stored} partidas nuevas · {len(ex['decisions'])} decisiones en la "
                    f"última · {riot.calls} llamadas · ~{rate:.0f} partidas/h")
            continue
        due = time.time() - refresh_days * 86400
        seed = con.execute(f"SELECT puuid, tier FROM seeds WHERE tier IN ({tier_sql}) AND "
                           f"(ids_at IS NULL OR ids_at < ?) ORDER BY rowid LIMIT 1",
                           (*tiers, due)).fetchone()
        if seed:
            puuid, tier = seed
            ids = riot.match_ids(puuid, start_time)
            with con:
                con.executemany("INSERT OR IGNORE INTO matches (match_id, tier) VALUES (?, ?)",
                                [(i, tier) for i in ids])
                con.execute("UPDATE seeds SET ids_at = ? WHERE puuid = ?",
                            (int(time.time()), puuid))
            continue
        nxt = _next_page(con, tiers, divisions, max_pages)
        if nxt is None:
            log("Ya no quedan jugadores por leer en esas ligas (sube --pages para más).")
            break
        tier, div, page = nxt
        entries = riot.ladder(tier, div, page)
        seeds = [(e["puuid"], tier, div, int(time.time())) for e in entries if e.get("puuid")]
        with con:
            con.executemany("INSERT OR IGNORE INTO seeds (puuid, tier, division, added_at) "
                            "VALUES (?, ?, ?, ?)", seeds)
            con.execute("INSERT OR REPLACE INTO ladder_pages VALUES (?, ?, ?, ?, ?)",
                        (tier, div, page, int(time.time()), len(seeds)))
        log(f"Liga {tier} {div}, página {page}: {len(seeds)} jugadores")
    return stored


def status(con, dd, path):
    q = lambda sql, *a: con.execute(sql, a).fetchall()
    size = os.path.getsize(path) / 1e6 if os.path.exists(path) else 0
    print(f"Base de datos: {path} ({size:.1f} MB)")
    seeds, fetched = q("SELECT COUNT(*), COUNT(ids_at) FROM seeds")[0]
    print(f"Jugadores semilla: {seeds} (historial leído: {fetched})")
    st = dict(q("SELECT status, COUNT(*) FROM matches GROUP BY status"))
    print(f"Partidas: {st.get('done', 0)} guardadas · {st.get('queued', 0)} en cola · "
          f"{st.get('skipped', 0)} descartadas · {st.get('error', 0)} con error")
    print(f"Decisiones (legendarios terminados): {q('SELECT COUNT(*) FROM decisions')[0][0]}")
    pats = sorted(q("SELECT patch, COUNT(*) FROM matches WHERE status = 'done' GROUP BY patch"),
                  key=lambda r: lr.patch_key(r[0]), reverse=True)
    if pats:
        print("Parches: " + ", ".join(f"{p} ({n})" for p, n in pats[:6]))
    top = q("SELECT champ, role, COUNT(*) AS n FROM decisions WHERE slot = 1 "
            "GROUP BY champ, role ORDER BY n DESC LIMIT 12")
    if top:
        names = dd.get("id2name") or {}
        print(f"Más datos en el 1er objeto (hacen falta {lr.MIN_SLOT_GAMES} para recomendar):")
        for c, r, n in top:
            print(f"  {names.get(c, c):14} {r:8} {n}")


def purge(con, keep):
    pats = sorted({r[0] for r in con.execute("SELECT DISTINCT patch FROM matches "
                                             "WHERE patch IS NOT NULL")},
                  key=lr.patch_key, reverse=True)
    old = pats[keep:]
    if not old:
        print("Nada que borrar.")
        return
    marks = ",".join("?" * len(old))
    with con:
        for t in ("decisions", "participants", "matches"):
            con.execute(f"DELETE FROM {t} WHERE patch IN ({marks})", old)
    con.execute("VACUUM")
    print("Borrados los parches: " + ", ".join(old))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recolecta partidas ranked (match-v5) para el "
                                             "recomendador de objetos.")
    ap.add_argument("--db", default=lr.DB_PATH, help="archivo SQLite (por defecto en la carpeta "
                                                     "de datos de la app)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="leer ligas y guardar partidas")
    c.add_argument("--tier", nargs="+", default=["EMERALD"], type=str.upper, choices=TIERS)
    c.add_argument("--division", nargs="+", default=list(DIVISIONS), type=str.upper,
                   choices=DIVISIONS)
    c.add_argument("--max-matches", type=int, default=0, help="parar tras N partidas nuevas")
    c.add_argument("--days", type=int, default=21, help="solo partidas de los últimos N días")
    c.add_argument("--pages", type=int, default=5, help="páginas de liga por división (~205 "
                                                        "jugadores cada una)")
    c.add_argument("--region", default=None, help="plataforma (la1, na1, ...); por defecto la "
                                                  "de Ajustes")
    sub.add_parser("status", help="qué hay en la base")
    p = sub.add_parser("purge", help="borrar parches viejos")
    p.add_argument("--keep-patches", type=int, default=3)
    a = ap.parse_args(argv)

    con = lr.open_db(a.db, write=True)
    dd = lb.ddragon()
    if a.cmd == "status":
        status(con, dd, a.db)
        return 0
    if a.cmd == "purge":
        purge(con, a.keep_patches)
        return 0
    import lolscout as ls
    key = ls.read_key()
    if not key:
        print("Falta la clave de Riot: ponla en RIOT_API_KEY, en un .env o en Ajustes.")
        return 2
    platform, regional, _site = cfg.routing(a.region)
    riot = Riot(key, platform, regional)
    print(f"Región {platform} ({regional}) · ligas {', '.join(a.tier)} · divisiones "
          f"{', '.join(a.division)} · base {a.db}")
    print("Ctrl+C para parar; al volver a correrlo continúa donde se quedó.")
    try:
        n = crawl(con, riot, lr.legendary_ids(dd), a.tier, a.division,
                  max_matches=a.max_matches, days=a.days, max_pages=a.pages)
        print(f"Listo: {n} partidas nuevas.")
    except KeyRejected as e:
        print(f"Riot rechazó la clave (HTTP {e}). Las de desarrollo caducan cada 24 h: pega una "
              f"nueva y vuelve a correr el mismo comando.")
        return 2
    except KeyboardInterrupt:
        print("\nDetenido. Todo lo guardado se queda; vuelve a correrlo para continuar.")
    status(con, dd, a.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
