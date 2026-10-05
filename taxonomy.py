"""Map each chain's own rubric onto one shared product group.

The six chains name things differently ("Kuehlregal", "Molkerei & Käse",
"Milchprodukte & Eier") and roughly a third of their rubrics aren't product
groups at all but promotional buckets ("Super Wochenende", "Top Angebote",
"Thema der Woche"). So: try the rubric first, and where it carries no product
meaning, fall back to keywords in the product title.
"""
import re
import unicodedata

# The filter's vocabulary. Order is the order shown in the dropdown.
GROUPS = [
    "Obst & Gemüse", "Fleisch & Wurst", "Fisch & Meeresfrüchte",
    "Molkerei & Käse", "Brot & Backwaren", "Tiefkühl",
    "Vorrat & Grundnahrung", "Vegetarisch & Vegan", "Süßes & Snacks",
    "Alkoholfreie Getränke",
    "Bier, Wein & Spirituosen", "Drogerie & Kosmetik", "Haushalt & Reinigung",
    "Haushaltswaren & Wohnen", "Baby & Kind", "Tierbedarf",
    "Garten & Baumarkt", "Mode & Accessoires", "Sport & Freizeit",
    "Sonstiges",
]

def _fold(t):
    t = unicodedata.normalize("NFKD", str(t or "")).lower()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return (t.replace("ß", "ss").replace("ae", "a").replace("oe", "o")
             .replace("ue", "u"))

# Rubric rules, most specific first -- "kueche & haushalt" is kitchenware while
# a bare "haushalt" is cleaning supplies, so the compound has to be tested first.
RUBRIC = [
    ("Vegetarisch & Vegan",   ["vegetarisch", "vegan"]),
    ("Fleisch & Wurst",       ["fleisch", "wurst", "bedientheke", "gefluge"]),
    ("Fisch & Meeresfrüchte", ["fisch", "meeresfr"]),
    ("Obst & Gemüse",         ["obst", "gemus", "salat"]),
    ("Molkerei & Käse",       ["molkerei", "kas", "kuhlregal", "kuhlung",
                               "milchprodukt", "joghurt", "eier"]),
    ("Brot & Backwaren",      ["backstube", "backwaren", "backerkronung",
                               "brot", "fruhstuck", "cerealien"]),
    ("Tiefkühl",              ["tiefkuhl", "tiefkuhlung", "eis"]),
    ("Bier, Wein & Spirituosen", ["wein", "bier", "spirituos", "sekt",
                                  "alkoholische"]),
    ("Alkoholfreie Getränke", ["alkoholfreie getranke", "getranke"]),
    ("Süßes & Snacks",        ["sussigkeit", "susses", "snack", "knabber",
                               "naschen", "salzige"]),
    ("Vorrat & Grundnahrung", ["konserven", "fertiggericht", "grundnahrung",
                               "kochen und backen", "saucen", "gewurz",
                               "xxl lebensmittel", "nudel", "vorrat"]),
    ("Baby & Kind",           ["baby", "kind", "spielware", "spielzeug"]),
    ("Tierbedarf",            ["tier"]),
    ("Garten & Baumarkt",     ["garten", "baumarkt", "pflanzen", "blumen",
                               "werkstatt", "werkzeug"]),
    ("Mode & Accessoires",    ["mode", "accessoire", "textil", "bekleidung",
                               "schuhe", "damen", "herren"]),
    ("Haushaltswaren & Wohnen", ["kuche und haushalt", "kuche & haushalt",
                                 "wohnen", "einrichtung", "haushaltsartikel",
                                 "haushaltswaren", "air fryer"]),
    ("Drogerie & Kosmetik",   ["drogerie", "kosmetik", "korperpflege", "beauty"]),
    ("Haushalt & Reinigung",  ["haushalt", "reinigung", "waschen", "putz"]),
    ("Sport & Freizeit",      ["sport", "freizeit", "multimedia", "technik"]),
]

# Rubrics that describe a promotion, not a product group -- skip straight to the
# title. Matched as substrings against the folded rubric.
PROMO = [
    "top angebote", "topangebote", "weitere angebote", "super wochenende",
    "wochenangebote", "wochenendangebote", "alles fur 1 euro", "knuller",
    "thema der woche", "bonus produkte", "sonstiges", "im angebot",
    "los-artikel", "payback", "marke vs", "sparen auf top marken",
    "dauerhaft", "schnell und einfach", "food highlights", "highlight",
    "bio-produkte", "fairtrade", "filial-angebote",
    "san fabio", "landfreund", "framstag", "eigenmarken", "markenprodukte",
]

# Title keywords, checked when the rubric says nothing useful.
TITLE = [
    ("Bier, Wein & Spirituosen", ["bier", "pils", "weizen", "wein", "rioja",
        "prosecco", "sekt", "champagner", "vodka", "wodka", "whisk", "rum",
        "gin", "likor", "aperol", "ramazzotti", "jagermeister", "korn",
        "tequila", "brandy", "cognac", "radler", "helles", "lager", "beer", "ale", "stout",
        "paulaner", "erdinger", "becks", "warsteiner", "bitburger",
        "krombacher", "jever", "veltins", "radeberger", "franziskaner",
        "augustiner", "tegernseer", "oettinger", "hasseroder"]),
    ("Alkoholfreie Getränke", ["cola", "limonade", "saft", "nektar", "wasser",
        "schorle", "eistee", "energy", "kaffee", "espresso", "kakao",
        "sirup", "brause", "smoothie", "tee", "apfelsaft", "orangensaft",
        "fruchtsaft", "multivitamin", "naturell", "fruchtetee", "krautertee",
        "schwarztee", "gruntee", "cappuccino", "dolce gusto", "kapseln",
        "ganze bohnen", "jacobs", "nescafe", "krombacher 0,0"]),
    ("Molkerei & Käse", ["milch", "joghurt", "yoghurt", "quark", "sahne",
        "butter", "kase", "gouda", "mozzarella", "camembert", "feta", "frischkase",
        "schmand", "creme fraiche", "pudding", "eier"]),
    ("Fisch & Meeresfrüchte", ["lachs", "thunfisch", "hering", "matjes",
        "garnele", "forelle", "makrele", "sardine", "fischstab", "scholle",
        "surimi", "shrimp"]),
    ("Fleisch & Wurst", ["hahnchen", "hanchen", "schwein", "rind", "hack",
        "schnitzel", "steak", "wurst", "salami", "schinken", "bratwurst",
        "frikadelle", "gulasch", "filet", "speck", "leberkas", "putenbrust",
        "geflugel", "lamm", "bacon"]),
    ("Vegetarisch & Vegan", ["vegan", "veggie", "tofu", "seitan", "falafel",
        "grillspiess", "gemusebállchen", "gemuseballchen", "my vay"]),
    ("Brot & Backwaren", ["brot", "brotchen", "baguette", "toast", "kuchen",
        "torte", "croissant", "muffin", "waffel", "knackebrot", "zwieback",
        "muesli", "musli", "cornflakes", "marmelade", "konfitur", "honig",
        "nutella", "apfeltasche", "berliner", "brezel", "haferflocken",
        "aufstrich", "knuspermusli"]),
    ("Obst & Gemüse", ["apfel", "banane", "trauben", "erdbeer", "tomate",
        "gurke", "paprika", "kartoffel", "zwiebel", "salat", "mohre", "karotte",
        "zucchini", "avocado", "melone", "birne", "pfirsich", "nektarine",
        "beeren", "champignon", "brokkoli", "zitrone", "orange", "mandarine",
        "kirsche", "pflaume", "spinat", "lauch", "kohl", "mango", "radieschen",
        "buschbohnen", "ananas", "kiwi", "heidelbeer", "himbeer",
        "kurbis", "rucola", "fenchel", "sellerie", "ingwer"]),
    ("Tiefkühl", ["pizza", "tiefkuhl", "eiscreme", "speiseeis", "magnum",
        "ben & jerry", "pommes", "backfisch", "frites", "mccain", "rahmspinat"]),
    ("Süßes & Snacks", ["schokolade", "milka", "riegel", "keks", "bonbon",
        "gummibar", "haribo", "chips", "flips", "cracker", "nuss", "erdnuss",
        "mandel", "praline", "lakritz", "kaugummi", "salzstange", "popcorn",
        "saltletts", "toffee", "traubenzucker", "toffifee", "nicnac",
        "schokoriegel", "waffeln"]),
    ("Vorrat & Grundnahrung", ["nudel", "spaghetti", "pasta", "reis", "mehl",
        "zucker", "salz", "olivenol", "rapsol", "sonnenblumenol", "speiseol",
        "essig", "senf", "ketchup",
        "mayonnaise", "sosse", "sauce", "suppe", "konserve", "dose", "passata",
        "pesto", "gewurz", "bruhe", "maggi", "knorr",
        "gnocchi", "lasagne", "tortellini", "ravioli", "paniermehl",
        "sultaninen", "backmischung", "bohnen", "rote bete", "linsen",
        "kichererbsen",
        "mais", "kühne", "kuhne"]),
    ("Drogerie & Kosmetik", ["shampoo", "duschgel", "zahnpasta", "zahnburste",
        "deo", "creme", "rasier", "windel", "binde", "tampon", "seife",
        "haarfarbe", "parfum", "sonnenschutz", "nivea", "labello", "handcreme",
        "feuchttuch", "wattestab"]),
    ("Haushalt & Reinigung", ["waschmittel", "weichspuler", "spulmittel",
        "reiniger", "putz", "wc-", "muellbeutel", "mullbeutel", "toilettenpapier",
        "kuchenrolle", "taschentuch", "alufolie", "frischhalte", "backpapier",
        "spee", "persil", "ariel", "domestos", "sagrotan", "kuschelweich"]),
    ("Tierbedarf", ["hunde", "katzen", "whiskas", "pedigree", "felix ",
        "vogelfutter", "tierfutter", "nager", "felix", "sheba", "kitekat"]),
    ("Baby & Kind", ["baby", "kinder", "spielzeug", "puzzle", "lego", "windeln"]),
    ("Garten & Baumarkt", ["parkside", "florabest", "akku", "bohrer", "sage",
        "rasenmaher", "pflanze", "blumen", "erde", "dunger", "schlauch",
        "werkzeug", "leiter", "farbe"]),
    ("Mode & Accessoires", ["esmara", "livergy", "pantolette", "t-shirt",
        "shirt", "hose", "jacke", "socken", "schuhe", "sneaker", "unterwasche",
        "pyjama", "mutze", "slip", "top"]),
    ("Haushaltswaren & Wohnen", ["pfanne", "topf", "geschirr", "besteck",
        "glas", "teller", "tasse", "kissen", "decke", "bettwasche", "handtuch",
        "vorhang", "teppich", "lampe", "regal", "silvercrest", "ernesto"]),
    ("Sport & Freizeit", ["crivit", "fahrrad", "laufschuh", "fitness", "yoga",
        "camping", "zelt", "koffer", "rucksack"]),
]

# Rubrics broad enough to span groups -- "Getränke" holds both beer and water,
# "Kühlregal" holds cheese, sausage and desserts alike.
SOFT = ["getranke", "kuhlregal", "kuhlung", "lebensmittel",
        "fleisch & fisch", "fleisch und fisch"]

_RUBRIC_C = [(g, [re.compile(r"\b" + re.escape(k)) for k in ks]) for g, ks in RUBRIC]
def _title_pat(k):
    """German compounds decide the matching rule.

    Short keywords must be boundary-anchored or they misfire inside longer
    words ("ei" in "alkoholfrei", "rum" in "Premium"). Keywords of five or more
    characters are safe as plain substrings, and have to be, because the word
    a shopper looks for is usually buried in a compound: "milch" in
    "H-Vollmilch", "tomate" in "Minipflaumentomaten", "chips" in "Crunchips".
    """
    k = re.escape(k)
    return re.compile(k if len(k) >= 5 else r"\b" + k)


_TITLE_C = [(g, [_title_pat(k) for k in ks]) for g, ks in TITLE]


def _by_rubric(rub):
    for g, pats in _RUBRIC_C:
        if any(p.search(rub) for p in pats):
            return g
    return None


def group_for(offer):
    rub = _fold(offer.get("category"))
    promo = bool(rub) and any(p in rub for p in PROMO)
    soft = bool(rub) and any(s in rub for s in SOFT)
    if rub and not promo and not soft:
        g = _by_rubric(rub)
        if g:
            return g
    # The name decides. A description only gets a say if the name said nothing,
    # because descriptions mention ingredients ("Gewürz Ketchup ... Tomaten")
    # that belong to a different group than the product itself.
    name = _fold(" ".join(str(x) for x in
                          [offer.get("title"), offer.get("brand")] if x))
    desc = _fold(offer.get("quantity"))
    for hay in (name, desc):
        if not hay:
            continue
        for g, pats in _TITLE_C:
            if any(p.search(hay) for p in pats):
                return g
    # Fall back to a broad rubric only after the title had its say.
    if rub and not promo:
        g = _by_rubric(rub)
        if g:
            return g
    return "Sonstiges"
