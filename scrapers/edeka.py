"""EDEKA -- offers are regional (Frankfurt is EDEKA Südwest).

The offers themselves come from a clean JSON service once you have a marketId.
There is no public market-search endpoint, so markets are resolved once by
driving the Marktsuche UI (which fans out to /api/market-gateway per hit) and
the chosen id is cached in config.json for later weekly runs.
"""
import datetime as dt

CHAIN = {"id": "edeka", "name": "EDEKA", "color": "#ffd200"}
BASE = "https://www.edeka.de"
OFFERS = BASE + "/eh/service/eh/offers?limit=999&marketId={}"
GATEWAY = BASE + "/api/market-gateway?marketId={}"


async def find_markets(s, plz, log=print):
    """Drive the Marktsuche UI and collect the marketIds it looks up."""
    ids = []

    async def on_resp(r):
        if "/api/market-gateway?marketId=" in r.url:
            mid = r.url.split("marketId=")[1].split("&")[0]
            if mid not in ids:
                ids.append(mid)

    s.page.on("response", lambda r: __import__("asyncio").create_task(on_resp(r)))
    await s.goto(f"{BASE}/marktsuche.jsp", settle=6000)
    # The visible search field sits under an activation overlay.
    await s.page.evaluate("""() => {
      const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      const a = [...document.querySelectorAll(
        '[data-element="m-store-search-input-field-dummy__activate"]')].filter(vis);
      if (a.length) { a[0].click(); return; }
      const i = [...document.querySelectorAll(
        'input[placeholder="Marktname oder Adresse"]')].filter(vis);
      if (i.length) i[0].focus();
    }""")
    await s.page.wait_for_timeout(2000)
    await s.page.keyboard.type(str(plz), delay=80)
    await s.page.wait_for_timeout(2500)
    await s.page.keyboard.press("Enter")
    await s.page.wait_for_timeout(9000)

    out = []
    for mid in ids[:25]:
        g = await s.api(GATEWAY.format(mid))
        if isinstance(g, dict) and g.get("id"):
            addr = (g.get("contact") or {}).get("address") or {}
            city = (addr.get("city") or {})
            out.append({"market_id": str(g["id"]), "name": g.get("name"),
                        "zip": city.get("zipCode"), "city": city.get("name"),
                        "channel": g.get("distributionChannelName"),
                        "region": g.get("region_abbreviation_keyword")})
    log(f"  edeka: {len(out)} markets near {plz}")
    return out


async def scrape(s, log=print, market_id=None, plz="60306"):
    if not market_id:
        markets = await find_markets(s, plz, log)
        if not markets:
            log("  edeka: no market resolved")
            return []
        market_id = markets[0]["market_id"]

    await s.goto(f"{BASE}/angebote/", settle=4000)
    g = await s.api(GATEWAY.format(market_id))
    market = g.get("name") if isinstance(g, dict) else None

    r = await s.api(OFFERS.format(market_id))
    if not isinstance(r, dict) or "docs" not in r:
        log(f"  edeka: offers call failed: {str(r)[:120]}")
        return []
    docs = r.get("docs") or []
    vfrom, vto = _d(r.get("gueltig_von")), _d(r.get("gueltig_bis"))
    log(f"  edeka: {len(docs)} offers | market {market_id} ({market}) | {vfrom} - {vto}")
    return [_norm(d, market, market_id, vfrom, vto) for d in docs]


def _d(ms):
    try:
        return dt.datetime.utcfromtimestamp(int(ms) / 1000).date().isoformat()
    except (TypeError, ValueError):
        return None


def _price(v):
    """EDEKA sends 0 for offers it publishes without a price (roughly 20 a week:
    ordinary cheese, sauces, Maultaschen). Treat that as unknown -- reading it
    as 0,00 EUR would file them as giveaways."""
    try:
        f = round(float(v), 2)
    except (TypeError, ValueError):
        return None
    return None if f == 0 else f


def _norm(d, market, market_id, vfrom, vto):
    labels = [x for x in [d.get("sonderkennzeichen"), d.get("nachlass"),
                          d.get("genussplus"), d.get("kriterien")] if x]
    return {
        "chain": CHAIN["id"],
        "title": (d.get("titel") or "").strip(),
        "brand": None,
        "quantity": (d.get("beschreibung") or "").strip() or None,
        "price": _price(d.get("preis")),
        "price_before": None,
        "base_price": d.get("basicPrice"),
        "discount": d.get("nachlass"),
        "image": d.get("bild_web130") or d.get("bild_app") or d.get("bild_web90"),
        "url": f"{BASE}/angebote/",
        "category": d.get("warengruppe") or "Angebote",
        "market": market,
        "market_id": market_id,
        "valid_from": vfrom,
        "valid_to": _d(d.get("gueltig_bis")) or vto,
        "national": bool(d.get("national")),
        "raw_labels": labels,
    }


async def scrape_all(s, market_list, log=print):
    """Offers across every EDEKA market, each tagged with the markets carrying it.

    EDEKA markets are run by different franchisees, so their offer sets really
    do differ; the service is cheap enough to ask each one directly.
    """
    if not market_list:
        return []
    await s.goto(f"{BASE}/angebote/", settle=4000)
    merged = {}
    for i, m in enumerate(market_list, 1):
        mid = m["market_id"]
        r = await s.api(OFFERS.format(mid))
        if not isinstance(r, dict) or "docs" not in r:
            log(f"    edeka: Markt {mid} nicht lesbar")
            continue
        vfrom, vto = _d(r.get("gueltig_von")), _d(r.get("gueltig_bis"))
        for d in r.get("docs") or []:
            key = d.get("angebotid") or (d.get("titel"), d.get("preis"))
            prev = merged.get(key)
            if prev is None:
                row = _norm(d, None, None, vfrom, vto)
                row["markets"] = [mid]
                row["offer_ref"] = str(d.get("angebotid") or "")
                merged[key] = row
            elif mid not in prev["markets"]:
                prev["markets"].append(mid)
        if i % 5 == 0 or i == len(market_list):
            log(f"    edeka: {i}/{len(market_list)} Märkte, {len(merged)} Angebote")
    out = []
    for row in merged.values():
        row["markets"] = sorted(row["markets"])
        out.append(row)
    log(f"  edeka: {len(out)} Angebote aus {len(market_list)} Märkten")
    return out
