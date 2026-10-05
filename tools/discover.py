"""Load each chain's offer page in a real browser and log every JSON/XHR response."""
import asyncio, json, sys, re
from playwright.async_api import async_playwright

TARGETS = {
 "aldi_sued": "https://www.aldi-sued.de/angebote",
 "lidl":      "https://www.lidl.de/c/online-prospekte/s10005610",
 "penny":     "https://www.penny.de/angebote",
 "netto":     "https://www.netto-online.de/filialangebote",
 "rewe":      "https://www.rewe.de/angebote/",
 "edeka":     "https://www.edeka.de/angebote/index.jsp",
}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

async def run(name, url):
    hits = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        ctx = await b.new_context(user_agent=UA, locale="de-DE",
                                  viewport={"width":1440,"height":900},
                                  extra_http_headers={"Accept-Language":"de-DE,de;q=0.9"})
        pg = await ctx.new_page()

        async def on_resp(r):
            try:
                ct = (r.headers or {}).get("content-type","")
                if "json" in ct and r.status == 200:
                    body = await r.body()
                    if len(body) > 800:
                        hits.append({"url": r.url, "size": len(body),
                                     "req": r.request.method})
            except Exception:
                pass
        pg.on("response", lambda r: asyncio.create_task(on_resp(r)))

        try:
            await pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            # accept cookie banner if present
            for sel in ['button:has-text("Alle akzeptieren")','button:has-text("Akzeptieren")',
                        'button:has-text("Alle zulassen")','#onetrust-accept-btn-handler',
                        '[data-testid="uc-accept-all-button"]','button:has-text("Zustimmen")']:
                try:
                    el = pg.locator(sel).first
                    if await el.is_visible(timeout=1500):
                        await el.click(timeout=3000); break
                except Exception: pass
            await pg.wait_for_timeout(6000)
            for _ in range(4):
                await pg.mouse.wheel(0, 4000); await pg.wait_for_timeout(1500)
            title = await pg.title()
        except Exception as e:
            title = f"ERR {type(e).__name__}: {e}"
        await b.close()
    return title, hits

async def main():
    for name, url in TARGETS.items():
        title, hits = await run(name, url)
        print(f"\n{'='*70}\n### {name}  |  {title[:70]}")
        seen=set()
        for h in sorted(hits, key=lambda x:-x["size"])[:14]:
            u = h["url"].split("?")[0]
            if u in seen: continue
            seen.add(u)
            print(f"  {h['size']:>8}  {h['req']:4} {h['url'][:150]}")

asyncio.run(main())
