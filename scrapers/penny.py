"""PENNY -- offers come from Magnolia REST: /.rest/offers/by-category/<yyyy-ww>/<slug>

Rather than hard-coding the ISO week and the category list (both change), we load
the offers page, let it fetch its own categories, and reuse the URLs it called.
Any category linked in the nav but not yet loaded is fetched afterwards.
"""
import re

CHAIN = {"id": "penny", "name": "PENNY", "color": "#e30613"}
BASE = "https://www.penny.de"
REST = re.compile(r"/\.rest/offers/by-category/(\d{4}-\d{2})/([a-z0-9-]+)")


async def scrape(s, log=print):
    await s.goto(f"{BASE}/angebote", settle=4000)
    await s.scroll_all(rounds=14)

    week, seen = None, {}
    for url, data in s.captured:
        m = REST.search(url)
        if m and isinstance(data, dict) and "offerTiles" in data:
            week = week or m.group(1)
            seen[m.group(2)] = data["offerTiles"]

    html = await s.html()
    week = week or _week_from(html)
    if not week:
        log("  penny: no week code found"); return []
    log(f"  penny: week {week}, {len(seen)} categories preloaded")

    # Pick up categories linked on the page that lazy-loading never reached.
    slugs = set(re.findall(r'/angebote/([a-z0-9-]+)(?:["/?~])', html))
    for slug in sorted(slugs - set(seen) - {"index"}):
        r = await s.api(f"{BASE}/.rest/offers/by-category/{week}/{slug}")
        if isinstance(r, dict) and r.get("offerTiles"):
            seen[slug] = r["offerTiles"]

    log(f"  penny: {len(seen)} categories, "
        f"{sum(len(v) for v in seen.values())} tiles")

    out, dedup = [], set()
    for slug, tiles in seen.items():
        for t in tiles:
            key = t.get("uuid") or (t.get("title"), t.get("price"))
            if key in dedup:
                continue
            dedup.add(key)
            out.append(_norm(t, slug, week))
    return out


def _week_from(html):
    m = re.search(r"(\d{4}-\d{2})", " ".join(re.findall(r"by-category/[^\"']+", html)))
    return m.group(1) if m else None


def _f(v):
    try:
        return round(float(str(v).replace(",", ".").replace("*", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _norm(t, slug, week):
    img = t.get("imageRendition") or {}
    extra = {}
    try:
        extra = __import__("json").loads(t.get("productData") or "{}")
    except Exception:
        pass
    labels = [x for x in [t.get("actionMarker"), t.get("advantage"),
                          extra.get("disturberType"), extra.get("promotion")] if x]
    return {
        "chain": CHAIN["id"],
        "title": (t.get("title") or "").replace("*", "").strip(),
        "brand": None,
        "quantity": t.get("quantity"),
        "price": _f(t.get("price")),
        "price_before": _f(t.get("listPrice") or t.get("crossOutPrice")),
        "base_price": (t.get("basePrice") or "").strip("()") or None,
        "discount": t.get("advantage"),
        # PENNY app / coupon price -- a second, lower price for app users.
        "app_price": _f(t.get("benefitPrice")),
        "app_discount": t.get("benefitValue"),
        "lowest_30d": _f(t.get("lowestPrice30Days")),
        "image": img.get("tileMd") or img.get("tileLg") or img.get("tileSm"),
        "url": BASE + t["linkHref"] if t.get("linkHref", "").startswith("/") else BASE + "/angebote",
        "category": slug.replace("-", " ").title(),
        "week": week,
        "raw_labels": [str(x) for x in labels],
    }
