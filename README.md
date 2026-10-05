# Prospekt.Woche — Wochenangebote von sechs deutschen Supermarktketten

Scrapes the current weekly offers of **ALDI SÜD, LIDL, PENNY, REWE, EDEKA and
NETTO Marken-Discount** for Frankfurt am Main (PLZ 60306, 50 km radius),
classifies free / 1+1 / coupon / cashback promotions, and renders everything
into a single self-contained website that refreshes every Monday.

```bash
.venv/bin/python tools/resolve_markets.py   # branches in radius -> data/markets.json
.venv/bin/python run.py           # scrape all chains  -> data/latest.json
.venv/bin/python tools/images.py  # cache thumbnails   -> web/img/
.venv/bin/python build_site.py    # render the site    -> web/index.html
tools/refresh.sh                  # all three, as the scheduler runs them
```

Open `web/index.html` directly in a browser — the data is embedded, so it needs
no server and works offline.

## How each chain is read

None of the six publish an open offers feed, all six sit behind Akamai, and all
six render offers client-side. Each therefore gets the cheapest approach that
actually works, in `scrapers/`:

| Chain | Source | Notes |
|---|---|---|
| ALDI SÜD | `api.aldi-sued.de` product search | National — one merchant (`B384`) serves all of DE. Frankfurt is ALDI **SÜD** territory. |
| LIDL | `endpoints.leaflets.schwarz` flyer API | Plain HTTP, no browser needed. See coverage gap below. |
| PENNY | `penny.de/.rest/offers/by-category/<week>/<slug>` | Week code and category list are discovered from the page, not hard-coded. |
| REWE | Rendered offers page, market pinned by cookie | Market resolved once via REWE's own fragment API. |
| EDEKA | `edeka.de/eh/service/eh/offers?marketId=…` | Regional (Frankfurt = EDEKA Südwest). Market id cached in `config.json`. |
| NETTO | Rendered `/filialangebote` pages, store pinned via Intershop | Store finder takes a lat/lon bounding box. |

Two techniques do the heavy lifting:

- **In-page `fetch()`.** Chain APIs reject outside HTTP clients (403). Calling
  them from inside the chain's own page inherits its cookies, origin and TLS
  fingerprint, so they answer normally. See `Session.api` in `scrapers/base.py`.
- **Real Chrome, not bundled Chromium.** NETTO and EDEKA serve "Access Denied"
  to Playwright's Chromium but accept the installed Google Chrome
  (`channel="chrome"`). This is why Chrome must be present.

Consent banners are dismissed with the *privacy-preserving* option
("Nur notwendige erlauben") wherever the CMP offers one.

## Branches and market attribution

`tools/resolve_markets.py` resolves every branch within `radius_km` of the
configured centre into `data/markets.json` (currently 220 within 10 km of
Frankfurt). It runs on demand, not weekly — branch lists change slowly and
EDEKA's has to be driven through its Marktsuche UI.

| Chain | Branches | How they're found |
|---|---|---|
| REWE | 76 | Market-chooser fragment API — returns full JSON with coordinates |
| ALDI SÜD | 41 | `service-points` API, filtered by distance |
| PENNY | 34 | `/.rest/market` — all 2122 German markets with coordinates |
| LIDL | 30 | Store-page manifest; **no coordinates published** |
| NETTO | 25 | Store finder, queried with a lat/lon bounding box |
| EDEKA | 14 | Marktsuche UI, then `market-gateway` per id for coordinates |

Chains split into two groups, and `run.py` treats them differently:

- **Per market** (REWE, EDEKA, NETTO) — branches genuinely carry different
  assortments, so each is queried and every offer records which branches have
  it. This is not a small effect: the NETTO branch used previously carried 105
  offers where two others carried 291, and REWE markets ranged from 173 to 397.
  Scraping one branch under-reported all three chains badly.
- **One assortment for the region** (ALDI SÜD, LIDL, PENNY) — ALDI SÜD serves
  all of Germany from one merchant id, and 33 of the 34 PENNY markets share a
  `sellingRegion`. Their offers are attributed to every branch in the radius.

Clicking any offer opens a detail view listing the branches that carry it, with
distances.

LIDL is the one gap: it publishes no branch coordinates, so its branches are
matched by town — the towns the other chains' resolved markets already put
inside the radius — and shown without distances.

### Keeping it fast

Done naively this would take over two hours. Two observations cut it to ~18 min:

- **REWE's unhydrated DOM already names its offers.** Every `div.sos-offer`
  carries `data-offer-nan` before hydration, so *which* offers a market has
  costs ~8s while full details cost ~47s. All 76 markets are fingerprinted
  cheaply, then a greedy set cover picks the fewest markets that together
  contain every article — in practice 5 — and only those are hydrated.
- **NETTO needs no scrolling, and 20 of its 22 sub-pages are duplicates.** The
  tiles are server-rendered, and only `/filialangebote/1` and `/2` hold offers
  of their own; the rest are filtered views that add nothing. Two page loads
  per branch, with the finer section names collected once and reused.

## Product images

Every offer image is downloaded once, shrunk to a 200 px WebP thumbnail and
cached under `web/img/`, keyed by a hash of its source URL — a weekly refresh
only fetches what actually changed (all 1130 fit in ~3.3 MB).

Two reasons it works this way rather than hotlinking:

- **NETTO returns 403 to every direct image request.** Its images are pulled
  through a browser parked on netto-online.de, using the same in-page `fetch`
  trick as the offer APIs, then converted from a data URL.
- **A published Artifact cannot load external hosts at all.** `build_site.py`
  therefore inlines the thumbnails as data URIs, which is why `web/index.html`
  is ~5 MB. One file then behaves identically opened from disk, served, or
  published — and there is no `img/` folder to keep alongside it.

Cards are still typographic first: anything that fails to cache falls back to
its product group set in condensed type, so the grid keeps its shape.

## Product groups

The six chains name their rubrics differently ("Kuehlregal", "Molkerei & Käse",
"Milchprodukte & Eier") and about a third of them aren't product groups at all
but promotional buckets ("Super Wochenende", "Top Angebote"). `taxonomy.py`
maps everything onto ~19 shared groups that drive the category filter.

The rule is: trust the rubric when it carries product meaning, otherwise read
the product name. Three details that matter, all of them learned from wrong
answers:

- **Broad rubrics defer to the title.** "Getränke" holds both beer and water,
  so `SOFT` rubrics let the name decide first — otherwise Heineken files as a
  soft drink.
- **Short keywords need word boundaries, long ones must not have them.** As a
  plain substring "ei" fires inside *alkoholfrei* and "rum" inside *Premium*;
  but German compounds bury the useful word, so "milch" has to match inside
  *H-Vollmilch* and "chips" inside *Crunchips*. The split is at five characters.
- **Descriptions only get a say if the name says nothing.** A ketchup whose
  description mentions Tomaten is not produce.

Order encodes precedence too: fish before meat (so *Lachsfilet* beats the
generic "filet"), bakery before fruit (so *Apfeltasche* is a pastry).

Roughly 5–6 % of offers end up in "Sonstiges". `build_site.py` recomputes the
group at build time, so tuning `taxonomy.py` and re-running `build_site.py` is
enough — no re-scrape needed.

The free/cashback verdict is deliberately *not* recomputed at build time:
`run.py` classifies against the full advertising text, before it gets trimmed
for display, so re-running the classifier on the trimmed text would quietly
drop hits whose evidence sits past the trim. Changing the classifier means
re-scraping — `run.py --only <chain>` merges into the existing file, so it can
be done one chain at a time.

## Known coverage gap

**LIDL food offers are not machine-readable.** Only leaflet items that link to
an online-shop product carry structured data, which for LIDL DE means non-food
plus wine/beer/spirits. Weekly grocery offers exist on the leaflet pages as
images only. The website states this rather than quietly under-reporting LIDL.

## The free-offers section

`normalize.py` reads each offer's advertising text and sorts hits into four
tiers, most specific first — a bare "gratis" also appears inside "1+1 gratis"
and "gratis testen", which mean different things:

| Tier | Matches |
|---|---|
| `bogo` | 1+1, 2+1, 2 für 1, "nimm 3 zahl 2" |
| `cashback` | Geld-zurück, Cashback, "gratis testen", Produkttest, Erstattung |
| `coupon_free` | Gratis-Zugabe/dazu via App, Coupon or Payback |
| `free` | gratis, kostenlos, geschenkt, or a 0,00 € price |

Every hit stores the matching text as `free_evidence`, which the website shows
on the card, so the classification can be checked rather than trusted. Genuine
freebies are rare in German leaflets — a low count is a real result, and the
section says so instead of padding itself.

## Where this lives, and why not on the Desktop

The project sits in **`~/prospekt`**, with a symlink at
`~/Desktop/Claude/supermarkt` so it stays where you'd look for it.

It cannot live under `~/Desktop` (nor `~/Documents` or `~/Downloads`). Those are
TCC-protected: a launchd agent may list and even create files there, but every
*read* fails with `Operation not permitted`. The agent could not read its own
script, let alone `config.json` or the venv. This is silent — nothing appears in
the refresh log, only in `logs/launchd.err.log`.

## Weekly refresh

A LaunchAgent runs `tools/refresh.sh`:

- **Monday 06:30** — the regular slot.
- **Daily 12:30** and **at login** — catch-up. Both exit immediately unless the
  published data is older than the current ISO week, so they cost nothing on a
  normal day.

The catch-up exists because of how the 2026-08-31 run was missed: launchd
re-runs a job that was skipped while the Mac was *asleep*, but not one skipped
while it was *shut down* — and the Mac was off at 06:30 that Monday. Waking up
days later now repairs the gap on its own.

A lock file prevents overlapping runs (cleared automatically after two hours if
a run is killed). A failed scrape keeps the previous website rather than
publishing an empty one. Logs land in `logs/`, eight weeks retained.

```bash
launchctl list | grep prospekt                    # is it registered?
tools/refresh.sh --force                          # scrape now, ignore staleness
launchctl bootout gui/$UID/de.prospekt.weekly     # stop scheduling
rm ~/Library/LaunchAgents/de.prospekt.weekly.plist
```

## What runs where

The website is refreshed by **GitHub Actions**, so it stays current whether or
not this Mac is switched on — that was the whole point of moving it there.

| | |
|---|---|
| `.github/workflows/weekly.yml` | Mondays 05:20 UTC: scrapes all six chains, caches images, builds and publishes. |
| `tools/refresh.sh` on the Mac | Fallback. Asks the published page which week it is showing and exits if that is already current, so it normally does nothing. |
| `.github/workflows/probe.yml` | Manual. Reports which chains answer from a runner, compares REWE strategies. |

### Running from a datacenter IP

The scraper was built on a home connection, and the assumption that Akamai
would block CI outright turned out to be wrong — `tools/cloud_probe.py`
measured it. Two findings shaped the setup:

- **All six chains answer a GitHub runner, but only through real Chrome.** With
  Playwright's bundled Chromium, EDEKA and NETTO return "Access Denied" there
  exactly as they do locally. What is being scored is the browser fingerprint,
  not the datacenter IP — so `playwright install chrome` is a hard requirement
  of the workflow, not a nicety.
- **REWE tiles never render on a runner.** The first cloud run read all 436
  article numbers and still produced zero offers: the article numbers sit in
  the unhydrated DOM, but the tile *contents* are injected afterwards, and that
  injection simply never completed in CI. Scrolling 400 tiles into view took 34
  minutes and yielded nothing.

  The fix was to stop relying on rendering at all. Watching the network during
  hydration showed each tile being filled by a `POST /api/frontend-includes`
  with `{"name": "offer-tile-by-nan", "params": {"nan", "wwIdent", "week"}}` —
  the same fragment API the market chooser uses. `fetch_details` now requests
  those fragments directly, 15 at a time, and parses them in a detached element.
  Three markets went from one market per 47 s to 380 offers in 47 s, and REWE
  works in CI: 417 offers.

- **REWE also serves an intermittent interstitial** titled "Nur einen Moment…".
  `_open_market` detects that title and retries, and the run now reports how
  many markets stayed blocked instead of quietly returning nothing.

Everything else stays identical between Mac and runner — same scrapers, same
`run.py`, same `build_site.py`.

## Publishing to the web

`tools/publish.sh` pushes `web/index.html` to GitHub Pages at the end of every
refresh; until it is set up it exits quietly, so a refresh never fails for want
of publishing. One-time setup:

```bash
gh auth login && tools/setup_pages.sh
```

Live at **https://g6jjjz4gyb-sketch.github.io/prospekt/** (account
`g6jjjz4gyb-sketch`, repo `prospekt`, set up 2026-09-02).

Two branches, deliberately: `main` holds the source and the workflows,
`gh-pages` holds the built site. Each publish *replaces* `gh-pages` with one
fresh commit — the page is a single ~10 MB file rewritten weekly, so keeping
its history would grow the repository by that much every week, and
force-pushing a shared branch would delete the source along with it.

The page also judges its own freshness in the viewer's browser: if the data is
from an earlier ISO week it shows a red "Veraltet" strip saying how many days
old it is, instead of going on promising a refresh that has already been
missed — which is exactly what it did for the month the Mac was switched off.

The scraping stays on this Mac by necessity: the chains sit behind Akamai,
which blocks datacenter IPs, and the whole approach depends on a real local
Chrome. Only the finished 9 MB HTML file is uploaded.

Because that file is rewritten in full every week, each publish **replaces** the
branch with a single fresh commit rather than adding to its history — otherwise
the repository would grow by 9 MB a week. On a free GitHub account a Pages site
is public; anyone with the URL can read it.

## Changing the location

Edit `config.json`. `plz`, `city`, `lat`, `lon` and `radius_km` drive store
selection; NETTO resolves its store from the coordinates on every run.

REWE and EDEKA cache a market id, because neither exposes a market-search API
that can be called directly. Clear them to re-resolve through the site's UI:

```json
"markets": { "rewe_ww_ident": null, "edeka_market_id": null, "netto_store_id": null }
```

Both then re-resolve automatically from `plz` on the next run; note the ids the
run logs and paste them back to keep later runs fast.

## Layout

```
config.json          location, cached market ids, browser settings
run.py               orchestrator; one browser context per chain
normalize.py         unified schema, label cleanup, free/cashback classifier
taxonomy.py          maps each chain's rubrics onto shared product groups
build_site.py        renders data/latest.json into web/index.html
tools/images.py      downloads, shrinks and caches every offer thumbnail
scrapers/base.py     browser session: consent, scrolling, in-page fetch
scrapers/http.py     curl-backed fetcher for the browser-free sources
scrapers/*.py        one module per chain, each exposing scrape() + CHAIN
data/                latest.json plus one archived file per ISO week
web/img/             cached WebP thumbnails, reused across weeks
web/index.html       the generated website
```

## Fragility

These are scrapers against sites that owe us nothing. Markup and endpoints will
change. `run.py` isolates each chain: one failure is recorded in the run summary
and shown on the website as "nicht erreichbar", and the other five still
publish. Check `logs/` when a chain's count drops to zero.
