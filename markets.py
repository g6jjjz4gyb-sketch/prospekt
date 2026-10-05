"""Resolve every branch of every chain within a radius of the configured centre.

Each chain answers a different question, so each gets its own resolver, but all
return the same record: {chain, market_id, name, street, zip, city, lat, lon,
distance_km, extra}. Results are cached in data/markets.json -- branch lists
change far more slowly than offers, and re-resolving EDEKA in particular means
driving its Marktsuche UI several times.
"""
import json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "markets.json")


def km(lat1, lon1, lat2, lon2):
    return 111.0 * math.hypot(float(lat1) - float(lat2),
                              (float(lon1) - float(lon2))
                              * math.cos(math.radians(float(lat1))))


def _rec(chain, mid, name, street, zipc, city, lat, lon, centre, **extra):
    return {
        "chain": chain, "market_id": str(mid), "name": name or None,
        "street": street or None, "zip": zipc or None, "city": city or None,
        "lat": float(lat), "lon": float(lon),
        "distance_km": round(km(centre[0], centre[1], lat, lon), 1),
        **extra,
    }


def _json_arrays(html, anchor):
    """Pull the JSON array following each `anchor` out of an HTML blob."""
    out = []
    for m in re.finditer(re.escape(anchor), html):
        try:
            i = html.index("[", m.end() - 1)
        except ValueError:
            continue
        depth, instr, esc = 0, False, False
        for j in range(i, len(html)):
            c = html[j]
            if esc:
                esc = False; continue
            if c == "\\":
                esc = True; continue
            if c == '"':
                instr = not instr; continue
            if instr:
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    out.append(html[i:j + 1]); break
    return out


# --------------------------------------------------------------- REWE

async def rewe(s, centre, radius, terms, log=print):
    from scrapers import rewe as R
    await s.goto("https://www.rewe.de/angebote/", settle=4000)
    found = {}
    for term in terms:
        payload = [{"id": R.MARKET_LIST_ID, "name": "wks-market-list",
                    "namespace": "market-chooser",
                    "query": {"searchTerm": str(term), "page": "1",
                              "longitude": None, "latitude": None,
                              "productId": "", "hasUserInteracted": "true"}}]
        r = await s.api(R.FRONTEND_INCLUDES,
                        headers={"Content-Type": "application/json"},
                        method="POST", body=payload)
        if not (isinstance(r, list) and r and r[0].get("content")):
            continue
        for arr in _json_arrays(r[0]["content"], '"marketResults":{"markets":'):
            try:
                for x in json.loads(arr):
                    found[x["wwIdent"]] = x
            except Exception:
                continue
    out = []
    for x in found.values():
        loc = x.get("location") or {}
        if not loc.get("latitude"):
            continue
        rec = _rec("rewe", x["wwIdent"],
                   x.get("name"), x.get("street"), x.get("zipCode"),
                   x.get("city"), loc["latitude"], loc["longitude"], centre,
                   market_type=(x.get("category") or {}).get("marketTypeDisplayName"))
        if rec["distance_km"] <= radius:
            out.append(rec)
    log(f"  rewe: {len(out)} Märkte im Radius (von {len(found)} gefunden)")
    return out


# --------------------------------------------------------------- EDEKA

async def edeka(s, centre, radius, terms, log=print):
    from scrapers import edeka as E
    ids = set()
    for term in terms:
        try:
            for m in await E.find_markets(s, term, log=lambda *_: None):
                ids.add(m["market_id"])
        except Exception as e:
            log(f"  edeka: Suche {term} fehlgeschlagen ({type(e).__name__})")
    out = []
    for mid in sorted(ids):
        g = await s.api(E.GATEWAY.format(mid))
        if not (isinstance(g, dict) and g.get("coordinates")):
            continue
        c, a = g["coordinates"], (g.get("contact") or {}).get("address") or {}
        city = a.get("city") or {}
        rec = _rec("edeka", g["id"], g.get("name"), a.get("street"),
                   city.get("zipCode"), city.get("name"),
                   c["lat"], c["lon"], centre,
                   market_type=g.get("distributionChannelName"))
        if rec["distance_km"] <= radius:
            out.append(rec)
    log(f"  edeka: {len(out)} Märkte im Radius (von {len(ids)} IDs)")
    return out


# --------------------------------------------------------------- NETTO

async def netto(s, centre, radius, log=print):
    from scrapers import netto as N
    await s.goto("https://www.netto-online.de/filialangebote", settle=4000)
    stores = await N.find_stores(s, centre[0], centre[1], radius, log=lambda *_: None)
    out = [_rec("netto", x["store_id"], x.get("store_name"), x.get("street"),
                x.get("post_code"), x.get("city"),
                x["coord_latitude"], x["coord_longitude"], centre,
                region_id=x.get("region_id"))
           for x in stores]
    out = [x for x in out if x["distance_km"] <= radius]
    log(f"  netto: {len(out)} Filialen im Radius")
    return out


# --------------------------------------------------------------- ALDI SÜD

async def aldi_sued(s, centre, radius, log=print):
    await s.goto("https://www.aldi-sued.de/angebote", settle=3000)
    r = await s.api("https://api.aldi-sued.de/v2/service-points?limit=5000")
    out = []
    for x in (r.get("data") if isinstance(r, dict) else []) or []:
        a = x.get("address") or {}
        if not a.get("latitude"):
            continue
        rec = _rec("aldi_sued", x["id"], a.get("address1"), a.get("address1"),
                   a.get("zipCode"), a.get("city"),
                   a["latitude"], a["longitude"], centre)
        if rec["distance_km"] <= radius:
            out.append(rec)
    log(f"  aldi_sued: {len(out)} Filialen im Radius")
    return out


# --------------------------------------------------------------- PENNY

async def penny(s, centre, radius, log=print):
    from scrapers import http
    try:
        data = http.get_json("https://www.penny.de/.rest/market", timeout=60)
    except Exception as e:
        log(f"  penny: Marktliste nicht abrufbar ({type(e).__name__})")
        return []
    out = []
    for x in data:
        if not x.get("latitude"):
            continue
        rec = _rec("penny", x["wwIdent"], x.get("marketName"),
                   x.get("streetWithHouseNumber"), x.get("zipCode"),
                   x.get("city"), x["latitude"], x["longitude"], centre,
                   selling_region=x.get("sellingRegion"))
        if rec["distance_km"] <= radius:
            out.append(rec)
    log(f"  penny: {len(out)} Märkte im Radius")
    return out


# --------------------------------------------------------------- LIDL

LIDL_MANIFEST = ("https://www.lidl.de/s/storesearch/26_16_10/builds/meta/"
                 "bid_26_16_10.json")


def _city_slug(name):
    t = (name or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    # "Frankfurt am Main", "Frankfurt/Bockenheim" and "Frankfurt-Nordend" are
    # all just "frankfurt" in LIDL's URLs.
    return t.split("-am-")[0].split("/")[0]


async def lidl(s, centre, radius, nearby_cities, log=print):
    """LIDL publishes no store coordinates, only a manifest of store pages.

    So the radius can't be measured directly. Instead we accept the towns that
    the other chains' resolved markets already put inside the radius, and list
    LIDL's branches in exactly those towns -- same catchment, no distances.
    """
    from scrapers import http
    try:
        data = http.get_json(LIDL_MANIFEST, timeout=60)
    except Exception as e:
        log(f"  lidl: Filialmanifest nicht abrufbar ({type(e).__name__})")
        return []
    wanted = {_city_slug(c) for c in nearby_cities if c}
    out = []
    for path in data.get("prerendered", []):
        parts = path.split("/")
        if len(parts) < 5 or parts[1] != "de-DE" or parts[2] != "filialen":
            continue
        city, street = parts[3], parts[4]
        if city not in wanted:
            continue
        out.append({
            "chain": "lidl", "market_id": f"{city}/{street}",
            "name": None,
            "street": street.replace("-", " ").title(),
            "zip": None, "city": city.replace("-", " ").title(),
            "lat": None, "lon": None, "distance_km": None,
            "url": "https://www.lidl.de" + path,
        })
    log(f"  lidl: {len(out)} Filialen in {len(wanted)} Orten "
        f"(ohne Entfernung - LIDL veröffentlicht keine Koordinaten)")
    return out


RESOLVERS = {"rewe": rewe, "edeka": edeka, "netto": netto,
             "aldi_sued": aldi_sued, "penny": penny, "lidl": lidl}


def load():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save(payload):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
