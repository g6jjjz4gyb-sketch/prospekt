#!/usr/bin/env python3
"""Check which chains are reachable from the machine this runs on.

The scraper was built on a home connection. Moving it to CI means running from
a datacenter IP, which Akamai treats very differently. Rather than assume,
this probes the one decisive request per chain and reports what actually
happens, so the architecture can follow the evidence.

    python tools/cloud_probe.py
"""
import asyncio, json, os, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from scrapers.base import Session
from scrapers import aldi_sued, edeka, http, netto, penny, rewe


async def probe_lidl():
    d = http.get_json(lidl_url(), timeout=45)
    n = len((d.get("flyer") or {}).get("products") or {})
    return n > 0, f"{n} Produkte im Prospekt"


def lidl_url():
    from scrapers.lidl import FLYER_API
    return FLYER_API.format("latest-leaflet-f5771509-f19a-11e9-b196-005056ab0fb6")


async def probe_penny(s):
    r = await s.api(f"{penny.BASE}/.rest/offers/by-category/"
                    f"{time.strftime('%G-%V')}/top-angebote")
    tiles = (r or {}).get("offerTiles") if isinstance(r, dict) else None
    return bool(tiles), f"{len(tiles)} Angebote" if tiles else str(r)[:90]


async def probe_aldi(s):
    r = await s.api(f"{aldi_sued.API}/v3/product-search?currency=EUR"
                    f"&serviceType=walk-in&categoryKey={aldi_sued.WEEKLY_CATEGORY}"
                    f"&limit=12&offset=0&servicePoint={aldi_sued.SERVICE_POINT}")
    if isinstance(r, dict) and "data" in r:
        n = r.get("meta", {}).get("pagination", {}).get("totalCount", 0)
        return True, f"{n} Wochenangebote"
    return False, str(r)[:90]


async def probe_rewe(s):
    await s.ctx.add_cookies([rewe.market_cookie("240259")])
    await s.goto(f"{rewe.BASE}/angebote/", settle=6000)
    n = await s.page.evaluate(
        "() => document.querySelectorAll('div.sos-offer').length")
    title = await s.page.title()
    return n > 0, f"{n} Angebote im DOM ({title[:40]})"


async def probe_edeka(s):
    await s.goto(f"{edeka.BASE}/angebote/", settle=5000)
    r = await s.api(edeka.OFFERS.format("8002364"))
    if isinstance(r, dict) and "docs" in r:
        return True, f"{len(r['docs'])} Angebote"
    return False, f"{(await s.page.title())[:40]} | {str(r)[:60]}"


async def probe_netto(s):
    await s.goto(f"{netto.SITE}/filialangebote", settle=5000)
    title = await s.page.title()
    if "Denied" in title or "denied" in title:
        return False, f"Access Denied ({title[:40]})"
    await s.api(f"{netto.ISHOP}/ViewMMPStoreFinder-AddStoreID?StoreID=3792")
    await s.goto(f"{netto.SITE}/filialangebote/1", settle=4000, cookies=False)
    n = await s.page.evaluate(
        "() => document.querySelectorAll('.product-list__item').length")
    return n > 0, f"{n} Kacheln ({title[:34]})"


BROWSER_PROBES = [("aldi_sued", probe_aldi), ("penny", probe_penny),
                  ("rewe", probe_rewe), ("edeka", probe_edeka),
                  ("netto", probe_netto)]


async def main():
    channel = os.environ.get("PROBE_CHANNEL") or None   # "chrome" locally
    results = {}

    t0 = time.time()
    try:
        ok, note = await probe_lidl()
    except Exception as e:
        ok, note = False, f"{type(e).__name__}: {e}"[:90]
    results["lidl"] = {"ok": ok, "note": note, "s": round(time.time() - t0, 1)}

    for name, fn in BROWSER_PROBES:
        t0 = time.time()
        try:
            async with Session(channel=channel) as s:
                if name in ("aldi_sued", "penny"):
                    await s.goto({"aldi_sued": "https://www.aldi-sued.de/angebote",
                                  "penny": f"{penny.BASE}/angebote"}[name], settle=5000)
                ok, note = await fn(s)
        except Exception as e:
            ok, note = False, f"{type(e).__name__}: {e}"[:90]
        results[name] = {"ok": ok, "note": note, "s": round(time.time() - t0, 1)}

    print("\n" + "=" * 68)
    print(f"{'Kette':12} {'Status':10} {'s':>6}  Befund")
    print("-" * 68)
    for k, v in results.items():
        print(f"{k:12} {'OK' if v['ok'] else 'BLOCKIERT':10} {v['s']:>6}  {v['note'][:40]}")
    n_ok = sum(1 for v in results.values() if v["ok"])
    print("-" * 68)
    print(f"{n_ok} von {len(results)} Ketten erreichbar")
    print(json.dumps(results, ensure_ascii=False))
    return 0 if n_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
