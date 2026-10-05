#!/bin/bash
# Push the built website to GitHub Pages.
#
# The site lives on its own branch (`gh-pages`), separate from the source on
# `main`: the page is a single ~9 MB file rewritten in full every week, so each
# publish *replaces* that branch with one fresh commit instead of adding to its
# history. Keeping both on one branch would mean either a repo growing 9 MB a
# week, or a force-push that deletes the source and the CI workflows.
#
# Runs at the end of every refresh -- on this Mac and on the GitHub runner.
# Exits 0 without doing anything until the repository is configured, so a
# refresh never fails merely because publishing is not set up.
set -u
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$BASE/web/index.html"
BRANCH="gh-pages"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

[ -f "$SRC" ] || { echo "publish: web/index.html fehlt"; exit 0; }

# On the runner the checkout itself is the repo; on the Mac it is .pages/.
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  WORK="$BASE/.publish"
  rm -rf "$WORK"; mkdir -p "$WORK"
  cd "$WORK" || exit 0
  git init -q -b "$BRANCH"
  # This is a *second*, freshly created repo -- the identity configured in the
  # checkout does not reach it, and without one `git commit` fails silently
  # enough to look like "nothing to commit".
  git config user.name  "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git remote add origin \
    "https://x-access-token:${GITHUB_TOKEN:-$GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
else
  WORK="$BASE/.pages"
  [ -d "$WORK/.git" ] || { echo "publish: nicht eingerichtet (tools/setup_pages.sh)"; exit 0; }
  cd "$WORK" || exit 0
  git remote get-url origin >/dev/null 2>&1 || {
    echo "publish: kein Remote konfiguriert"; exit 0; }
  git checkout --orphan _publish >/dev/null 2>&1 || exit 1
fi

cp "$SRC" index.html
touch .nojekyll                     # serve the file as-is, no Jekyll build

week=$(date '+%G-W%V')
git add -A >/dev/null
if git diff --cached --quiet; then
  echo "publish: keine Änderung gegenüber dem letzten Stand"; exit 0
fi
git commit -q -m "Angebote $week (Stand $(date '+%Y-%m-%d %H:%M'))" || {
  echo "publish: commit fehlgeschlagen"; exit 1; }
git branch -M "$BRANCH" >/dev/null 2>&1

if git push -f -q origin "$BRANCH" 2>&1; then
  remote=$(git remote get-url origin | sed 's#//[^@]*@#//#')
  echo "publish: $week veröffentlicht -> $remote ($BRANCH)"
  [ -n "${GITHUB_ACTIONS:-}" ] || { git reflog expire --expire=now --all >/dev/null 2>&1
                                    git gc --prune=now -q >/dev/null 2>&1; }
else
  echo "publish: push fehlgeschlagen - Anmeldung prüfen (gh auth status)"
  exit 0
fi
