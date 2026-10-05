#!/usr/bin/env python3
"""Find a way to read many REWE markets from a datacenter IP.

REWE serves the first page load fine and then answers "Nur einen Moment…"
(Akamai's interstitial) for the rest of the session. Four strategies are tried
over the same six markets so the fix follows measurement rather than a guess.
"""
import asyncio, os, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from scrapers.base import Session
from scrapers import rewe

MARKETS = ["240259", "241182", "240798", "230494", "240507", "240460"]
CHANNEL = os.environ.get("PROBE_CHANNEL") or None
BLOCKED = "Nur einen Moment"


async def count(page):
    return await page.evaluate(
        "() => document.querySelectorAll('div.sos-offer').length")


async def strat_naive(log):
    async with Session(channel=CHANNEL) as s:
        ok = 0
        for ww in MARKETS:
            await s.ctx.clear_cookies()
            await s.ctx.add_cookies([rewe.market_cookie(ww)])
            await s.goto(f"{rewe.BASE}/angebote/", settle=4000)
            n = await count(s.page)
            ok += n > 0
            log(f"      {ww}: {n:4}  {(await s.page.title())[:28]}")
        return ok


async def strat_slow(log, pause=9000):
    async with Session(channel=CHANNEL) as s:
        ok = 0
        for ww in MARKETS:
            await s.ctx.clear_cookies()
            await s.ctx.add_cookies([rewe.market_cookie(ww)])
            await s.goto(f"{rewe.BASE}/angebote/", settle=4000)
            n = await count(s.page)
            ok += n > 0
            log(f"      {ww}: {n:4}  {(await s.page.title())[:28]}")
            await s.page.wait_for_timeout(pause)
        return ok


async def strat_fresh_context(log):
    """New browser context per market: fresh cookie jar and Akamai sensor."""
    ok = 0
    for ww in MARKETS:
        async with Session(channel=CHANNEL) as s:
            await s.ctx.add_cookies([rewe.market_cookie(ww)])
            await s.goto(f"{rewe.BASE}/angebote/", settle=4000)
            n = await count(s.page)
            ok += n > 0
            log(f"      {ww}: {n:4}  {(await s.page.title())[:28]}")
    return ok


async def strat_retry(log, tries=3):
    """Stay in one session, but reload when the interstitial appears."""
    async with Session(channel=CHANNEL) as s:
        ok = 0
        for ww in MARKETS:
            await s.ctx.clear_cookies()
            await s.ctx.add_cookies([rewe.market_cookie(ww)])
            n, title = 0, ""
            for attempt in range(tries):
                await s.goto(f"{rewe.BASE}/angebote/", settle=4000 + attempt * 3000)
                title = await s.page.title()
                if BLOCKED not in title:
                    n = await count(s.page)
                    if n:
                        break
                await s.page.wait_for_timeout(4000 * (attempt + 1))
            ok += n > 0
            log(f"      {ww}: {n:4}  {title[:28]}")
        return ok


STRATEGIES = [
    ("naiv (wie bisher)", strat_naive),
    ("9s Pause zwischen Märkten", strat_slow),
    ("neuer Browser-Kontext je Markt", strat_fresh_context),
    ("Neuladen bei Sperrseite", strat_retry),
]


async def main():
    log = lambda m: print(m, flush=True)
    results = {}
    for name, fn in STRATEGIES:
        log(f"\n=== {name}")
        t0 = time.time()
        try:
            ok = await fn(log)
        except Exception as e:
            log(f"      FEHLER {type(e).__name__}: {e}")
            ok = 0
        dt = round(time.time() - t0, 1)
        results[name] = (ok, dt)
        log(f"    -> {ok}/{len(MARKETS)} Märkte in {dt}s")

    print("\n" + "=" * 62)
    for name, (ok, dt) in results.items():
        per = round(dt / len(MARKETS), 1)
        print(f"  {ok}/{len(MARKETS)}  {per:>5}s/Markt   {name}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
