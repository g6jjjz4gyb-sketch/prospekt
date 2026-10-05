"""Plain-HTTP fetcher for sources that don't need a browser.

Transport is curl, not urllib: several of these hosts negotiate a TLS profile
Python's stock context can't match (endpoints.leaflets.schwarz fails the
handshake outright), and Akamai fronts others and wants a full browser header
set. curl gives us both for free.
"""
import json, subprocess

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BASE_HEADERS = [
    "Accept-Language: de-DE,de;q=0.9,en;q=0.8",
    'sec-ch-ua: "Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile: ?0",
    'sec-ch-ua-platform: "macOS"',
    "Sec-Fetch-Dest: document",
    "Sec-Fetch-Mode: navigate",
    "Sec-Fetch-Site: none",
    "Upgrade-Insecure-Requests: 1",
]
HTML_ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8")


class FetchError(RuntimeError):
    pass


def get(url, timeout=40, accept=HTML_ACCEPT, referer=None):
    cmd = ["curl", "-sL", "--compressed", "-A", UA,
           "--max-time", str(timeout), "-w", "\n%{http_code}"]
    for h in BASE_HEADERS:
        cmd += ["-H", h]
    cmd += ["-H", f"Accept: {accept}"]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
    if p.returncode != 0:
        raise FetchError(f"curl exit {p.returncode}: {p.stderr[:200]}")
    body, _, code = p.stdout.rpartition("\n")
    if code.strip() != "200":
        raise FetchError(f"HTTP {code.strip()} for {url[:100]}")
    return body


def get_json(url, **kw):
    kw.setdefault("accept", "application/json")
    return json.loads(get(url, **kw))
