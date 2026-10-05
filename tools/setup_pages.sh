#!/bin/bash
# One-time setup: create the GitHub repository and switch on GitHub Pages.
#
# Run this once, after `gh auth login`. Everything afterwards is handled by
# tools/publish.sh at the end of each weekly refresh.
set -eu
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGES="$BASE/.pages"
REPO="${1:-prospekt}"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

command -v gh >/dev/null || { echo "gh fehlt: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || {
  echo "Nicht angemeldet. Bitte zuerst ausführen:  gh auth login"; exit 1; }

USER=$(gh api user --jq .login)
echo "GitHub-Konto: $USER"

mkdir -p "$PAGES"
cd "$PAGES"
[ -d .git ] || git init -q -b main
# Repo-local identity: there is no global one, and publish.sh commits later.
git config user.email "$USER@users.noreply.github.com"
git config user.name "$USER"
cp "$BASE/web/index.html" index.html 2>/dev/null || {
  echo "web/index.html fehlt - bitte zuerst build_site.py laufen lassen"; exit 1; }
touch .nojekyll
git add -A >/dev/null
git commit -q -m "Angebote $(date '+%G-W%V')" 2>/dev/null || true

if gh repo view "$USER/$REPO" >/dev/null 2>&1; then
  echo "Repository $USER/$REPO existiert bereits"
  git remote get-url origin >/dev/null 2>&1 || \
    git remote add origin "https://github.com/$USER/$REPO.git"
else
  echo "Lege Repository $USER/$REPO an (öffentlich - GitHub Pages braucht das im Gratis-Tarif)"
  gh repo create "$REPO" --public --source=. --remote=origin --push
fi

git push -f -u origin main
gh api -X POST "repos/$USER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/" \
  >/dev/null 2>&1 && echo "GitHub Pages aktiviert" \
  || echo "GitHub Pages war bereits aktiv (oder wird gleich aktiv)"

echo
echo "Adresse:  https://$USER.github.io/$REPO/"
echo "Die erste Veröffentlichung kann ein bis zwei Minuten dauern."
