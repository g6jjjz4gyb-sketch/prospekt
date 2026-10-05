#!/bin/bash
# Weekly refresh: scrape all chains, cache images, rebuild the website.
#
# Runs Monday 06:30, again every day at 12:30, and at login -- but only
# actually scrapes when the data is not already from the current ISO week.
# The extra triggers exist because launchd catches up a missed job after
# *sleep* but not after a *shutdown*: the Mac was switched off at 06:30 on
# 2026-08-31 and that week's run was simply skipped.
set -u
# Derived from this script's own location, so the project can be moved
# without editing anything. It must live outside ~/Desktop, ~/Documents and
# ~/Downloads: macOS denies background agents read access there, which is what
# silently broke the 2026-08-31 run.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$BASE/.venv/bin/python"
LOCK="$BASE/logs/.refresh.lock"
mkdir -p "$BASE/logs"
LOG="$BASE/logs/refresh-$(date +%Y-W%V).log"

log() { echo "$*" >>"$LOG"; }

# Only one run at a time; a stale lock from a killed run is cleared after 2h.
if [ -e "$LOCK" ]; then
  if [ -n "$(find "$LOCK" -mmin +120 2>/dev/null)" ]; then
    rm -f "$LOCK"
  else
    log "$(date '+%F %T') übersprungen - läuft bereits (PID $(cat "$LOCK" 2>/dev/null))"
    exit 0
  fi
fi
echo $$ >"$LOCK"
trap 'rm -f "$LOCK"' EXIT

# The site is normally refreshed by GitHub Actions, which runs whether or not
# this Mac is on. So first ask the published page which week it is showing: if
# it is already current, this machine has nothing to do. Only the first 64 KB
# are fetched -- the masthead sits near the top of a 9 MB file.
PUBLISHED_URL="https://g6jjjz4gyb-sketch.github.io/prospekt/"
if [ "${1:-}" != "--force" ]; then
  week_now=$(date '+%G / KW %V')
  head_html=$(curl -sL --max-time 25 -r 0-65535 "$PUBLISHED_URL" 2>/dev/null) || head_html=""
  if [ -n "$head_html" ] && printf '%s' "$head_html" | grep -q "Kalenderwoche <b>$week_now</b>"; then
    log "$(date '+%F %T') übersprungen - veröffentlichte Seite ist aktuell ($week_now)"
    exit 0
  fi
fi

# Skip unless the local data is older than the current ISO week.
if [ "${1:-}" != "--force" ]; then
  if BASE="$BASE" "$PY" - <<'PYEOF'
import datetime as dt, json, os, sys
p = os.path.join(os.environ["BASE"], "data", "latest.json")
try:
    with open(p) as f:
        have = json.load(f).get("iso_week")
except Exception:
    sys.exit(1)                      # no data at all -> scrape
iso = dt.date.today().isocalendar()
sys.exit(0 if have == f"{iso[0]}-W{iso[1]:02d}" else 1)
PYEOF
  then
    log "$(date '+%F %T') übersprungen - Daten sind aktuell"
    exit 0
  fi
fi

{
  echo "=== refresh started $(date '+%Y-%m-%d %H:%M:%S') ==="
  cd "$BASE" || exit 1
  "$PY" run.py
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "!! scrape failed (exit $rc) - keeping the previous website"
    exit $rc
  fi
  "$PY" tools/images.py
  "$PY" build_site.py
  # Publishing must never fail the refresh, but its errors belong in the log.
  "$BASE/tools/publish.sh" || echo "!! publish fehlgeschlagen (Website lokal aktuell)"
  echo "=== refresh finished $(date '+%Y-%m-%d %H:%M:%S') ==="
} >>"$LOG" 2>&1

ls -1t "$BASE"/logs/refresh-*.log 2>/dev/null | tail -n +9 | xargs -r rm --
