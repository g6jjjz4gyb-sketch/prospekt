"""Unified offer schema plus the free/cashback classifier.

`classify` decides which offers belong in the highlighted "Gratis" section.
It works on the advertising text, so it is deliberately conservative: German
leaflets rarely price anything at 0,00 EUR, and the interesting freebies are
phrased as 1+1, coupon giveaways or manufacturer cashback ("Geld zurueck").
Each hit records *why* it matched so the website can show the evidence rather
than asking the reader to trust a label.
"""
import re
import unicodedata

import taxonomy

# Order matters: the first tier that matches wins, strongest claim first.
# Order matters: most specific tier first, because a bare "gratis" also appears
# inside "1+1 gratis" and "gratis testen", which mean quite different things.
FREE_RULES = [
    ("bogo", "1+1 / 2 für 1", [
        r"\b1\s*\+\s*1\b", r"\b2\s*\+\s*1\b", r"\b3\s*\+\s*1\b",
        r"\b2\s*f(ü|ue)r\s*1\b", r"\b3\s*f(ü|ue)r\s*2\b",
        r"nimm\s*\d\s*zahl\s*\d", r"\bzweite[sr]?\s+(artikel|produkt)\s+gratis",
        r"\bbuy\s*one\s*get\s*one\b",
    ]),
    ("cashback", "Cashback / Geld zurück", [
        r"geld[\s-]*zur(ü|ue)ck", r"\bcashback\b", r"\bcash[\s-]back\b",
        r"(gratis|kostenlos)\s*testen", r"produkttest",
        r"\btestaktion\b", r"\b(rück)?erstattung\b",
    ]),
    ("coupon_free", "Gratis per Coupon / App", [
        r"gratis[\s-]*(zugabe|dazu|artikel|produkt)",
        r"(coupon|gutschein|app)[^.]{0,30}gratis",
        r"gratis[^.]{0,30}(coupon|gutschein|app)",
        r"\bpayback[^.]{0,25}gratis\b", r"\bgratis[^.]{0,25}payback\b",
        r"\bzugabe\b",
    ]),
    ("free", "Gratis", [
        r"\bgratis\b", r"\bkostenlos\b", r"\bgeschenkt\b", r"\bumsonst\b",
        r"\bfor free\b", r"\bzum nulltarif\b",
    ]),
]
COMPILED = [(k, lbl, [re.compile(p, re.I) for p in pats])
            for k, lbl, pats in FREE_RULES]

TIER_ORDER = {"free": 0, "bogo": 1, "coupon_free": 2, "cashback": 3}


def _haystack(o):
    parts = [o.get("title"), o.get("quantity"), o.get("description"),
             o.get("discount"), o.get("category"), o.get("_text")]
    parts += [str(x) for x in (o.get("raw_labels") or [])]
    text = " ".join(str(p) for p in parts if p)
    # Normalise so "GRATIS", "Gra­tis" and "gratis" all match.
    return unicodedata.normalize("NFC", text)


def classify(o):
    """Return (tier, label, evidence) or (None, None, None)."""
    text = _haystack(o)
    for key, label, pats in COMPILED:
        for p in pats:
            m = p.search(text)
            if m:
                s = max(0, m.start() - 45)
                return key, label, text[s:m.end() + 45].strip()
    # A bare 0,00 EUR is deliberately NOT treated as free: in these feeds it
    # almost always means the chain published no price, and the giveaways that
    # are real always say so in the advertising text, which the rules above
    # already catch.
    return None, None, None



def label_names(value, depth=0):
    """Flatten a chain's badge/label field into plain names.

    Chains hand these back in wildly different shapes -- EDEKA nests dicts with
    an 'name' key, ALDI nests badge groups under 'items' -- so pull out the
    human-readable strings and drop the plumbing.
    """
    if value is None or depth > 4:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v and not v.startswith(("{", "[", "http")) else []
    if isinstance(value, (int, float)):
        return []
    if isinstance(value, dict):
        for key in ("name", "label", "text", "title", "displayName"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return [v.strip()]
        out = []
        for key in ("items", "badges", "values", "children"):
            out += label_names(value.get(key), depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out += label_names(v, depth + 1)
        return out
    return []


_TAG = re.compile(r"<[^>]*>")
_CSSISH = re.compile(r"[{};]|[a-z-]+\s*:\s*#?[0-9a-z.%()\s,-]+;")


def clean_text(t, limit=160):
    """Strip markup/CSS fragments that leak in from innerText scraping."""
    if not t:
        return None
    t = _TAG.sub(" ", str(t))
    t = _CSSISH.sub(" ", t)
    t = re.sub(r"&nbsp;?", " ", t)
    t = re.sub(r"\s+", " ", t)
    # Drop a leading CSS/markup remnant (e.g. 'c0d15 ">') left by innerText.
    t = re.sub(r'^[^A-Za-zÄÖÜäöü]*[a-f0-9]{4,6}\s*"?>\s*', "", t)
    t = t.strip(" -\u2013\u2014\"'>")
    return t[:limit] or None


# Labels the chains attach for their own bookkeeping; they tell a shopper
# nothing, so they never reach the cards.
LABEL_STOPLIST = {
    "kein störer", "normaler preis", "aktion", "rabatt", "spot",
    "filiale filialartikel", "filiale", "filialartikel", "marke",
    "filiale & shop filial- & online shop artikel", "reduzierter preis",
}


def useful_labels(labels):
    out = []
    for l in labels:
        t = re.sub(r"\s+", " ", str(l)).strip()
        if not t or t.lower() in LABEL_STOPLIST or len(t) > 28:
            continue
        if t.lower().startswith("filiale"):
            continue
        if t not in out:
            out.append(t)
    return out


_BP_DEC = re.compile(r"(?<=\d)\.(?=\d{2}\b)")


_VALID_CLAUSE = re.compile(r"\s+g(ü|ue)ltig\s+(von|am|bis)\b.*$", re.I)


def clean_category(c):
    """Section headings often carry the validity period; the card shows dates
    separately, so keep only the name."""
    if not c:
        return c
    return _VALID_CLAUSE.sub("", str(c)).strip(" ,-") or None


def de_decimals(t):
    """Chains mix '1.76 / kg' and '1,76 / kg'; show one convention."""
    if not t:
        return t
    return _BP_DEC.sub(",", str(t))


REQUIRED = ("chain", "title", "price", "image", "url", "category")


def finalize(o):
    """Fill gaps, attach the free-offer verdict, and drop scraping scratch keys."""
    for k in REQUIRED:
        o.setdefault(k, None)
    tier, label, evidence = classify(o)
    o["free_tier"] = tier
    o["free_label"] = label
    o["free_evidence"] = clean_text(evidence)
    o.pop("_raw", None)
    o["raw_labels"] = useful_labels(label_names(o.get("raw_labels")))
    o["base_price"] = de_decimals(clean_text(o.get("base_price"), 60))
    o["quantity"] = clean_text(o.get("quantity"), 120)
    o["category"] = clean_category(o.get("category"))
    o["group"] = taxonomy.group_for(o)
    if o.get("title"):
        o["title"] = re.sub(r"\s+", " ", str(o["title"])).strip()
    # Savings, where both sides are known and sane.
    p, b = o.get("price"), o.get("price_before")
    if isinstance(p, (int, float)) and isinstance(b, (int, float)) and b > p > 0:
        o["saving_pct"] = round((b - p) / b * 100)
        o["saving_abs"] = round(b - p, 2)
    else:
        o.setdefault("saving_pct", None)
        o.setdefault("saving_abs", None)
    return o


def sort_key(o):
    return (TIER_ORDER.get(o.get("free_tier"), 9), -(o.get("saving_pct") or 0))
