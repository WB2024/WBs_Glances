#!/usr/bin/env bash
# Refreshes this repo from the live server: pulls the running config, sanitises it, shows what changed.
# You then review, commit and push (that is the remote backup).
#
#   scripts/export.sh                      # uses root@192.168.1.110
#   GLANCE_HOST=root@my-host scripts/export.sh
#
# Needs: ssh access to the Glance host, python3 and PyYAML-free stdlib only. Raw files (which include .env files) live in a temp
# folder that is deleted at the end; only the sanitised tree is written into the repo, and the run fails if any real secret value
# is still present in it.
set -euo pipefail
HOST="${GLANCE_HOST:-root@192.168.1.110}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> pulling the live config from $HOST"
ssh "$HOST" 'cd / && tar -cf - \
  --exclude=opt/glance/legacy --exclude=opt/glance/data/cache --exclude=opt/glance/data/covers \
  --exclude=opt/glance/assets/favicons --exclude=opt/glance/.env --exclude=opt/glance/glance.env --exclude=opt/stacks/changedetection/datastore \
  --exclude="*.bak*" --exclude=__pycache__ \
  opt/glance opt/glance-admin opt/stacks/glance opt/stacks/glance-admin opt/stacks/glance-agent opt/stacks/changedetection 2>/dev/null' | tar -xf - -C "$TMP"
ssh "$HOST" 'cat /opt/glance/.env' > "$TMP/master.env"

echo "==> sanitising"
PY="$(command -v python3 || command -v python)"
"$PY" "$REPO/scripts/sanitize.py" "$TMP" "$REPO" --env-values "$TMP/master.env" "$TMP"/opt/stacks/*/.env

echo "==> changes in the repo"
git -C "$REPO" status --short
echo
echo "Review with 'git diff', then: git add -A && git commit -m \"Update config\" && git push"
