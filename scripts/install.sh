#!/usr/bin/env bash
# Restores the Glance dashboard from this repo onto a Docker host (run as root on the machine that will run Glance).
#
#   git clone git@github.com:WB2024/WBs_Glances.git && cd WBs_Glances
#   sudo scripts/install.sh            # 1st run: copies files, creates /opt/glance/.env from the example and stops
#   sudo nano /opt/glance/.env         # fill in hosts, keys and the PIN
#   sudo scripts/install.sh            # 2nd run: PIN config, env split, build and start both containers
#
# Safe to re-run: existing .env files and your data (bookmarks, notes, to-do, feeds) are never overwritten.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OPT=/opt

die() { echo "error: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "run as root (sudo scripts/install.sh)"
command -v docker >/dev/null || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is not installed"
command -v python3 >/dev/null || die "python3 is not installed"

echo "==> copying files into $OPT (existing data files are kept)"
mkdir -p "$OPT/glance" "$OPT/glance-admin" "$OPT/stacks"
copy() {   # copy SRC DST [ignore-existing]
  if command -v rsync >/dev/null; then rsync -a ${3:+--ignore-existing} "$1/" "$2/"; else cp -a${3:+n} "$1/." "$2/"; fi
}
copy "$REPO/opt/glance-admin" "$OPT/glance-admin"
copy "$REPO/opt/stacks" "$OPT/stacks"
copy "$REPO/opt/glance/tools" "$OPT/glance/tools"
copy "$REPO/opt/glance/assets" "$OPT/glance/assets"
copy "$REPO/opt/glance/config" "$OPT/glance/config" ignore
mkdir -p "$OPT/glance/data"
copy "$REPO/opt/glance/data" "$OPT/glance/data" ignore
install -m 755 "$REPO/opt/glance/check_pages.py" "$OPT/glance/check_pages.py"
install -m 755 "$REPO/scripts/make_pin_config.py" "$OPT/glance/tools/make_pin_config.py"
mkdir -p "$OPT/glance/assets/favicons" "$OPT/glance/assets/images"
chown -R 1000:1000 "$OPT/glance/data" "$OPT/glance/config/data" "$OPT/glance/assets/favicons"

if [ ! -f "$OPT/glance/.env" ]; then
  install -m 600 "$REPO/opt/glance/.env.example" "$OPT/glance/.env"
  echo
  echo "Created $OPT/glance/.env from the example. Edit it (hosts, keys, GLANCE_PIN), then run this script again."
  exit 0
fi
chmod 600 "$OPT/glance/.env"

echo "==> PIN lock configuration"
if grep -qE '^GLANCE_PIN=.+' "$OPT/glance/.env"; then
  python3 "$OPT/glance/tools/make_pin_config.py" > "$OPT/glance/assets/glance/wb-restricted-config.js"
else
  echo "   no GLANCE_PIN set: the locked widgets will say 'not configured' until you set one and re-run"
fi

echo "==> price-watch container (changedetection.io) and its API key"
( cd "$OPT/stacks/changedetection" && docker compose up -d )
for _ in $(seq 1 30); do [ -s "$OPT/stacks/changedetection/datastore/changedetection.json" ] && break; sleep 2; done
python3 - <<'PY'
import json, re
env = open("/opt/glance/.env", encoding="utf-8").read()
if re.search(r"^CHANGEDETECTION_KEY=.+", env, re.M):
    raise SystemExit
try:
    d = json.load(open("/opt/stacks/changedetection/datastore/changedetection.json"))
except OSError:
    raise SystemExit("   changedetection.io has not written its settings yet: re-run this script in a minute to pick up its API key")
def find(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "api_access_token" and v:
                return v
            r = find(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = find(v)
            if r:
                return r
key = find(d) or ""
env = re.sub(r"^CHANGEDETECTION_KEY=.*\n?", "", env, flags=re.M).rstrip("\n") + "\nCHANGEDETECTION_KEY=%s\n" % key
open("/opt/glance/.env", "w", encoding="utf-8").write(env)
print("   stored the changedetection.io API key" if key else "   could not find the API key yet")
PY

echo "==> splitting the env: Glance only receives the variables its config uses"
python3 "$OPT/glance/tools/sync_env.py"
# glance-admin has its own env file with just the names its compose file lists
python3 - <<'PY'
import re
master = {}
for line in open("/opt/glance/.env", encoding="utf-8"):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        master[k.strip()] = v.split("  #")[0].rstrip("\n").strip()
names = sorted(set(re.findall(r"\$\{([A-Z0-9_]+)(?::-[^}]*)?\}", open("/opt/stacks/glance-admin/compose.yaml", encoding="utf-8").read())))
with open("/opt/stacks/glance-admin/.env", "w", encoding="utf-8") as f:
    for n in names:
        if master.get(n, "") != "":
            f.write("%s=%s\n" % (n, master[n]))
print("   glance-admin env: %d of %d variables set" % (sum(1 for n in names if master.get(n)), len(names)))
PY
chmod 600 "$OPT/stacks/glance-admin/.env"

echo "==> building and starting glance-admin, then Glance"
( cd "$OPT/stacks/glance-admin" && docker compose up -d --build )
( cd "$OPT/stacks/glance" && docker compose up -d )
docker image prune -f >/dev/null
sleep 8
python3 "$OPT/glance/check_pages.py" || true
echo
echo "Done. Open http://$(hostname -I | awk '{print $1}'):3002"
echo "Hosts that run Docker apps you want listed on the Infra page need the agent + lister: see README.md > Other hosts."
