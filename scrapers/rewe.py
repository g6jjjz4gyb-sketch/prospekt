"""REWE -- offers are market-specific and rendered client-side.

Selecting a market through the UI navigates, which trips REWE's Akamai
interstitial ("Nur einen Moment..."). So we resolve the market once via the
site's own fragment API, then inject the resulting `wksMarketsCookie` on later
runs and load the offers page directly -- no navigation, no challenge.
"""
import datetime as dt
import json, re, urllib.parse

CHAIN = {"id": "rewe", "name": "REWE", "color": "#cc071e"}
BASE = "https://www.rewe.de"
FRONTEND_INCLUDES = f"{BASE}/api/frontend-includes"
MARKET_LIST_ID = "d2688107-9c69-4e81-8b82-92da4adc97a6"


def market_cookie(ww_ident):
    val = urllib.parse.quote(json.dumps(
        {"stationary": {"wwIdent": str(ww_ident), "serviceTypes": ["STATIONARY"]}},
        separators=(",", ":")))
    return {"name": "wksMarketsCookie", "value": val,
            "domain": ".rewe.de", "path": "/"}


async def find_markets(s, plz):
    """Return [{ww_ident, name, address}] near a postcode, nearest first."""
    await s.goto(f"{BASE}/angebote/", settle=4000)
    payload = [{"id": MARKET_LIST_ID, "name": "wks-market-list",
                "namespace": "market-chooser",
                "query": {"searchTerm": str(plz), "page": "1", "longitude": None,
                          "latitude": None, "productId": "", "hasUserInteracted": "true"}}]
    r = await s.api(FRONTEND_INCLUDES, headers={"Content-Type": "application/json"},
                    method="POST", body=payload)
    if not isinstance(r, list) or not r:
        return []
    html = r[0].get("content", "")
    # The fragment renders each market as a block carrying its wwIdent.
    out, seen = [], set()
    for m in re.finditer(r'wwIdent["\\\s:=]+(\d{5,9})', html):
        ident = m.group(1)
        if ident in seen:
            continue
        seen.add(ident)
        window = html[m.start():m.start() + 1200]
        texts = [t.strip() for t in re.findall(r'>([^<>{}]{4,70})<', window)
                 if t.strip() and "wwIdent" not in t]
        name = next((t for t in texts if "REWE" in t), None)
        addr = next((t for t in texts if re.search(r'\d{5}\s+\w', t)), None)
        out.append({"ww_ident": ident, "name": name, "address": addr})
    return out


EXTRACT_JS = r"""
() => {
  const txt = (el) => (el ? (el.innerText || el.textContent || '').trim() : null);
  const eur = (t) => {
    if (!t) return null;
    const m = String(t).match(/(\d+),(\d{2})/);
    return m ? parseFloat(m[1] + '.' + m[2]) : null;
  };
  return [...document.querySelectorAll('div.sos-offer[data-rendered="true"]')].map(el => {
    const link  = el.querySelector('[data-testid="offer-title-link"]');
    const img   = el.querySelector('[data-testid="offer-image"]');
    const info  = [...el.querySelectorAll('.cor-offer-information__additional')]
                    .map(x => txt(x)).filter(Boolean);
    const label = txt(el.querySelector('.cor-offer-price__tag-label'));
    const price = txt(el.querySelector('.cor-offer-price__tag-price'));
    const block = txt(el.querySelector('.cor-offer-price'));
    // A crossed-out reference price, when present, is the other money value.
    let before = null;
    if (block) {
      const all = [...block.matchAll(/(\d+,\d{2})/g)].map(m => m[1]);
      const p = price ? price.match(/(\d+,\d{2})/) : null;
      const others = all.filter(a => !p || a !== p[1]);
      if (others.length) before = others[others.length - 1];
    }
    const joined = info.join(' ');
    const base = (joined.match(/\(([^)]*=\s*[\d,]+\s*€)\)/) || [])[1] || null;
    const dep  = (joined.match(/zzgl\.\s*([\d,]+)\s*€\s*Pfand/) || [])[1] || null;
    return {
      title: link ? (link.getAttribute('data-offer-title') || txt(link)) : txt(el.querySelector('h3')),
      info: joined || null,
      price: eur(price),
      price_before: eur(before),
      base_price: base,
      deposit: dep ? parseFloat(dep.replace(',', '.')) : null,
      label: label,
      image: img ? (img.getAttribute('src') || img.getAttribute('data-src')) : null,
      category: el.getAttribute('data-category'),
      nan: el.getAttribute('data-offer-nan'),
      wwident: el.getAttribute('data-offer-wwident'),
    };
  });
}"""


async def scrape(s, log=print, ww_ident=None, plz="60306"):
    if not ww_ident:
        markets = await find_markets(s, plz)
        if not markets:
            log("  rewe: no market found for " + str(plz))
            return []
        ww_ident = markets[0]["ww_ident"]
        log(f"  rewe: using market {ww_ident} ({markets[0].get('name')})")

    await s.ctx.add_cookies([market_cookie(ww_ident)])
    await s.goto(f"{BASE}/angebote/", settle=8000)

    # Offers hydrate on scroll; keep going until the rendered count settles.
    # Offers hydrate only once their tile intersects the viewport, and wheel
    # scrolling races that: a short page looks "finished" before the later
    # category sections have even been inserted. So do it in two deterministic
    # phases -- grow the page to its full height, then walk every tile into
    # view until none are left unrendered.
    async def counts():
        return await s.page.evaluate("""() => ({
            rendered: document.querySelectorAll(
                'div.sos-offer[data-rendered="true"]').length,
            total: document.querySelectorAll('div.sos-offer').length,
            height: document.body.scrollHeight,
        })""")

    stable, last_h = 0, -1
    for _ in range(40):
        await s.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await s.page.wait_for_timeout(700)
        c = await counts()
        stable = stable + 1 if c["height"] == last_h else 0
        last_h = c["height"]
        if stable >= 4:
            break

    last_n = -1
    for _ in range(60):
        c = await counts()
        if c["total"] and c["rendered"] >= c["total"]:
            break
        moved = await s.page.evaluate("""() => {
            const pending = [...document.querySelectorAll('div.sos-offer')]
              .filter(e => e.getAttribute('data-rendered') !== 'true');
            if (!pending.length) return 0;
            pending[0].scrollIntoView({block: 'center'});
            return pending.length;
        }""")
        if not moved:
            break
        await s.page.wait_for_timeout(600)
        if c["rendered"] == last_n:
            # No progress for a while: the remaining tiles are not going to load.
            stable += 1
            if stable > 24:
                break
        else:
            stable = 0
        last_n = c["rendered"]

    market = None
    try:
        market = (await s.page.title()).replace("Angebote im REWE Markt", "").strip()
    except Exception:
        pass
    rows = await s.page.evaluate(EXTRACT_JS)
    log(f"  rewe: {len(rows)} offers | market {ww_ident} | {market}")
    return [_norm(r, market) for r in rows if r.get("title")]


def _norm(r, market):
    return {
        "chain": CHAIN["id"],
        "title": r["title"],
        "brand": None,
        "quantity": r.get("info"),
        "price": r.get("price"),
        "price_before": r.get("price_before"),
        "base_price": r.get("base_price"),
        "discount": None,
        "deposit": r.get("deposit"),
        "image": r.get("image"),
        "url": f"{BASE}/angebote/",
        "category": (r.get("category") or "").replace("-", " ").title() or "Angebote",
        "market": market,
        "raw_labels": [x for x in [r.get("label")] if x],
    }


# --------------------------------------------------------------------------
# Multi-market scraping
#
# Loading a market's offers page costs ~8s, hydrating every tile ~47s. But the
# unhydrated DOM already carries each offer's article number (`data-offer-nan`)
# and category, so which offers a market has is cheap to read -- only the
# product details are expensive. So: fingerprint every market cheaply, then
# hydrate the smallest set of markets that covers every article seen.

FINGERPRINT_JS = """
() => {
  const els = [...document.querySelectorAll('div.sos-offer')];
  const out = {cats: {}, week: null};
  els.forEach(e => {
    const nan = e.getAttribute('data-offer-nan');
    if (!nan) return;
    out.cats[nan] = e.getAttribute('data-category') || null;
    out.week = out.week || e.getAttribute('data-offer-week');
  });
  return out;
}"""


# One tile's markup, fetched straight from the fragment API instead of waiting
# for the page to hydrate it. Scrolling 400 tiles into view took minutes and
# produced nothing at all on a CI runner, where the tiles never rendered.
DETAIL_JS = r"""
async ([url, items, ids]) => {
  const res = await fetch(url, {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(items),
  });
  if (!res.ok) return {__err: res.status};
  let data;
  try { data = await res.json(); } catch (e) { return {__err: 'parse'}; }
  const host = document.createElement('div');
  host.style.display = 'none';
  document.body.appendChild(host);
  const txt = (el) => (el ? (el.innerText || el.textContent || '').trim() : null);
  const eur = (t) => {
    if (!t) return null;
    const m = String(t).match(/(\d+),(\d{2})/);
    return m ? parseFloat(m[1] + '.' + m[2]) : null;
  };
  const out = {};
  (Array.isArray(data) ? data : []).forEach((frag, i) => {
    const nan = ids[i];
    if (!frag || !frag.content) return;
    host.innerHTML = frag.content;
    const link  = host.querySelector('[data-testid="offer-title-link"]');
    const img   = host.querySelector('[data-testid="offer-image"]');
    const info  = [...host.querySelectorAll('.cor-offer-information__additional')]
                    .map(x => txt(x)).filter(Boolean);
    const label = txt(host.querySelector('.cor-offer-price__tag-label'));
    const price = txt(host.querySelector('.cor-offer-price__tag-price'));
    const block = txt(host.querySelector('.cor-offer-price'));
    let before = null;
    if (block) {
      const all = [...block.matchAll(/(\d+,\d{2})/g)].map(m => m[1]);
      const p = price ? price.match(/(\d+,\d{2})/) : null;
      const others = all.filter(a => !p || a !== p[1]);
      if (others.length) before = others[others.length - 1];
    }
    const joined = info.join(' ');
    const title = link ? (link.getAttribute('data-offer-title') || txt(link))
                       : txt(host.querySelector('h3'));
    if (!title) return;
    const base = (joined.match(/\(([^)]*=\s*[\d,]+\s*€)\)/) || [])[1] || null;
    const dep  = (joined.match(/zzgl\.\s*([\d,]+)\s*€\s*Pfand/) || [])[1] || null;
    out[nan] = {
      title, info: joined || null, price: eur(price), price_before: eur(before),
      base_price: base, deposit: dep ? parseFloat(dep.replace(',', '.')) : null,
      label, image: img ? (img.getAttribute('src') || img.getAttribute('data-src')) : null,
      nan,
    };
  });
  host.remove();
  return out;
}"""


def _detail_items(nans, ww_ident, week):
    import uuid
    return [{"id": str(uuid.uuid4()), "name": "offer-tile-by-nan", "namespace": "cor",
             "params": {"nan": str(n), "wwIdent": str(ww_ident),
                        "heroStyles": "false", "showDuration": "auto",
                        "enableDetailDeeplink": "true", "week": week}}
            for n in nans]


async def fetch_details(s, nans, ww_ident, week, log=print, batch=15):
    """Offer details for a list of article numbers, via the fragment API."""
    out = {}
    nans = list(nans)
    for i in range(0, len(nans), batch):
        chunk = nans[i:i + batch]
        try:
            res = await s.page.evaluate(
                DETAIL_JS,
                [FRONTEND_INCLUDES, _detail_items(chunk, ww_ident, week), chunk])
        except Exception as e:
            log(f"    rewe: Detail-Abruf fehlgeschlagen ({type(e).__name__})")
            continue
        if isinstance(res, dict) and "__err" not in res:
            out.update(res)
        if (i // batch) % 5 == 4:
            log(f"    rewe: Details {len(out)}/{len(nans)}")
    return out


# Akamai answers some loads with an interstitial titled "Nur einen Moment…"
# instead of the page. It is intermittent -- from a datacenter IP it hit often
# enough to zero out a whole run, while a retry clears it. Treat it as a
# transient condition rather than an empty market.
INTERSTITIAL = "Nur einen Moment"


async def _open_market(s, ww_ident, settle=5000, tries=4):
    """Open a market's offers page, retrying past the bot interstitial."""
    for attempt in range(tries):
        await s.ctx.clear_cookies()
        await s.ctx.add_cookies([market_cookie(ww_ident)])
        await s.goto(f"{BASE}/angebote/", settle=settle + attempt * 2000)
        try:
            title = await s.page.title()
        except Exception:
            title = ""
        if INTERSTITIAL not in title:
            n = await s.page.evaluate(
                "() => document.querySelectorAll('div.sos-offer').length")
            if n:
                return True
        if attempt < tries - 1:
            await s.page.wait_for_timeout(3000 * (attempt + 1))
    return False


async def fingerprint(s, ww_ident):
    """Article numbers a market carries, without waiting for hydration."""
    if not await _open_market(s, ww_ident):
        return {}
    try:
        return await s.page.evaluate(FINGERPRINT_JS)
    except Exception:
        return {}


async def scrape_all(s, market_list, log=print):
    """Offers across every REWE market, each tagged with the markets carrying it.

    Two cheap passes instead of one expensive one: read every market's article
    numbers straight out of the unhydrated DOM, then pull each article's details
    once from the fragment API. No tile ever has to render, which is what made
    this slow locally and impossible on a CI runner, where they never render.
    """
    idents = [m["market_id"] for m in market_list]
    if not idents:
        return []

    by_market, cats, week, blocked = {}, {}, None, 0
    for i, ww in enumerate(idents, 1):
        fp = await fingerprint(s, ww)
        if not fp.get("cats"):
            blocked += 1
        else:
            by_market[ww] = set(fp["cats"])
            for nan, cat in fp["cats"].items():
                cats.setdefault(nan, cat)
            week = week or fp.get("week")
        if i % 15 == 0 or i == len(idents):
            log(f"    rewe: {i}/{len(idents)} Märkte erfasst")
    if blocked:
        log(f"    rewe: {blocked} Märkte nicht lesbar (Sperrseite)")
    if not by_market:
        log("  rewe: keine Angebote gefunden - vermutlich durchgehend gesperrt")
        return []

    union = sorted(set().union(*by_market.values()))
    week = week or dt.date.today().strftime("%G/%V")
    log(f"  rewe: {len(union)} Artikel in {len(by_market)} Märkten, Woche {week}")

    # Details do not vary by market; ask through the market carrying the most.
    anchor = max(by_market, key=lambda m: len(by_market[m]))
    details = await fetch_details(s, union, anchor, week, log=log)

    out = []
    for nan, r in details.items():
        markets = sorted(m for m, nans in by_market.items() if nan in nans)
        if not markets:
            continue
        row = _norm(r, None)
        row["category"] = (cats.get(nan) or "").replace("-", " ").title() or "Angebote"
        row["markets"] = markets
        row["offer_ref"] = nan
        out.append(row)
    missing = len(union) - len(out)
    log(f"  rewe: {len(out)} Angebote"
        + (f" ({missing} Artikel ohne Details)" if missing else ""))
    return out
