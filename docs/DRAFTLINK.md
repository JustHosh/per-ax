# DraftBoard — the Live Draft Link 🔗

In champ select, Smiteless posts **one short URL into the lobby chat** (and opens it for
you too). Anyone who clicks it — including the four random teammates who will never install
anything — lands on **DraftBoard**, a live web board of the current draft: both teams,
bans, and per-seat **champion suggestions with runes** for this exact game. They tap
**"This is me"** on their seat and get pick + rune cards that keep updating as the draft
evolves. No app, no account, no refresh.

**Total monthly cost: $0.** The page is static hosting (GitHub Pages), the live data
channel is Firebase's free Spark tier, and all art/names load from Riot's public ddragon
CDN in the viewer's browser. Smiteless only uploads a few KB of champion/rune IDs per
champ select.

```
you (Smiteless) ──publishes draft──▶ Firebase RTDB (free) ──streams──▶ teammates' browsers
        └──posts ONE short link in chat + opens it for you──▶ …github.io/smiteless/draft/#d=…
```

Out of the box every link carries `&db=<host>`, so the page knows which database to stream
from. To get the short form — just `…/draft/#d=<id>` — bake your Firebase host into your page:
set `loldraft._DEFAULT_PAGE_DB` and `DEFAULT_DB` in `docs/draft/index.html` to the same host
(both are empty in this fork). The chat post and whether it auto-opens for you are toggles in
Settings → CHAMP SELECT (`draft_msg` in the settings JSON overrides the message text).

**It becomes the scoreboard in-game.** During champ select the page shows the draft (picks,
bans, per-seat suggestions). The moment the game loads, `loldraft._scout_phase` PATCHes a
full scout onto the same node (`scout: {allies, enemies, plan, wincons}`) — rank, last-10
form, this-champ record, performance grade, and the profile-read tags for all ten — and the
page swaps to the scoreboard view. Same link, no refresh. It publishes public match-history
facts (names visible on the loading screen, ranks public on op.gg); nothing private. Turn
the whole feature off with the "Live draft link" toggle if you don't want to share it.

## One-time setup (~5 minutes)

The feature stays dormant until you give Smiteless BOTH a database to publish to and the URL
of your own hosted copy of the page.

### 1. Create a free Firebase Realtime Database

1. Go to [console.firebase.google.com](https://console.firebase.google.com) → **Create a
   project** (any name, e.g. `smiteless-draft`). Analytics off is fine.
2. In the left menu: **Build → Realtime Database → Create Database**. Pick the US region,
   start in **locked mode**.
3. Open the **Rules** tab and replace the rules with:

   ```json
   {
     "rules": {
       "drafts": {
         "$draft": {
           ".read": true,
           ".write": true,
           ".validate": "newData.hasChild('v') || newData.val() == null"
         }
       }
     }
   }
   ```

   Draft IDs are random and unguessable, the data is just champion IDs (nothing personal),
   and every draft is retired when champ select ends — open write on this one path is the
   price of running with zero servers and zero logins. Don't store anything else in this
   database.
4. Copy the database URL shown above the data tree — it looks like
   `https://smiteless-draft-default-rtdb.firebaseio.com`.

### 2. Host the page

The page itself is [`docs/draft/index.html`](draft/index.html), served by GitHub Pages from
YOUR repo: **Settings → Pages → Deploy from a branch → `main` / `docs`**. Its URL is
`https://<user>.github.io/<repo>/draft/`.

### 3. Paste both into Smiteless

Tray → **Settings** → **LIVE DRAFT LINK** → paste the **Database URL** and the **Page URL** →
**Save + test**. The test publishes a fake draft and opens the resulting page in your browser
— if you see the demo board go live, the whole pipeline works. The "Live draft link" checkbox
under CHAMP SELECT turns the chat post on/off.

## How it behaves

- Publishing starts when champ select opens and stops the moment it ends; the draft node
  is marked ended and deleted at the next lobby. Nothing runs between games.
- The link is posted **once** per champ select, after the first successful publish.
- Suggestions are the overlay's own pick brain (op.gg counters + comp fit) run for every
  seat — with **no mastery gate**, because these are for teammates whose champion pools
  are unknown. Your own overlay panel still applies your 12k-mastery climb guard.
- The viewer's browser streams changes over Firebase's SSE endpoint and falls back to
  7-second polling if streaming is blocked.
- Manual test any time: `python core\loldraft.py test`.

## Privacy — read before turning it on

- **During champ select** the published draft holds champion/rune/item IDs and role tags
  only: no names, no PUUIDs, no ranks. Enemy picks appear exactly as Riot exposes them there
  (locked champions only).
- **Once the game loads, the same page becomes a scoreboard for all ten players**: game name
  (without the tag), rank and LP, last-10 form, KDA, performance grade and profile tags such
  as `SMURF READ` or `tilt risk`. The database is public-read by design, so anyone holding the
  link can see that board.
- The link is also posted automatically, once per lobby, into champ-select chat.

Leave the feature off (it is off until you configure it) unless you are comfortable
publishing that about the other nine players.
