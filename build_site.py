#!/usr/bin/env python3
"""Render data/latest.json into a self-contained web/index.html.

The data is embedded rather than fetched so the page works from a file:// URL
(and as a published Artifact, where external requests are blocked). Product
images are decorative only: the card is typographic first and hides the
thumbnail if it fails to load.
"""
import base64, json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import normalize
import taxonomy

DATA = os.path.join(HERE, "data", "latest.json")
WEB = os.path.join(HERE, "web")
OUT = os.path.join(WEB, "index.html")

TIER_META = {
    "free":        ("Gratis",              "Als gratis, kostenlos oder 0,00 € beworben"),
    "bogo":        ("1+1 / 2 für 1",       "Eine Einheit ist beim Kauf effektiv gratis"),
    "coupon_free": ("Gratis per Coupon",   "Gratis-Zugabe über App, Coupon oder Payback"),
    "cashback":    ("Cashback",            "Hersteller erstattet den Kaufpreis zurück"),
}

TEMPLATE = r"""<title>Prospekt Frankfurt</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{
  --paper:#e8eaee; --sunk:#dcdfe5; --card:#ffffff; --ink:#15171c; --ink-2:#454b57;
  --ink-3:#6b7280; --line:#c9ced8; --line-soft:#dfe3ea;
  --signal:#c8102e; --signal-ink:#ffffff;
  --flash:#ffd400; --flash-ink:#15171c; --flash-edge:#c8a400;
  --good:#0f7b52; --shadow:0 1px 0 rgba(21,23,28,.06), 0 6px 18px -12px rgba(21,23,28,.5);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#101318; --sunk:#0a0c10; --card:#191d24; --ink:#e9ecf1; --ink-2:#aab2c0;
    --ink-3:#7d8697; --line:#2c333e; --line-soft:#232932;
    --signal:#ff5a6e; --signal-ink:#1a0308;
    --flash:#ffd400; --flash-ink:#15171c; --flash-edge:#8a7200;
    --good:#3ecf96; --shadow:0 1px 0 rgba(0,0,0,.4), 0 8px 22px -14px #000;
  }
}
:root[data-theme="dark"]{
  --paper:#101318; --sunk:#0a0c10; --card:#191d24; --ink:#e9ecf1; --ink-2:#aab2c0;
  --ink-3:#7d8697; --line:#2c333e; --line-soft:#232932;
  --signal:#ff5a6e; --signal-ink:#1a0308;
  --flash:#ffd400; --flash-ink:#15171c; --flash-edge:#8a7200;
  --good:#3ecf96; --shadow:0 1px 0 rgba(0,0,0,.4), 0 8px 22px -14px #000;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1240px; margin:0 auto; padding:0 20px}
h1,h2,h3{text-wrap:balance; margin:0}
.cond{font-family:"Barlow Condensed","IBM Plex Sans",sans-serif}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace}
.tnum{font-variant-numeric:tabular-nums}

/* ---------- masthead ---------- */
header.mast{border-bottom:2px solid var(--ink); background:var(--card)}
.mast-in{display:flex; flex-wrap:wrap; align-items:flex-end; gap:18px 28px; padding:22px 0 16px}
.mast h1{
  font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:clamp(34px,5.2vw,54px);
  line-height:.92; letter-spacing:-.01em; text-transform:uppercase;
}
.mast h1 em{font-style:normal; color:var(--signal)}
.mast .sub{color:var(--ink-2); font-size:14px; max-width:46ch}
.mast .meta{margin-left:auto; text-align:right; font-size:12.5px; color:var(--ink-3); line-height:1.75}
.mast .meta b{color:var(--ink); font-weight:600}
.kbd{
  font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.04em;
  border:1px solid var(--line); border-radius:4px; padding:1px 5px; color:var(--ink-2);
}

/* ---------- source strip ---------- */
.sources{display:flex; flex-wrap:wrap; gap:8px; padding:14px 0 18px}
.src{
  display:flex; align-items:baseline; gap:8px; background:var(--card);
  border:1px solid var(--line-soft); border-left:4px solid var(--rail,var(--ink-3));
  border-radius:3px; padding:7px 12px 7px 10px; box-shadow:var(--shadow);
}
.src .n{font-weight:600; font-size:12.5px; letter-spacing:.01em}
.src .c{font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:19px; line-height:1}
.src.bad{border-left-color:var(--signal)}
.src.bad .c{color:var(--signal); font-size:12px; font-family:inherit; font-weight:600}

/* ---------- gratis band ---------- */
.band{background:var(--flash); color:var(--flash-ink); border-block:2px solid var(--ink); margin-top:6px}
.band-in{padding:26px 0 30px}
.band h2{
  font-family:"Barlow Condensed",sans-serif; font-weight:700; text-transform:uppercase;
  font-size:clamp(26px,3.6vw,38px); line-height:1; letter-spacing:.005em;
}
.band .lede{max-width:62ch; margin-top:8px; font-size:14px; color:#3a3208}
.band .lede b{color:var(--flash-ink)}
.tiers{display:flex; flex-wrap:wrap; gap:7px; margin:16px 0 20px}
.tier{
  background:rgba(21,23,28,.08); border:1px solid rgba(21,23,28,.28); border-radius:999px;
  padding:4px 11px; font-size:12px; font-weight:600;
}
.tier .k{font-family:"Barlow Condensed",sans-serif; font-size:15px; margin-right:5px}
.free-grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(275px,1fr)); gap:12px}
.fcard{
  background:var(--card); color:var(--ink); border:2px solid var(--ink); border-radius:4px;
  padding:13px 14px; display:flex; flex-direction:column; gap:7px;
}
.fcard .top{display:flex; align-items:center; justify-content:space-between; gap:10px}
.fcard .chain{font-size:10.5px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
.fcard .badge{
  background:var(--flash); color:var(--flash-ink); border:1px solid var(--flash-edge);
  border-radius:3px; padding:2px 7px; font-size:10.5px; font-weight:700;
  letter-spacing:.05em; text-transform:uppercase;
}
.fcard .fthumb{
  height:104px; background:var(--sunk); border-radius:3px; display:grid;
  place-items:center; overflow:hidden;
}
.fcard .fthumb img{max-width:100%; max-height:100%; object-fit:contain; padding:6px}
.fcard .t{font-weight:600; font-size:15.5px; line-height:1.3}
.fcard .ev{
  font-family:"IBM Plex Mono",monospace; font-size:11.5px; line-height:1.5; color:var(--ink-2);
  background:var(--sunk); border-left:2px solid var(--flash-edge); padding:7px 9px; border-radius:0 3px 3px 0;
}
.band .empty{
  background:var(--card); color:var(--ink); border:2px dashed var(--ink);
  border-radius:4px; padding:18px 20px; font-size:14px; max-width:70ch;
}

/* ---------- controls ---------- */
.controls{position:sticky; top:0; z-index:20; background:var(--paper); border-bottom:1px solid var(--line); padding:11px 0}
.controls-in{display:flex; flex-direction:column; gap:9px}
.row-2{display:flex; flex-wrap:wrap; gap:9px; align-items:center}
.row-2 .grow{flex:1 1 240px; min-width:200px}
.row-2 select{width:auto; min-width:170px}
.chips{display:flex; flex-wrap:wrap; gap:6px}
.chip{
  font:inherit; font-size:12.5px; font-weight:600; cursor:pointer;
  background:var(--card); color:var(--ink-2); border:1px solid var(--line);
  border-radius:999px; padding:5px 12px 5px 9px; display:inline-flex; align-items:center; gap:7px;
}
.chip .dot{width:9px; height:9px; border-radius:2px; background:var(--rail,var(--ink-3)); flex:none}
.chip .qty{font-family:"IBM Plex Mono",monospace; font-size:10.5px; color:var(--ink-3)}
.chip[aria-pressed="true"]{background:var(--ink); color:var(--paper); border-color:var(--ink)}
.chip[aria-pressed="true"] .qty{color:var(--paper); opacity:.72}
.chip:focus-visible,.tgl:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--signal); outline-offset:2px}
.grow{flex:1 1 190px}
input[type=search],select{
  font:inherit; font-size:13.5px; width:100%; background:var(--card); color:var(--ink);
  border:1px solid var(--line); border-radius:3px; padding:7px 10px;
}
.tgl{
  font:inherit; font-size:12.5px; font-weight:700; cursor:pointer; white-space:nowrap;
  background:var(--card); color:var(--ink); border:1px solid var(--ink); border-radius:3px; padding:6px 12px;
}
.tgl[aria-pressed="true"]{background:var(--flash); border-color:var(--ink); color:var(--flash-ink)}

/* ---------- offer grid ---------- */
main{padding:20px 0 60px}
.count{font-size:12.5px; color:var(--ink-3); padding:2px 0 14px}
.count b{color:var(--ink); font-weight:600}
.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(212px,1fr)); gap:11px}
.card{
  background:var(--card); border:1px solid var(--line-soft); border-top:3px solid var(--rail,var(--ink-3));
  border-radius:3px; box-shadow:var(--shadow); padding:11px 12px 12px;
  display:flex; flex-direction:column; gap:8px; min-height:170px;
}
.card .hd{display:flex; align-items:flex-start; justify-content:space-between; gap:8px}
.card .chain{font-size:9.5px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
.card .cat{font-size:10px; color:var(--ink-3); text-align:right; max-width:52%}
.thumb-wrap{
  position:relative; height:96px; background:var(--sunk); border-radius:2px;
  display:grid; place-items:center; overflow:hidden;
}
.thumb-wrap .fb{
  font-family:"Barlow Condensed",sans-serif; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; font-size:12px; color:var(--ink-3); text-align:center;
  padding:0 10px; line-height:1.2;
}
.card .thumb{
  position:absolute; inset:0; width:100%; height:100%; object-fit:contain;
  background:var(--sunk); padding:5px;
}
.card .t{font-weight:600; font-size:14px; line-height:1.32; overflow-wrap:anywhere}
.card .q{font-size:11.5px; color:var(--ink-3); line-height:1.4}
.card .foot{margin-top:auto; display:flex; align-items:flex-end; justify-content:space-between; gap:8px}
.price{font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:30px; line-height:.9; letter-spacing:-.01em}
.price small{font-size:15px; font-weight:600; margin-left:1px}
.was{font-size:11.5px; color:var(--ink-3); text-decoration:line-through}
.base{font-family:"IBM Plex Mono",monospace; font-size:10.5px; color:var(--ink-3)}
.pct{
  background:var(--signal); color:var(--signal-ink); border-radius:3px; padding:3px 7px;
  font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:16px; line-height:1; white-space:nowrap;
}
.applbl{
  display:inline-block; background:var(--sunk); border:1px solid var(--line-soft); border-radius:2px;
  padding:2px 6px; font-size:10px; font-weight:600; color:var(--ink-2); letter-spacing:.03em;
}
.freeflag{background:var(--flash); border-color:var(--flash-edge); color:var(--flash-ink)}
/* ---------- offer detail dialog ---------- */
.card{cursor:pointer; text-align:left; font:inherit; color:inherit; width:100%}
.card:hover{border-color:var(--ink-3)}
.card:focus-visible{outline:2px solid var(--signal); outline-offset:2px}
.mk{
  display:inline-flex; align-items:center; gap:4px; font-size:10px; font-weight:600;
  color:var(--ink-3); letter-spacing:.02em;
}
dialog#detail{
  border:2px solid var(--ink); border-radius:5px; padding:0; max-width:640px;
  width:calc(100vw - 32px); max-height:86vh; background:var(--card); color:var(--ink);
  box-shadow:0 24px 60px -20px rgba(0,0,0,.55);
}
dialog#detail::backdrop{background:rgba(10,12,16,.6)}
.dlg{display:flex; flex-direction:column; max-height:86vh}
.dlg-hd{
  display:flex; align-items:flex-start; gap:14px; padding:16px 18px 14px;
  border-bottom:1px solid var(--line-soft); border-top:4px solid var(--rail,var(--ink-3));
}
.dlg-hd .grow2{flex:1; min-width:0}
.dlg-chain{font-size:10px; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3)}
.dlg-hd h2{font-size:19px; line-height:1.25; margin-top:3px; font-weight:600}
.dlg-close{
  font:inherit; font-size:20px; line-height:1; cursor:pointer; flex:none;
  background:none; border:1px solid var(--line); border-radius:4px;
  color:var(--ink-2); width:32px; height:32px;
}
.dlg-close:hover{background:var(--sunk)}
.dlg-body{overflow-y:auto; padding:16px 18px 20px; display:flex; flex-direction:column; gap:16px}
.dlg-top{display:flex; gap:16px; flex-wrap:wrap}
.dlg-img{
  width:150px; height:150px; flex:none; background:var(--sunk); border-radius:3px;
  display:grid; place-items:center; overflow:hidden;
}
.dlg-img img{max-width:100%; max-height:100%; object-fit:contain; padding:8px}
.dlg-facts{flex:1; min-width:190px; display:flex; flex-direction:column; gap:9px}
.dlg-price{display:flex; align-items:baseline; gap:10px; flex-wrap:wrap}
.dlg-price .price{font-size:38px}
.dl{display:grid; grid-template-columns:auto 1fr; gap:5px 14px; font-size:12.5px}
.dl dt{color:var(--ink-3)}
.dl dd{margin:0; font-variant-numeric:tabular-nums}
.dlg-sec h3{
  font-family:"Barlow Condensed",sans-serif; text-transform:uppercase; font-size:16px;
  letter-spacing:.03em; margin-bottom:3px;
}
.dlg-sec .hint{font-size:12px; color:var(--ink-3); margin-bottom:9px}
.mlist{display:flex; flex-direction:column; gap:0; border:1px solid var(--line-soft); border-radius:3px}
.mrow{
  display:flex; align-items:baseline; gap:10px; padding:7px 11px; font-size:12.5px;
  border-bottom:1px solid var(--line-soft);
}
.mrow:last-child{border-bottom:none}
.mrow .d{
  font-family:"IBM Plex Mono",monospace; font-size:11px; color:var(--ink-3);
  min-width:52px; text-align:right; flex:none;
}
.mrow .nm{font-weight:600}
.mrow .ad{color:var(--ink-3)}
.mnote{
  font-size:12px; color:var(--ink-2); background:var(--sunk); border-radius:3px;
  padding:9px 11px; border-left:3px solid var(--rail,var(--ink-3));
}
.evbox{
  font-family:"IBM Plex Mono",monospace; font-size:11.5px; line-height:1.5;
  background:var(--sunk); border-left:3px solid var(--flash-edge);
  padding:9px 11px; border-radius:0 3px 3px 0; color:var(--ink-2);
}
.more{display:flex; justify-content:center; padding:26px 0}
.more button{
  font:inherit; font-weight:700; font-size:14px; cursor:pointer; background:var(--ink); color:var(--paper);
  border:none; border-radius:3px; padding:11px 26px;
}
.none{padding:44px 4px; color:var(--ink-3); font-size:14px}

/* ---------- notes ---------- */
footer{border-top:2px solid var(--ink); background:var(--card); padding:24px 0 40px; font-size:12.5px; color:var(--ink-2)}
footer h3{font-family:"Barlow Condensed",sans-serif; text-transform:uppercase; font-size:17px; letter-spacing:.02em; margin-bottom:8px}
footer ul{margin:0; padding-left:17px; display:flex; flex-direction:column; gap:6px}
footer .cols{display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:24px}
footer a{color:var(--signal)}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
</style>

<header class="mast">
  <div class="wrap mast-in">
    <div>
      <h1>Prospekt<em>.</em>Woche</h1>
      <p class="sub">Alle Wochenangebote von ALDI SÜD, LIDL, PENNY, REWE, EDEKA und
        NETTO — aus jedem Markt im Umkreis von __RADIUS__ km um __CITY__,
        jeden Montag neu eingelesen. Klick auf ein Angebot zeigt, in welchen
        Märkten es gilt.</p>
    </div>
    <div class="meta">
      <div>Kalenderwoche <b>__WEEK__</b></div>
      <div><b>__TOTAL__</b> Angebote · <b>__FREECOUNT__</b> gratis oder Cashback</div>
      <div><b>__NMARKETS__</b> Märkte im Umkreis von <b>__RADIUS__ km</b></div>
      <div>Stand <b>__STAMP__</b></div>
      <div>Nächste Aktualisierung <span class="kbd">Mo __NEXT__ · 06:30</span></div>
    </div>
  </div>
  <div class="wrap"><div class="sources">__SOURCES__</div></div>
</header>

<section class="band">
  <div class="wrap band-in">
    <h2>Gratis, 1+1 und Geld zurück</h2>
    <p class="lede">__BANDLEDE__</p>
    <div class="tiers">__TIERS__</div>
    __FREEBLOCK__
  </div>
</section>

<div class="controls">
  <div class="wrap controls-in">
    <div class="chips" id="chips"></div>
    <div class="row-2">
      <div class="grow"><input type="search" id="q" placeholder="Produkt, Marke oder Kategorie suchen…" aria-label="Angebote durchsuchen"></div>
      <select id="cat" aria-label="Warengruppe">
        <option value="all">Alle Warengruppen</option>
        __CATOPTS__
      </select>
      <select id="sort" aria-label="Sortierung">
        <option value="disc">Höchster Rabatt</option>
        <option value="price">Günstigster Preis</option>
        <option value="chain">Nach Kette</option>
        <option value="az">A–Z</option>
      </select>
      <button class="tgl" id="onlyfree" aria-pressed="false">Nur Gratis</button>
    </div>
  </div>
</div>

<main class="wrap">
  <p class="count" id="count"></p>
  <div class="grid" id="grid"></div>
  <div class="more" id="more" hidden><button type="button">Weitere Angebote laden</button></div>
  <p class="none" id="none" hidden>Keine Angebote für diese Auswahl. Suche zurücksetzen oder eine andere Kette wählen.</p>
</main>

<dialog id="detail" aria-label="Angebotsdetails">
  <div class="dlg" id="dlgbody"></div>
</dialog>

<footer>
  <div class="wrap cols">
    <div>
      <h3>Woher die Daten kommen</h3>
      <ul>__NOTES__</ul>
    </div>
    <div>
      <h3>Zu den Gratis-Angeboten</h3>
      <ul>
        <li>Die Einstufung liest den Werbetext der Kette. Jede Karte zeigt die
          Fundstelle, damit die Zuordnung nachprüfbar bleibt.</li>
        <li><b>Cashback</b> bedeutet: erst zahlen, dann erstattet der Hersteller —
          meist über ein eigenes Portal und mit Kassenbon.</li>
        <li>Echte 0,00-€-Artikel sind in deutschen Prospekten selten. Findet die
          Auswertung keine, bleibt der Abschnitt bewusst leer statt gefüllt.</li>
      </ul>
    </div>
    <div>
      <h3>Kleingedrucktes</h3>
      <ul>
        <li>Preise stammen aus den erfassten Märkten im Umkreis von __RADIUS__ km
          um __PLZ__ __CITY__. Welche Märkte ein Angebot führen, steht in der
          Detailansicht.</li>
        <li>Pfand, Mengenbegrenzungen und Aktionszeiträume stehen im Angebotstext
          der jeweiligen Kette.</li>
        <li>Ohne Gewähr — verbindlich ist immer der Aushang in der Filiale.</li>
      </ul>
    </div>
  </div>
</footer>

<script>
const DATA = __JSON__;
const IMG = __IMAGES__;
const MARKETS = __MARKETS__;
const CH = DATA.sources;
const fmt = n => n == null ? null : n.toFixed(2).replace('.', ',');
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

let state = {chain: 'all', cat: 'all', q: '', sort: 'disc', onlyFree: false, shown: 60};
const PAGE = 60;

/* chain filter chips */
const chipBox = document.getElementById('chips');
const chains = Object.keys(CH).filter(k => CH[k].ok);
chipBox.innerHTML =
  `<button class="chip" data-c="all" aria-pressed="true">Alle
     <span class="qty">${DATA.counts.total}</span></button>` +
  chains.map(k => `<button class="chip" data-c="${k}" aria-pressed="false"
      style="--rail:${CH[k].color}"><span class="dot"></span>${esc(CH[k].name)}
      <span class="qty">${CH[k].count}</span></button>`).join('');

chipBox.addEventListener('click', e => {
  const b = e.target.closest('.chip'); if (!b) return;
  state.chain = b.dataset.c; state.shown = PAGE;
  [...chipBox.children].forEach(c => c.setAttribute('aria-pressed', c === b));
  render();
});
document.getElementById('q').addEventListener('input', e => {
  state.q = e.target.value.toLowerCase().trim(); state.shown = PAGE; render();
});
document.getElementById('cat').addEventListener('change', e => {
  state.cat = e.target.value; state.shown = PAGE; render();
});
document.getElementById('sort').addEventListener('change', e => {
  state.sort = e.target.value; render();
});
const freeBtn = document.getElementById('onlyfree');
freeBtn.addEventListener('click', () => {
  state.onlyFree = !state.onlyFree; state.shown = PAGE;
  freeBtn.setAttribute('aria-pressed', String(state.onlyFree)); render();
});
document.querySelector('#more button').addEventListener('click', () => {
  state.shown += PAGE; render(true);
});

function filtered() {
  let rows = DATA.offers;
  if (state.chain !== 'all') rows = rows.filter(o => o.chain === state.chain);
  if (state.cat !== 'all') rows = rows.filter(o => o.group === state.cat);
  if (state.onlyFree) rows = rows.filter(o => o.free_tier);
  if (state.q) {
    const q = state.q;
    rows = rows.filter(o =>
      (o.title || '').toLowerCase().includes(q) ||
      (o.category || '').toLowerCase().includes(q) ||
      (o.group || '').toLowerCase().includes(q) ||
      (o.brand || '').toLowerCase().includes(q) ||
      (o.quantity || '').toLowerCase().includes(q));
  }
  const s = state.sort;
  rows = rows.slice().sort((a, b) =>
    s === 'price' ? (a.price ?? 9e9) - (b.price ?? 9e9) :
    s === 'az'    ? (a.title || '').localeCompare(b.title || '', 'de') :
    s === 'chain' ? (a.chain).localeCompare(b.chain) ||
                    (b.saving_pct || 0) - (a.saving_pct || 0)
                  : (b.saving_pct || 0) - (a.saving_pct || 0) ||
                    (a.price ?? 9e9) - (b.price ?? 9e9));
  return rows;
}

function card(o) {
  const c = CH[o.chain] || {};
  const pct = o.saving_pct ? `<span class="pct">−${o.saving_pct}%</span>` : '';
  const was = o.price_before ? `<span class="was tnum">${fmt(o.price_before)} €</span>` : '';
  const price = o.price == null ? '<span class="price">—</span>'
    : `<span class="price tnum">${fmt(o.price)}<small> €</small></span>`;
  // The label sits underneath; a removed/never-loading image reveals it, so
  // cards keep a consistent shape whether or not the chain allows hotlinking.
  // IMG holds the cached thumbnails; the label underneath shows through for
  // anything that failed to cache.
  const src = IMG[o.img] || null;
  const thumb = `<div class="thumb-wrap"><span class="fb">${esc(
      o.group || o.category || '')}</span>` +
    (src ? `<img class="thumb" src="${src}" alt="" loading="lazy"
         onerror="this.remove()">` : '') + `</div>`;
  const flags = [];
  if (o.free_label) flags.push(`<span class="applbl freeflag">${esc(o.free_label)}</span>`);
  if (o.app_price != null) flags.push(`<span class="applbl">App ${fmt(o.app_price)} €</span>`);
  (o.raw_labels || []).slice(0, 2).forEach(l => {
    if (l && l.length < 26) flags.push(`<span class="applbl">${esc(l)}</span>`);
  });
  const n = (o.markets || []).length;
  return `<button type="button" class="card" data-i="${o._i}"
      style="--rail:${c.color || '#888'}">
    <div class="hd"><span class="chain">${esc(c.name || o.chain)}</span>
      <span class="cat">${esc(o.group || o.category || '')}</span></div>
    ${thumb}
    <div class="t">${esc(o.title)}</div>
    ${o.quantity ? `<div class="q">${esc(String(o.quantity).slice(0, 90))}</div>` : ''}
    ${flags.length ? `<div>${flags.join(' ')}</div>` : ''}
    <div class="foot">
      <div>${price}${was ? '<br>' + was : ''}
        ${o.base_price ? `<div class="base">${esc(o.base_price)}</div>` : ''}</div>
      ${pct}
    </div>
    <div class="mk">${n ? `${n} ${n === 1 ? 'Markt' : 'Märkte'}` : 'ohne Marktzuordnung'}</div>
  </button>`;
}

function render(append) {
  const rows = filtered();
  const slice = rows.slice(0, state.shown);
  const grid = document.getElementById('grid');
  grid.innerHTML = slice.map(card).join('');
  document.getElementById('count').innerHTML =
    `<b>${rows.length}</b> Angebote` +
    (state.chain === 'all' ? '' : ` bei ${esc(CH[state.chain].name)}`) +
    (state.cat === 'all' ? '' : ` · ${esc(state.cat)}`) +
    (state.onlyFree ? ' · nur Gratis, 1+1 und Cashback' : '') +
    (state.q ? ` · Suche „${esc(state.q)}“` : '');
  document.getElementById('more').hidden = rows.length <= state.shown;
  document.getElementById('none').hidden = rows.length !== 0;
}

/* ---------- offer detail ---------- */
const dlg = document.getElementById('detail');
const dlgBody = document.getElementById('dlgbody');

function marketRows(chain, ids) {
  const all = MARKETS[chain] || [];
  const want = new Set(ids || []);
  const rows = all.filter(m => want.has(m.market_id));
  // Keep the resolver's order (nearest first) but push unknown ids to the end.
  const known = new Set(rows.map(m => m.market_id));
  (ids || []).forEach(id => {
    if (!known.has(id)) rows.push({market_id: id, name: null, city: null});
  });
  return rows;
}

function detailHTML(o) {
  const c = CH[o.chain] || {};
  const src = IMG[o.img] || null;
  const ids = o.markets || [];
  const total = (MARKETS[o.chain] || []).length;
  const rows = marketRows(o.chain, ids);
  const perMarket = c.per_market;

  const facts = [];
  const add = (k, v) => { if (v != null && v !== '') facts.push([k, v]); };
  add('Menge', o.quantity);
  add('Grundpreis', o.base_price);
  if (o.price_before != null) add('Vorher', fmt(o.price_before) + ' €');
  if (o.saving_abs != null) add('Ersparnis', fmt(o.saving_abs) + ' €' +
    (o.saving_pct ? ` (${o.saving_pct} %)` : ''));
  if (o.app_price != null) add('App-Preis', fmt(o.app_price) + ' €' +
    (o.app_discount ? ` (${esc(o.app_discount)})` : ''));
  if (o.deposit != null) add('Pfand', fmt(o.deposit) + ' €');
  add('Warengruppe', o.group);
  add('Rubrik der Kette', o.category);
  if (o.valid_from || o.valid_to)
    add('Gültig', [o.valid_from, o.valid_to].filter(Boolean).join(' – '));
  if ((o.raw_labels || []).length) add('Hinweise', o.raw_labels.join(', '));

  const mnote = perMarket
    ? `Erfasst in <b>${ids.length}</b> von ${total} ${esc(c.name)}-Märkten im Umkreis.`
    : `${esc(c.name)} führt ein Sortiment für die ganze Region — das Angebot gilt in
       allen <b>${total}</b> erfassten Filialen im Umkreis.`;

  return `
    <div class="dlg-hd" style="--rail:${c.color || '#888'}">
      <div class="grow2">
        <div class="dlg-chain">${esc(c.name || o.chain)}</div>
        <h2>${esc(o.title)}</h2>
      </div>
      <button type="button" class="dlg-close" id="dlgx" aria-label="Schließen">×</button>
    </div>
    <div class="dlg-body">
      <div class="dlg-top">
        <div class="dlg-img">${src ? `<img src="${src}" alt="">`
          : `<span class="fb">${esc(o.group || '')}</span>`}</div>
        <div class="dlg-facts">
          <div class="dlg-price">
            ${o.price == null ? '<span class="price">—</span>'
              : `<span class="price tnum">${fmt(o.price)}<small> €</small></span>`}
            ${o.price_before ? `<span class="was tnum">${fmt(o.price_before)} €</span>` : ''}
            ${o.saving_pct ? `<span class="pct">−${o.saving_pct}%</span>` : ''}
          </div>
          ${o.free_label ? `<div><span class="applbl freeflag">${esc(o.free_label)}</span></div>` : ''}
          <dl class="dl">${facts.map(([k, v]) =>
            `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
        </div>
      </div>
      ${o.free_evidence ? `<div class="dlg-sec">
        <h3>Fundstelle</h3>
        <p class="hint">Der Text, auf den sich die Gratis-Einstufung stützt.</p>
        <div class="evbox">${esc(o.free_evidence)}</div></div>` : ''}
      <div class="dlg-sec">
        <h3>Wo es das gibt</h3>
        <div class="mnote" style="--rail:${c.color || '#888'}">${mnote}</div>
        ${rows.length ? `<div class="mlist" style="margin-top:9px">${rows.map(m => `
          <div class="mrow">
            <span class="d">${m.distance_km != null ? m.distance_km.toFixed(1) + ' km' : '—'}</span>
            <span class="nm">${esc(m.name || m.street || m.market_id)}</span>
            <span class="ad">${esc([m.street && m.name ? m.street : null,
                                    [m.zip, m.city].filter(Boolean).join(' ')]
                                   .filter(Boolean).join(', '))}</span>
          </div>`).join('')}</div>`
          : '<p class="hint" style="margin-top:9px">Für diese Kette liegt keine Filialliste vor.</p>'}
      </div>
    </div>`;
}

function openDetail(i) {
  const o = DATA.offers[i];
  if (!o) return;
  dlgBody.innerHTML = detailHTML(o);
  document.getElementById('dlgx').addEventListener('click', () => dlg.close());
  if (!dlg.open) dlg.showModal();
  dlgBody.querySelector('.dlg-body').scrollTop = 0;
}

document.getElementById('grid').addEventListener('click', e => {
  const b = e.target.closest('.card');
  if (b) openDetail(Number(b.dataset.i));
});
document.querySelector('.free-grid, .band')?.addEventListener('click', e => {
  const b = e.target.closest('[data-i]');
  if (b) openDetail(Number(b.dataset.i));
});
dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });

render();
</script>
"""


def collect_images(d):
    """Inline every cached thumbnail as a data URI.

    One self-contained file then works three ways: opened from disk, served,
    and published as an Artifact (where external image hosts are blocked and
    relative paths don't exist). Offers carry a short key into this map instead
    of a URL, which keeps the embedded JSON small.
    """
    images, missing = {}, 0
    for o in d["offers"]:
        rel = o.get("image_local")
        path = os.path.join(WEB, rel) if rel else None
        if not path or not os.path.exists(path):
            o["img"] = None
            missing += 1
        else:
            k = os.path.splitext(os.path.basename(rel))[0]
            if k not in images:
                with open(path, "rb") as fh:
                    images[k] = ("data:image/webp;base64,"
                                 + base64.b64encode(fh.read()).decode())
            o["img"] = k
        # The original URLs are no longer needed by the page.
        o.pop("image", None)
        o.pop("image_local", None)
    return images, missing


def build():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)

    images, missing = collect_images(d)
    for i, o in enumerate(d["offers"]):
        o["_i"] = i

    gen = dt.datetime.fromisoformat(d["generated_at"])
    nxt = gen.date() + dt.timedelta(days=(7 - gen.weekday()) % 7 or 7)

    src_html = []
    for cid, m in d["sources"].items():
        if m["ok"]:
            src_html.append(
                f'<div class="src" style="--rail:{m["color"]}">'
                f'<span class="c tnum">{m["count"]}</span>'
                f'<span class="n">{m["name"]}</span></div>')
        else:
            src_html.append(
                f'<div class="src bad"><span class="c">nicht erreichbar</span>'
                f'<span class="n">{m["name"]}</span></div>')

    free = [o for o in d["offers"] if o.get("free_tier")]
    by_tier = d["counts"]["by_tier"]
    tiers = "".join(
        f'<span class="tier"><span class="k tnum">{by_tier.get(k, 0)}</span>'
        f'{TIER_META[k][0]}</span>'
        for k in ("free", "bogo", "coupon_free", "cashback"))

    if free:
        lede = (f"Diese Woche <b>{len(free)}</b> Treffer aus "
                f"<b>{len(d['offers'])}</b> Angeboten — jeweils mit der Textstelle, "
                "auf die sich die Einstufung stützt.")
        cards = []
        for o in sorted(free, key=lambda x: ("free bogo coupon_free cashback"
                                             .split().index(x["free_tier"]))):
            name = d["sources"].get(o["chain"], {}).get("name", o["chain"])
            price = (f'{o["price"]:.2f}'.replace(".", ",") + " €"
                     if o.get("price") is not None else "")
            thumb = (f'<div class="fthumb"><img src="{images[o["img"]]}" alt=""></div>'
                     if o.get("img") and o["img"] in images else "")
            cards.append(
                f'<article class="fcard" data-i="{o["_i"]}" '
                f'style="cursor:pointer"><div class="top">'
                f'<span class="chain">{_e(name)}</span>'
                f'<span class="badge">{_e(o["free_label"])}</span></div>'
                f'{thumb}'
                f'<div class="t">{_e(o["title"])}</div>'
                + (f'<div class="q base">{price}</div>' if price else "")
                + (f'<div class="ev">{_e(o["free_evidence"])}</div>'
                   if o.get("free_evidence") else "")
                + "</article>")
        block = f'<div class="free-grid">{"".join(cards)}</div>'
    else:
        lede = ("Für diese Woche wurde in keinem der sechs Prospekte ein Gratis-, "
                "1+1- oder Cashback-Angebot ausgewiesen.")
        block = ('<p class="empty">Der Abschnitt bleibt leer, weil die Auswertung '
                 'nichts gefunden hat — nicht, weil sie nicht gesucht hätte. '
                 'Geprüft werden Gratis- und 0,00-€-Auszeichnungen, 1+1- und '
                 '2-für-1-Bündel, Coupon- und App-Zugaben sowie Cashback- und '
                 'Geld-zurück-Aktionen.</p>')

    notes = ['<li>Jede Kette wird an ihrer eigenen Quelle abgefragt — Shop-API, '
             'Prospekt-API oder die gerenderte Angebotsseite des Marktes.</li>']
    for cid, m in d["sources"].items():
        if m.get("note"):
            notes.append(f'<li><b>{_e(m["name"])}:</b> {_e(m["note"])}</li>')
        if not m["ok"]:
            notes.append(f'<li><b>{_e(m["name"])}:</b> diese Woche nicht '
                         f'erreichbar ({_e(m.get("error", ""))}).</li>')
    per, uni = [], []
    for cid, m in d["sources"].items():
        (per if m.get("per_market") else uni).append(
            f'{m["name"]} ({m.get("markets", 0)})')
    if per:
        notes.append("<li><b>Pro Markt erfasst:</b> " + _e(", ".join(per))
                     + " — diese Ketten führen je Filiale ein eigenes Sortiment, "
                       "sie werden einzeln abgefragt.</li>")
    if uni:
        notes.append("<li><b>Ein Sortiment für die Region:</b> " + _e(", ".join(uni))
                     + " — ein Angebot gilt hier in allen erfassten Filialen.</li>")
    notes.append("<li>Filialliste zuletzt aufgelöst am "
                 + _e((d.get("markets_resolved_at") or "")[:10])
                 + " (<code>tools/resolve_markets.py</code>). LIDL veröffentlicht "
                   "keine Filialkoordinaten, dessen Filialen stehen daher ohne "
                   "Entfernungsangabe.</li>")

    # Product groups are recomputed on every build so tuning taxonomy.py needs
    # no re-scrape. The free/cashback verdict deliberately is NOT: run.py
    # classifies against the full advertising text, before it gets trimmed for
    # display, and re-running it here on the trimmed text would quietly drop
    # hits whose evidence sits past the trim. Changing the classifier therefore
    # means re-running the scrape (per chain is fine -- --only merges).
    for o in d["offers"]:
        o["group"] = taxonomy.group_for(o)

    market_data = d.pop("markets", {}) or {}
    n_markets = sum(len(v) for v in market_data.values())

    counts = {}
    for o in d["offers"]:
        g = o.get("group") or "Sonstiges"
        counts[g] = counts.get(g, 0) + 1
    catopts = "".join(
        f'<option value="{_e(g)}">{_e(g)} ({counts[g]})</option>'
        for g in taxonomy.GROUPS if counts.get(g))

    html = (TEMPLATE
            .replace("__CATOPTS__", catopts)
            .replace("__IMAGES__", json.dumps(images, separators=(",", ":")))
            .replace("__MARKETS__", json.dumps(market_data,
                                               ensure_ascii=False, separators=(",", ":")))
            .replace("__JSON__", json.dumps(d, ensure_ascii=False, separators=(",", ":")))
            .replace("__SOURCES__", "".join(src_html))
            .replace("__TIERS__", tiers)
            .replace("__BANDLEDE__", lede)
            .replace("__FREEBLOCK__", block)
            .replace("__NOTES__", "".join(notes))
            .replace("__WEEK__", d["iso_week"].replace("-W", " / KW "))
            .replace("__NMARKETS__", str(n_markets))
            .replace("__RADIUS__", str(d.get("radius_km", "")))
            .replace("__TOTAL__", str(d["counts"]["total"]))
            .replace("__FREECOUNT__", str(d["counts"]["free"]))
            .replace("__STAMP__", gen.strftime("%d.%m.%Y, %H:%M"))
            .replace("__NEXT__", nxt.strftime("%d.%m."))
            .replace("__CITY__", d["location"]["city"])
            .replace("__PLZ__", d["location"]["plz"]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {OUT}  ({len(html) / 1e6:.1f} MB, {d['counts']['total']} offers, "
          f"{len(images)} images inlined, {missing} without, "
          f"{d['counts']['free']} free)")
    return OUT


def _e(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
