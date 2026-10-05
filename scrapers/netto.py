"""NETTO Marken-Discount -- Intershop storefront, offers are per store.

Store selection drives everything: the store finder takes a lat/lon bounding
box, and once a StoreID is registered the /filialangebote pages render that
store's weekly assortment. Each tile carries an "add to wishlist" link whose
query string is the offer in structured form, so we parse that rather than
scraping prices out of nested spans.
"""
import math, re, urllib.parse

CHAIN = {"id": "netto", "name": "NETTO Marken-Discount", "color": "#ffe500"}
SITE = "https://www.netto-online.de"
ISHOP = SITE + "/INTERSHOP/web/WFS/Plus-NettoDE-Site/de_DE/-/EUR"
BEVERAGE_STORE_TYPE = "4"        # Getränke-Discount, different assortment


def _km(lat1, lon1, lat2, lon2):
    return 111.0 * math.hypot(lat1 - lat2,
                              (lon1 - lon2) * math.cos(math.radians(lat1)))


async def find_stores(s, lat, lon, radius_km=50, log=print):
    """Store finder takes a bounding box, so derive one from centre + radius."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * math.cos(math.radians(lat)))
    body = (f"s={lat - dlat:.4f}&n={lat + dlat:.4f}"
            f"&w={lon - dlon:.4f}&e={lon + dlon:.4f}"
            "&netto=false&city=false&service=false&beverage=false&nonfood=false")
    r = await s.page.evaluate("""async ([url, body]) => {
        const res = await fetch(url, {method: 'POST', credentials: 'include',
          headers: {'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'}, body});
        try { return JSON.parse(await res.text()); } catch (e) { return {}; }
    }""", [f"{ISHOP}/ViewMMPStoreFinder-GetStoreItems", body])

    items = [i for i in (r.get("store_items") or [])
             if i.get("store_type_id") != BEVERAGE_STORE_TYPE]
    for i in items:
        try:
            i["distance_km"] = round(
                _km(lat, lon, float(i["coord_latitude"]), float(i["coord_longitude"])), 1)
        except (TypeError, ValueError, KeyError):
            i["distance_km"] = 9999
    items = [i for i in items if i["distance_km"] <= radius_km]
    items.sort(key=lambda i: i["distance_km"])
    log(f"  netto: {len(items)} stores within {radius_km} km")
    return items


EXTRACT_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('.product-list__item').forEach(el => {
    const a = el.querySelector('a[href*="ViewMMPWishlist-AddStoreArticle"]');
    if (!a) return;
    const pct = el.querySelector('.product__percent-saving__text');
    const old = el.querySelector('.product__old-price');
    // Tiles carry inline <style> blocks; innerText picks up the CSS, so read
    // from a cleaned clone instead.
    const clean = (node) => {
      if (!node) return '';
      const c = node.cloneNode(true);
      c.querySelectorAll('style,script').forEach(n => n.remove());
      return (c.innerText || '').replace(/\s+/g, ' ').trim();
    };
    const dist = [...el.querySelectorAll('.product__store-disturber-wrapper__item')]
                   .map(clean).filter(Boolean);
    out.push({
      href: a.getAttribute('href'),
      discount: pct ? pct.innerText.trim() : null,
      old_price: old ? old.innerText.trim() : null,
      disturbers: dist,
      full_text: clean(el).slice(0, 400),
    });
  });
  return out;
}"""


async def scrape(s, log=print, store_id=None, lat=50.1188, lon=8.6644,
                 radius_km=50, plz="60306"):
    await s.goto(f"{SITE}/filialangebote", settle=5000)

    store = None
    if not store_id:
        stores = await find_stores(s, lat, lon, radius_km, log)
        if not stores:
            log("  netto: no store found")
            return []
        store = stores[0]
        store_id = store["store_id"]
        log(f"  netto: using store {store_id} "
            f"({store.get('post_code')} {store.get('city')}, {store['distance_km']} km)")

    await s.api(f"{ISHOP}/ViewMMPStoreFinder-AddStoreID?StoreID={store_id}")
    await s.goto(f"{SITE}/filialangebote", settle=6000)

    pages = await s.page.evaluate(
        """() => [...new Set([...document.querySelectorAll('a')]
             .map(a => a.getAttribute('href') || '')
             .filter(h => /\\/filialangebote\\/\\d/.test(h)))]""")
    pages = [p if p.startswith("http") else SITE + p for p in pages]
    if not pages:
        pages = [f"{SITE}/filialangebote/1"]

    # /filialangebote/1 lists everything; the sub-pages are filtered views of
    # the same items under a specific heading. Keep one row per offer, but let
    # a specific section name win over the catch-all one.
    GENERIC = {"Wochenangebote", "Wochenendangebote", "Filial-Angebote"}
    rows, seen = [], {}
    for url in pages:
        try:
            await s.goto(url, settle=5000, cookies=False)
            await s.scroll_all(rounds=12)
            # Each sub-page's h1 names its section, e.g.
            # "Knüller der Woche gültig von Montag, 24.08.26 - ...".
            head = await s.page.evaluate(
                "() => { const h = document.querySelector('h1');"
                " return h ? h.innerText.trim() : ''; }")
            category = re.split(r"\s+g(ü|ue)ltig\s+(von|am|bis)", head)[0].strip() or None
            tiles = await s.page.evaluate(EXTRACT_JS)
        except Exception as e:
            log(f"  netto: {url[-24:]} failed ({type(e).__name__})")
            continue
        for t in tiles:
            row = _norm(t, store, store_id, category)
            if not row["title"]:
                continue
            key = (row["title"], row["price"])
            prev = seen.get(key)
            if prev is None:
                seen[key] = row
                rows.append(row)
            elif prev["category"] in GENERIC and row["category"] not in GENERIC:
                prev["category"] = row["category"]
    log(f"  netto: {len(rows)} offers from {len(pages)} pages")
    return rows


def _num(v):
    if not v:
        return None
    m = re.search(r"(\d+[.,]\d{1,2})", str(v).replace("–", "-"))
    return float(m.group(1).replace(",", ".")) if m else None


def _norm(t, store, store_id, category=None):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(t["href"]).query)
    g = lambda k: (q.get(k) or [None])[0]
    period = g("ValidityPeriod") or ""
    dates = re.findall(r"(\d{2}\.\d{2}\.\d{2})", period)
    return {
        "chain": CHAIN["id"],
        "title": (g("Name") or "").strip(),
        "brand": None,
        "quantity": " ".join(x for x in [g("BundleText"), g("Text")] if x) or None,
        "price": _num(g("Price")),
        "price_before": _num(t.get("old_price")),
        "base_price": g("BasePrice"),
        "discount": t.get("discount"),
        "deposit": _num(g("DepositText")),
        "image": g("Image"),
        "url": f"{SITE}/filialangebote",
        "category": category or "Filial-Angebote",
        "market": (f"{store.get('post_code')} {store.get('city')}"
                   if store else None),
        "market_id": store_id,
        "valid_from": dates[0] if dates else None,
        "valid_to": dates[1] if len(dates) > 1 else None,
        "raw_labels": [x for x in (t.get("disturbers") or []) if x],
        "_text": t.get("full_text"),
    }


# --------------------------------------------------------------------------
# Multi-store scraping
#
# Two findings shape this. Tiles are server-rendered, so no scrolling is needed
# (3s per page instead of 9s). And of the ~22 linked sub-pages only
# /filialangebote/1 (Wochenangebote) and /2 (Wochenendangebote) hold offers of
# their own -- the rest are filtered views that add nothing. So each store costs
# two page loads, and the finer section names are collected once from a
# reference store and reused as a lookup.

MAIN_PAGES = ("/filialangebote/1", "/filialangebote/2")


async def _set_store(s, store_id):
    await s.api(f"{ISHOP}/ViewMMPStoreFinder-AddStoreID?StoreID={store_id}")


async def _page_offers(s, url):
    await s.goto(url, settle=2800, cookies=False)
    head = await s.page.evaluate(
        "() => { const h = document.querySelector('h1');"
        " return h ? h.innerText.trim() : ''; }")
    category = re.split(r"\s+g(ü|ue)ltig\s+(von|am|bis)", head)[0].strip() or None
    return category, await s.page.evaluate(EXTRACT_JS)


def _key(row):
    return (row["title"], row["price"])


async def _category_map(s, store_id, log):
    """Section names, learned once from one store and reused for the rest."""
    await _set_store(s, store_id)
    await s.goto(f"{SITE}/filialangebote", settle=4000, cookies=False)
    pages = await s.page.evaluate(
        """() => [...new Set([...document.querySelectorAll('a')]
             .map(a => a.getAttribute('href') || '')
             .filter(h => /\\/filialangebote\\/\\d/.test(h)))]""")
    pages = [p if p.startswith("http") else SITE + p for p in pages]
    extra = [p for p in pages if not p.endswith(MAIN_PAGES)]
    cmap = {}
    for url in extra:
        try:
            category, tiles = await _page_offers(s, url)
        except Exception:
            continue
        if not category or category in ("Wochenangebote", "Wochenendangebote"):
            continue
        for t in tiles:
            row = _norm(t, None, store_id, category)
            if row["title"]:
                cmap.setdefault(_key(row), category)
    log(f"  netto: {len(cmap)} Artikel einer Warengruppe zugeordnet "
        f"({len(extra)} Rubrikseiten)")
    return cmap


async def scrape_all(s, store_list, log=print):
    """Offers across every NETTO store, each tagged with the stores carrying it."""
    if not store_list:
        return []
    await s.goto(f"{SITE}/filialangebote", settle=4000)

    # Use the store with the widest assortment as the category reference.
    cmap = await _category_map(s, store_list[0]["market_id"], log)

    merged = {}
    for i, st in enumerate(store_list, 1):
        sid = st["market_id"]
        try:
            await _set_store(s, sid)
            for path in MAIN_PAGES:
                category, tiles = await _page_offers(s, SITE + path)
                for t in tiles:
                    row = _norm(t, None, sid, category)
                    if not row["title"]:
                        continue
                    k = _key(row)
                    prev = merged.get(k)
                    if prev is None:
                        row["category"] = cmap.get(k, row["category"])
                        row["markets"] = [sid]
                        merged[k] = row
                    elif sid not in prev["markets"]:
                        prev["markets"].append(sid)
        except Exception as e:
            log(f"    netto: Filiale {sid} übersprungen ({type(e).__name__})")
            continue
        if i % 5 == 0 or i == len(store_list):
            log(f"    netto: {i}/{len(store_list)} Filialen, {len(merged)} Angebote")

    out = []
    for row in merged.values():
        row["markets"] = sorted(row["markets"])
        row["market"] = None
        row["market_id"] = None
        out.append(row)
    log(f"  netto: {len(out)} Angebote aus {len(store_list)} Filialen")
    return out
