"""Shared browser session for all chain scrapers.

Every German grocery site here sits behind Akamai/Cloudflare and renders offers
client-side. Rather than forging headers per chain, we drive a real Chromium and
issue the chains' own API calls from inside their page via fetch() -- that
inherits cookies, origin and TLS fingerprint, so the bot walls let them through.
"""
import asyncio, json, re
from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

COOKIE_SELECTORS = [
    '#onetrust-accept-btn-handler',
    'button:has-text("Alle akzeptieren")',
    'button:has-text("Alle Akzeptieren")',
    'button:has-text("Alle zulassen")',
    'button:has-text("Akzeptieren")',
    'button:has-text("Zustimmen")',
    'button:has-text("Einverstanden")',
    '[data-testid="uc-accept-all-button"]',
    '#uc-btn-accept-banner',
]

# Chromium flags + JS patches that strip the obvious "I am automation" tells.
STEALTH_JS = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'languages',{get:()=>['de-DE','de','en-US']});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
window.chrome = window.chrome || {runtime:{}};
const q = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
  p.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : q(p));
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-sandbox",
    "--lang=de-DE",
]


class Session:
    """Async context manager wrapping one Chromium page."""

    def __init__(self, headless=True, capture=False, channel=None):
        self.headless = headless
        self.capture = capture
        # channel='chrome' uses the installed Google Chrome instead of the
        # bundled Chromium; Akamai scores its fingerprint far more kindly.
        self.channel = channel
        self.captured = []          # [(url, json)] when capture=True

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        kw = {"headless": self.headless, "args": LAUNCH_ARGS}
        if self.channel:
            kw["channel"] = self.channel
        self.browser = await self._pw.chromium.launch(**kw)
        self.ctx = await self.browser.new_context(
            user_agent=UA, locale="de-DE", timezone_id="Europe/Berlin",
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
        )
        await self.ctx.add_init_script(STEALTH_JS)
        self.page = await self.ctx.new_page()
        if self.capture:
            self.page.on("response", lambda r: asyncio.create_task(self._grab(r)))
        return self

    async def _grab(self, r):
        try:
            if r.status == 200 and "json" in (r.headers or {}).get("content-type", ""):
                body = await r.body()
                if len(body) > 200:
                    self.captured.append((r.url, json.loads(body)))
        except Exception:
            pass

    async def __aexit__(self, *a):
        try:
            await self.browser.close()
        finally:
            await self._pw.stop()

    # ---------- navigation ----------

    async def goto(self, url, wait="domcontentloaded", timeout=45000,
                   settle=3000, cookies=True):
        await self.page.goto(url, wait_until=wait, timeout=timeout)
        if cookies:
            await self.accept_cookies()
        await self.page.wait_for_timeout(settle)

    async def accept_cookies(self):
        """Dismiss the consent banner, preferring the privacy-preserving choice.

        Banners here (Usercentrics, OneTrust, Cookiebot) mostly live in a shadow
        root and swallow pointer events until dismissed, so we walk shadow roots
        in JS and click there. 'Only necessary' is tried before 'accept all';
        if neither exists the overlay is removed so it stops blocking clicks.
        """
        js = """() => {
          const DENY = ['uc-deny-all-button','onetrust-reject-all-handler',
                        'CybotCookiebotDialogBodyButtonDecline'];
          const ACCEPT = ['uc-accept-all-button','onetrust-accept-btn-handler',
                          'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll'];
          const DENY_TXT = ['nur notwendige','nur essenzielle','ablehnen',
                            'alle ablehnen','only necessary'];
          const ACC_TXT  = ['alle erlauben','alle akzeptieren','alle zulassen',
                            'akzeptieren','zustimmen','einverstanden'];
          const nodes = [];
          const walk = (root, d) => {
            if (d > 6) return;
            let els; try { els = root.querySelectorAll('*'); } catch (e) { return; }
            els.forEach(el => {
              nodes.push(el);
              if (el.shadowRoot) walk(el.shadowRoot, d + 1);
            });
          };
          walk(document, 0);
          const hit = (ids, txts) => nodes.find(el => {
            const tid = el.getAttribute && el.getAttribute('data-testid');
            if (ids.includes(el.id) || ids.includes(tid)) return true;
            if (!/^(BUTTON|A)$/.test(el.tagName)) return false;
            const t = (el.innerText || '').trim().toLowerCase();
            return t && txts.some(x => t === x || t.startsWith(x));
          });
          let el = hit(DENY, DENY_TXT) || hit(ACCEPT, ACC_TXT);
          if (el) { el.click(); return 'clicked:' + (el.getAttribute('data-testid') || el.id || el.innerText.slice(0,20)); }
          const ov = document.querySelector('#usercentrics-root, #onetrust-consent-sdk, #CybotCookiebotDialog');
          if (ov) { ov.remove(); return 'removed-overlay'; }
          return 'none';
        }"""
        for _ in range(3):
            try:
                res = await self.page.evaluate(js)
            except Exception:
                res = 'err'
            if res and res != 'none':
                await self.page.wait_for_timeout(1500)
                # Second pass: some CMPs re-render, and leftovers still block clicks.
                try:
                    await self.page.evaluate(
                        "() => document.querySelectorAll("
                        "'#usercentrics-root,#onetrust-consent-sdk,#CybotCookiebotDialog')"
                        ".forEach(e => e.remove())")
                except Exception:
                    pass
                return res
            await self.page.wait_for_timeout(1500)
        return 'none'

    async def scroll_all(self, rounds=12, step=3000, pause=900):
        """Trigger lazy-loading until the page stops growing."""
        last = 0
        for _ in range(rounds):
            await self.page.mouse.wheel(0, step)
            await self.page.wait_for_timeout(pause)
            h = await self.page.evaluate("document.body.scrollHeight")
            if h == last:
                break
            last = h
        return last

    async def click_all(self, selector, limit=40, pause=1200):
        """Repeatedly click a 'load more' style button while it exists."""
        n = 0
        for _ in range(limit):
            try:
                el = self.page.locator(selector).first
                if not await el.is_visible(timeout=1200):
                    break
                await el.click(timeout=4000)
                await self.page.wait_for_timeout(pause)
                n += 1
            except Exception:
                break
        return n

    # ---------- in-page API access ----------

    async def api(self, url, headers=None, method="GET", body=None):
        """Run fetch() inside the current page so the call carries the site's
        own cookies/origin. Returns parsed JSON or None."""
        js = """
        async ([url, headers, method, body]) => {
          try {
            const r = await fetch(url, {
              method, headers: headers || {},
              body: body ? JSON.stringify(body) : undefined,
              credentials: 'include',
            });
            if (!r.ok) return {__err: r.status};
            const t = await r.text();
            try { return JSON.parse(t); } catch (e) { return {__raw: t.slice(0, 400)}; }
          } catch (e) { return {__err: String(e)}; }
        }"""
        try:
            res = await self.page.evaluate(js, [url, headers or {}, method, body])
        except Exception as e:
            return {"__err": str(e)}
        return res

    async def html(self):
        return await self.page.content()
