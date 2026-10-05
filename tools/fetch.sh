#!/bin/bash
# fetch.sh <url> [outfile] [extra curl args...]
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
URL="$1"; OUT="${2:-/dev/stdout}"; shift 2 2>/dev/null
curl -sL --compressed -A "$UA" \
 -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8' \
 -H 'Accept-Language: de-DE,de;q=0.9,en;q=0.8' \
 -H 'sec-ch-ua: "Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"' \
 -H 'sec-ch-ua-mobile: ?0' -H 'sec-ch-ua-platform: "macOS"' \
 -H 'Sec-Fetch-Dest: document' -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Site: none' -H 'Sec-Fetch-User: ?1' \
 -H 'Upgrade-Insecure-Requests: 1' \
 -o "$OUT" -w "http=%{http_code} size=%{size_download} url=%{url_effective}\n" --max-time 30 "$@" "$URL"
