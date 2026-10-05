#!/usr/bin/env python3
"""Resolve every branch within the configured radius and cache it.

Branch lists change slowly and EDEKA's has to be scraped through its Marktsuche
UI, so this runs on demand rather than as part of the weekly refresh.

    python tools/resolve_markets.py            # refresh data/markets.json
"""
import argparse, asyncio, datetime as dt, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import markets
from scrapers.base import Session


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated chain ids")
    args = ap.parse_args()

    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    loc = cfg["location"]
    centre = (loc["lat"], loc["lon"])
    radius = loc["radius_km"]
    terms = loc.get("search_terms") or [loc["plz"]]
    br = cfg.get("browser", {})
    log = lambda m: print(m, flush=True)

    log(f"Märkte im Umkreis von {radius} km um {loc['plz']} {loc['city']}")
    prev = markets.load() or {}
    out = dict(prev.get("markets") or {})
    want = ({c.strip() for c in args.only.split(",")} if args.only
            else set(markets.RESOLVERS))
    async with Session(channel=br.get("channel"),
                       headless=br.get("headless", True)) as s:
        # LIDL runs last: it borrows the catchment towns the others resolved.
        order = [c for c in markets.RESOLVERS if c != "lidl"] + ["lidl"]
        for chain in order:
            if chain not in want:
                continue
            fn = markets.RESOLVERS[chain]
            try:
                if chain in ("rewe", "edeka"):
                    out[chain] = await fn(s, centre, radius, terms, log=log)
                elif chain == "lidl":
                    cities = {m.get("city") for c, v in out.items()
                              if c != "lidl" for m in v}
                    out[chain] = await fn(s, centre, radius, cities, log=log)
                else:
                    out[chain] = await fn(s, centre, radius, log=log)
            except Exception as e:
                log(f"  {chain}: FEHLER {type(e).__name__}: {e}")
                out.setdefault(chain, [])

    payload = {
        "resolved_at": dt.datetime.now().isoformat(timespec="seconds"),
        "centre": {"plz": loc["plz"], "city": loc["city"],
                   "lat": loc["lat"], "lon": loc["lon"]},
        "radius_km": radius,
        "markets": out,
    }
    markets.save(payload)
    total = sum(len(v) for v in out.values())
    log(f"\n{total} Märkte gespeichert in data/markets.json")
    for c, v in out.items():
        log(f"  {c:10} {len(v):3}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
