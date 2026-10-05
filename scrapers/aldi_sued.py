"""ALDI SÜD -- Frankfurt is ALDI SÜD territory.

Weekly offers come from the shop API (api.aldi-sued.de). The API rejects plain
HTTP clients, so calls are issued from inside an aldi-sued.de page. Offers are
national: the country's defaultMerchant (servicePoint B384) serves all of DE.
"""
import re

API = "https://api.aldi-sued.de"
SERVICE_POINT = "B384"
WEEKLY_CATEGORY = "1588161426582123"   # "Wochenangebote"
PAGE = 12                              # API rejects other page sizes

CHAIN = {"id": "aldi_sued", "name": "ALDI SÜD", "color": "#00005f"}


async def scrape(s, log=print):
    await s.goto("https://www.aldi-sued.de/angebote", settle=4000)

    out, offset, total = [], 0, None
    while True:
        url = (f"{API}/v3/product-search?currency=EUR&serviceType=walk-in"
               f"&categoryKey={WEEKLY_CATEGORY}&limit={PAGE}&offset={offset}"
               f"&servicePoint={SERVICE_POINT}")
        r = await s.api(url)
        if not isinstance(r, dict) or "data" not in r:
            log(f"  aldi: stopped at offset {offset}: {str(r)[:120]}")
            break
        if total is None:
            total = r.get("meta", {}).get("pagination", {}).get("totalCount", 0)
            log(f"  aldi: {total} weekly offers")
        batch = r["data"]
        if not batch:
            break
        out.extend(batch)
        offset += PAGE
        if offset >= (total or 0) or offset > 600:
            break
    return [_norm(p) for p in out]


def _img(p, width=500):
    """assets[].url is a template with {width}/{slug} placeholders."""
    for a in (p.get("assets") or []):
        u = a.get("url")
        if u:
            return u.replace("{width}", str(width)).replace(
                "{slug}", p.get("urlSlugText") or "product")
    return None


def _eur(cents):
    try:
        return round(int(cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def _parse_de(txt):
    """'2,19 \u20ac' -> 2.19"""
    if not txt:
        return None
    m = re.search(r"(\d+[.,]\d{2})", str(txt))
    return float(m.group(1).replace(",", ".")) if m else None


def _norm(p):
    pr = p.get("price") or {}
    cats = p.get("categories") or []
    sub = [c["name"] for c in cats if c.get("name") != "Wochenangebote"]
    deposit = _eur(pr.get("bottleDeposit")) or 0.0
    return {
        "chain": CHAIN["id"],
        "title": " ".join(x for x in [(p.get("brandName") or "").strip(),
                                      (p.get("name") or "").strip()] if x),
        "brand": (p.get("brandName") or "").strip() or None,
        "quantity": p.get("sellingSize") or None,
        "price": _eur(pr.get("amountRelevant") or pr.get("amount")),
        "price_before": _parse_de(pr.get("wasPriceDisplay")),
        "base_price": pr.get("comparisonDisplay"),
        "discount": pr.get("savingsDisplay"),
        "deposit": deposit or None,
        "image": _img(p),
        "url": (f"https://www.aldi-sued.de/p/{p['urlSlugText']}"
                if p.get("urlSlugText") else "https://www.aldi-sued.de/angebote"),
        "category": sub[0] if sub else "Wochenangebote",
        "raw_labels": p.get("badges") or [],
    }
