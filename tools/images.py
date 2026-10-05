#!/usr/bin/env python3
"""Download every offer image once, shrink it, and cache it under web/img/.

Why this exists:
  * NETTO returns 403 to any direct image request, so its images are pulled
    through a browser sitting on netto-online.de (in-page fetch -> data URL).
  * A published Artifact cannot load external hosts at all, so the site needs
    local copies it can either reference or inline.

Images are keyed by a hash of their source URL, so a weekly refresh only
downloads what actually changed. Offers get `image_local` (a path relative to
web/) while `image` keeps the original URL.
"""
import asyncio, base64, hashlib, io, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from PIL import Image

DATA = os.path.join(HERE, "data", "latest.json")
IMGDIR = os.path.join(HERE, "web", "img")
REL = "img"
MAX_PX = 200          # cards render ~96px tall; 200 covers retina
QUALITY = 65
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BROWSER_ONLY = {"netto": "https://www.netto-online.de/filialangebote"}


def key(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def dest(url):
    return os.path.join(IMGDIR, key(url) + ".webp")


def save(raw, path):
    """Normalise whatever the CDN sent into a small WebP thumbnail."""
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return False
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    tmp = path + ".tmp"
    im.save(tmp, "WEBP", quality=QUALITY, method=4)
    os.replace(tmp, path)
    return True


def curl_get(url, referer=None):
    cmd = ["curl", "-sL", "--compressed", "-A", UA, "--max-time", "30",
           "-H", "Accept: image/avif,image/webp,image/apng,*/*;q=0.8",
           "-H", "Accept-Language: de-DE,de;q=0.9"]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, timeout=45)
    return p.stdout if p.returncode == 0 and len(p.stdout) > 200 else None


FETCH_JS = """
async (urls) => {
  const out = {};
  for (const u of urls) {
    try {
      const r = await fetch(u, {credentials: 'include'});
      if (!r.ok) { out[u] = null; continue; }
      const b = await r.blob();
      out[u] = await new Promise(res => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => res(null);
        fr.readAsDataURL(b);
      });
    } catch (e) { out[u] = null; }
  }
  return out;
}"""


async def fetch_via_browser(urls, page_url, log):
    """For hosts that refuse outside clients: fetch from inside their own page."""
    from scrapers.base import Session
    got = 0
    async with Session(channel="chrome") as s:
        await s.goto(page_url, settle=4000)
        for i in range(0, len(urls), 20):
            chunk = urls[i:i + 20]
            try:
                res = await s.page.evaluate(FETCH_JS, chunk)
            except Exception as e:
                log(f"    browser batch failed: {type(e).__name__}")
                continue
            for u, durl in (res or {}).items():
                if not durl or "," not in durl:
                    continue
                try:
                    raw = base64.b64decode(durl.split(",", 1)[1])
                except Exception:
                    continue
                if save(raw, dest(u)):
                    got += 1
            log(f"    {min(i + 20, len(urls))}/{len(urls)}")
    return got


async def main():
    log = lambda m: print(m, flush=True)
    os.makedirs(IMGDIR, exist_ok=True)
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)

    todo, by_chain = {}, {}
    for o in d["offers"]:
        u = o.get("image")
        if not u:
            continue
        if os.path.exists(dest(u)):
            continue
        todo[u] = o["chain"]
    for u, c in todo.items():
        by_chain.setdefault(c, []).append(u)

    cached = sum(1 for o in d["offers"]
                 if o.get("image") and os.path.exists(dest(o["image"])))
    log(f"images: {cached} already cached, {len(todo)} to fetch")

    for chain, urls in sorted(by_chain.items()):
        if chain in BROWSER_ONLY:
            log(f"  {chain}: {len(urls)} via browser (host blocks direct requests)")
            n = await fetch_via_browser(urls, BROWSER_ONLY[chain], log)
        else:
            log(f"  {chain}: {len(urls)} direct")

            def one(u):
                raw = curl_get(u)
                return bool(raw and save(raw, dest(u)))

            with ThreadPoolExecutor(max_workers=8) as pool:
                n = sum(1 for ok in pool.map(one, urls) if ok)
        log(f"  {chain}: {n}/{len(urls)} fetched")

    # Point every offer at its local copy where one exists.
    have = 0
    for o in d["offers"]:
        u = o.get("image")
        if u and os.path.exists(dest(u)):
            o["image_local"] = f"{REL}/{key(u)}.webp"
            have += 1
        else:
            o["image_local"] = None
    d["counts"]["images"] = have
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))

    total = sum(os.path.getsize(os.path.join(IMGDIR, x))
                for x in os.listdir(IMGDIR) if x.endswith(".webp"))
    log(f"images: {have}/{len(d['offers'])} offers have a local thumbnail "
        f"({total / 1e6:.1f} MB on disk)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
