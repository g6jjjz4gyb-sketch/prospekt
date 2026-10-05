"""LIDL -- offers come from the Schwarz-group leaflet API.

Only leaflet items that map to an online-shop product carry structured data,
and for Lidl DE that means non-food plus wine/beer/spirits. Weekly *food*
offers appear on the leaflet pages as images only, with no machine-readable
price -- see COVERAGE_NOTE, which the site surfaces to the reader.
"""
import datetime as dt
import re

from . import http

CHAIN = {"id": "lidl", "name": "LIDL", "color": "#0050aa"}
PROSPEKTE = "https://www.lidl.de/c/online-prospekte/s10005610"
FLYER_API = "https://endpoints.leaflets.schwarz/v4/flyer?flyer_identifier={}"

COVERAGE_NOTE = ("LIDL veröffentlicht nur Non-Food- und Getränke-Angebote "
                 "maschinenlesbar. Wochen-Lebensmittelangebote stehen "
                 "ausschließlich als Prospektbild zur Verfügung.")


def _slugs():
    html = http.get(PROSPEKTE)
    found = re.findall(r"https://www\.lidl\.de/l/prospekte/([a-zA-Z0-9._-]+)", html)
    # Preserve page order, drop duplicates.
    out = []
    for s in found:
        if s not in out:
            out.append(s)
    return out


def _active(f, today):
    """Keep leaflets whose offer window covers today."""
    try:
        start = dt.date.fromisoformat((f.get("offerStartDate") or f["startDate"])[:10])
        end = dt.date.fromisoformat((f.get("offerEndDate") or f["endDate"])[:10])
    except Exception:
        return False
    return start <= today <= end


async def scrape(s=None, log=print):
    today = dt.date.today()
    rows, leaflets = [], []
    for slug in _slugs():
        try:
            d = http.get_json(FLYER_API.format(slug), timeout=40)
        except Exception as e:
            log(f"  lidl: {slug[:40]} failed ({type(e).__name__})")
            continue
        f = d.get("flyer") or {}
        if not _active(f, today):
            continue
        prods = f.get("products") or {}
        prods = list(prods.values()) if isinstance(prods, dict) else list(prods)
        leaflets.append((f.get("title", slug), len(prods)))
        for p in prods:
            rows.append(_norm(p, f))
    log(f"  lidl: {len(rows)} offers from {len(leaflets)} active leaflets "
        + ", ".join(f"{t[:28]}({n})" for t, n in leaflets))
    return rows


def _clean(t):
    if not t:
        return None
    t = re.sub(r"&szlig;", "ß", t)
    t = re.sub(r"&auml;", "ä", t); t = re.sub(r"&ouml;", "ö", t)
    t = re.sub(r"&uuml;", "ü", t); t = re.sub(r"&Auml;", "Ä", t)
    t = re.sub(r"&Ouml;", "Ö", t); t = re.sub(r"&Uuml;", "Ü", t)
    t = re.sub(r"&amp;", "&", t)
    return re.sub(r"<[^>]+>", " ", t).strip()


def _norm(p, f):
    try:
        price = round(float(p.get("price")), 2)
    except (TypeError, ValueError):
        price = None
    cat = (p.get("wonCategoryPrimary") or "").split("/")
    return {
        "chain": CHAIN["id"],
        "title": _clean(p.get("title")),
        "brand": p.get("brand") or None,
        "quantity": None,
        "price": price,
        "price_before": None,
        "base_price": None,
        "discount": None,
        "image": p.get("image"),
        "url": p.get("url") or (
            "https://www.lidl.de" + p["canonicalUrl"] if p.get("canonicalUrl") else None),
        "category": cat[1] if len(cat) > 1 else "Aktionsprospekt",
        "description": _clean(p.get("description")),
        "valid_from": (f.get("offerStartDate") or "")[:10] or None,
        "valid_to": (f.get("offerEndDate") or "")[:10] or None,
        "leaflet": f.get("title"),
        "leaflet_url": f.get("flyerUrlAbsolute"),
        "raw_labels": [],
    }
