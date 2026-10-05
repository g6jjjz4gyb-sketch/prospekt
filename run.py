#!/usr/bin/env python3
"""Scrape the weekly offers of six German grocery chains into one JSON file.

Each chain runs in its own browser context: REWE and NETTO both pin a store
through cookies, and sharing a context would leak one chain's market into the
next. A chain that fails is recorded in `sources` and the run continues -- a
broken site should cost one section of the website, not the whole page.

    python run.py            # scrape everything, write data/latest.json
    python run.py --only rewe,penny
"""
import argparse, asyncio, datetime as dt, json, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from scrapers.base import Session
from scrapers import aldi_sued, edeka, lidl, netto, penny, rewe
import markets as markets_mod
import normalize

MODULES = {m.CHAIN["id"]: m for m in (aldi_sued, lidl, penny, rewe, edeka, netto)}
DATA = os.path.join(HERE, "data")

# Chains whose offers genuinely differ from branch to branch. The rest publish
# one assortment for the whole area, so their offers apply to every branch of
# that chain inside the radius.
PER_MARKET = {"rewe", "edeka", "netto"}


def load_config():
    with open(os.path.join(HERE, "config.json")) as f:
        return json.load(f)


def kwargs_for(chain, cfg):
    loc, mk = cfg["location"], cfg.get("markets", {})
    if chain == "rewe":
        return {"ww_ident": mk.get("rewe_ww_ident"), "plz": loc["plz"]}
    if chain == "edeka":
        return {"market_id": mk.get("edeka_market_id"), "plz": loc["plz"]}
    if chain == "netto":
        return {"store_id": mk.get("netto_store_id"), "lat": loc["lat"],
                "lon": loc["lon"], "radius_km": loc["radius_km"], "plz": loc["plz"]}
    return {}


async def run_chain(chain, cfg, log, chain_markets):
    mod = MODULES[chain]
    br = cfg.get("browser", {})
    t0 = dt.datetime.now()
    try:
        async with Session(channel=br.get("channel"),
                           headless=br.get("headless", True),
                           capture=(chain == "penny")) as s:
            if chain in PER_MARKET and chain_markets:
                rows = await mod.scrape_all(s, chain_markets, log=log)
            else:
                rows = await mod.scrape(s, log=log, **kwargs_for(chain, cfg))
                # One assortment for the whole area: it applies everywhere.
                ids = [m["market_id"] for m in chain_markets]
                for r in rows:
                    r["markets"] = list(ids)
    except Exception as e:
        log(f"  {chain}: FAILED {type(e).__name__}: {e}")
        traceback.print_exc(limit=2)
        return chain, [], {"ok": False, "error": f"{type(e).__name__}: {e}",
                           "count": 0, "seconds": 0}
    secs = round((dt.datetime.now() - t0).total_seconds(), 1)
    rows = [normalize.finalize(r) for r in rows if r.get("title")]
    return chain, rows, {"ok": True, "count": len(rows), "seconds": secs,
                         "per_market": chain in PER_MARKET,
                         "markets": len(chain_markets),
                         "note": getattr(mod, "COVERAGE_NOTE", None)}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated chain ids")
    ap.add_argument("--out", default=os.path.join(DATA, "latest.json"))
    args = ap.parse_args()

    cfg = load_config()
    chains = [c for c in cfg["chains"] if c in MODULES]
    if args.only:
        want = {c.strip() for c in args.only.split(",")}
        chains = [c for c in chains if c in want]

    os.makedirs(DATA, exist_ok=True)
    log = lambda m: print(m, flush=True)

    mk = markets_mod.load()
    if not mk:
        print("data/markets.json fehlt - bitte zuerst "
              "'python tools/resolve_markets.py' laufen lassen.", file=sys.stderr)
        return 2
    by_chain = mk["markets"]
    log(f"{sum(len(v) for v in by_chain.values())} Märkte im Umkreis von "
        f"{mk['radius_km']} km (Stand {mk['resolved_at'][:10]})")
    started = dt.datetime.now()
    log(f"Scraping {len(chains)} chains for {cfg['location']['plz']} "
        f"{cfg['location']['city']} at {started:%Y-%m-%d %H:%M}")

    offers, sources = [], {}
    for chain in chains:
        log(f"[{chain}]")
        name, rows, meta = await run_chain(chain, cfg, log,
                                           by_chain.get(chain, []))
        meta["name"] = MODULES[chain].CHAIN["name"]
        meta["color"] = MODULES[chain].CHAIN["color"]
        sources[name] = meta
        offers.extend(rows)

    # A partial run (--only) must fold into the existing file: replacing it
    # would silently drop every chain that wasn't scraped this time.
    if args.only and os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, ValueError):
            prev = None
        if prev:
            done = set(sources)
            kept = [o for o in prev.get("offers", []) if o.get("chain") not in done]
            offers = kept + offers
            merged = dict(prev.get("sources") or {})
            merged.update(sources)
            sources = merged
            log(f"  ({len(kept)} Angebote der übrigen Ketten übernommen)")

    offers.sort(key=normalize.sort_key)
    free = [o for o in offers if o.get("free_tier")]
    iso = started.isocalendar()
    payload = {
        "generated_at": started.isoformat(timespec="seconds"),
        "iso_week": f"{iso[0]}-W{iso[1]:02d}",
        "location": cfg["location"],
        "sources": sources,
        "markets": by_chain,
        "markets_resolved_at": mk.get("resolved_at"),
        "radius_km": mk.get("radius_km"),
        "counts": {"total": len(offers), "free": len(free),
                   "by_tier": {t: sum(1 for o in free if o["free_tier"] == t)
                               for t in ("free", "bogo", "coupon_free", "cashback")}},
        "offers": offers,
    }
    for path in (args.out, os.path.join(DATA, f"offers-{payload['iso_week']}.json")):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    log("\n" + "-" * 58)
    for c, m in sources.items():
        if m["ok"]:
            scope = (f"{m['markets']:>3} Märkte einzeln" if m.get("per_market")
                     else f"{m['markets']:>3} Märkte, ein Sortiment")
            state = f"{m['count']:>5} Angebote  {m['seconds']:>6}s  {scope}"
        else:
            state = f"  FEHLER  {m['error'][:40]}"
        log(f"  {m['name'][:24]:26} {state}")
    log(f"  {'TOTAL':26} {len(offers):>5} offers | {len(free)} free/cashback")
    log(f"  written to {args.out}")
    return 0 if any(m["ok"] for m in sources.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
