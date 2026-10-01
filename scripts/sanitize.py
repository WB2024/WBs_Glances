#!/usr/bin/env python3
"""Builds the public, sanitised copy of the Glance setup from a raw export of the live server.

    python scripts/sanitize.py RAW_DIR OUT_DIR [--env-values FILE ...] [--keep-private-names]

RAW_DIR  a copy of /opt/glance, /opt/glance-admin and /opt/stacks/{glance,glance-admin,glance-agent} (scripts/export.sh makes it)
OUT_DIR  the repo root; the tree is written under OUT_DIR/opt/...

What it does
  * copies only an allow-list of files (config, scripts, source, compose files); never .env files, caches, notes or backups
  * replaces personal data: weather location, local news feeds, personal bookmarks, wallpaper, PIN hash, private library names
  * renames the two PIN-locked "private" apps to neutral placeholders (PRIVA / PRIVB) unless --keep-private-names is given
  * regenerates the Bookmarks, News and Video News page files from the sanitised data
  * scans the result: it fails (exit 2) if any value from the real .env files, any e-mail address or any long token is still present
Nothing here talks to the network.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys

ALLOW = [  # (source relative to RAW_DIR, destination relative to OUT_DIR/opt)
    ("opt/glance/config/glance.yml", "glance/config/glance.yml"),
    ("opt/glance/config/pages", "glance/config/pages"),
    ("opt/glance/assets/glance/custom.css", "glance/assets/glance/custom.css"),
    ("opt/glance/assets/glance/wb-home.js", "glance/assets/glance/wb-home.js"),
    ("opt/glance/assets/glance/wb-restricted.js", "glance/assets/glance/wb-restricted.js"),
    ("opt/glance/assets/glance/rustydisc.png", "glance/assets/glance/rustydisc.png"),
    ("opt/glance/tools", "glance/tools"),
    ("opt/glance/check_pages.py", "glance/check_pages.py"),
    ("opt/glance/data/channels.json", "glance/data/channels.json"),
    ("opt/glance/data/news.json", "glance/data/news.json"),
    ("opt/glance/data/bookmarks.json", "glance/data/bookmarks.json"),
    ("opt/glance-admin", "glance-admin"),
    ("opt/stacks/glance/compose.yaml", "stacks/glance/compose.yaml"),
    ("opt/stacks/glance-admin/compose.yaml", "stacks/glance-admin/compose.yaml"),
    ("opt/stacks/glance-agent/compose.yaml", "stacks/glance-agent/compose.yaml"),
    ("opt/stacks/glance-agent/lister", "stacks/glance-agent/lister"),
]
SKIP_NAMES = {".env", "glance.env", "__pycache__"}
SKIP_SUFFIX = (".pyc", ".bak", ".tmp", ".pre-cleanup")
TEXT_SUFFIX = (".py", ".yml", ".yaml", ".js", ".css", ".json", ".md", ".txt", ".sh", ".html", "Dockerfile")

# The private-app rename table lives in scripts/.private-renames.json (git-ignored, so the names it hides are never published):
#   {"regex": [[pattern, replacement], ...], "literal": [[old, new], ...], "survivor": "regex that must not match the output",
#    "drop_feeds": "regex: news feeds whose URL matches are replaced by a national BBC England feed"}
# It also holds anything else that identifies the owner (home town, private app names).
RENAMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".private-renames.json")
RENAMES = {"regex": [], "literal": [], "survivor": "", "drop_feeds": ""}


def load_renames(required):
    if os.path.exists(RENAMES_FILE):
        with open(RENAMES_FILE, encoding="utf-8") as f:
            RENAMES.update(json.load(f))
    elif required:
        sys.exit("missing %s (the rename table for the private apps). Create it, or pass --no-private-renames if there is nothing to hide." % RENAMES_FILE)


PERSONAL_BOOKMARK_GROUPS = {"Communication", "Networking", "Android", "Work", "Music Downloads", "Download Sites", "Game Downloads", "More Bookmarks", "Private"}
PERSONAL_BOOKMARK_LINKS = {"My Github", "SR Github", "EE account", "ISH", "Gobble Bot", "Elder Plinius"}


def is_text(path):
    return path.endswith(TEXT_SUFFIX) or os.path.basename(path) == "Dockerfile"


def copy_tree(raw, out, keep_names):
    n = 0
    for src_rel, dst_rel in ALLOW:
        src = os.path.join(raw, src_rel)
        dst = os.path.join(out, "opt", dst_rel)
        pairs = []
        if os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in SKIP_NAMES and d != "retired" and d != "legacy"]
                for f in files:
                    if f in SKIP_NAMES or f.endswith(SKIP_SUFFIX) or ".pre-" in f:
                        continue
                    s = os.path.join(root, f)
                    pairs.append((s, os.path.join(dst, os.path.relpath(s, src))))
        elif os.path.isfile(src):
            pairs.append((src, dst))
        for s, d in pairs:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if is_text(s):
                with open(s, encoding="utf-8", newline="") as f:
                    text = f.read()
                text = text.replace("\r\n", "\n")
                text = transform(s, text, keep_names)
                with open(d, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            else:
                shutil.copyfile(s, d)
            n += 1
    return n


def rename_private(text):
    for old, new in RENAMES["literal"]:
        text = text.replace(old, new)
    for pat, rep in RENAMES["regex"]:
        text = re.sub(pat, rep, text)
    return text


def transform(path, text, keep_names):
    base = os.path.basename(path)
    p = path.replace("\\", "/")
    if base == "custom.css":
        text = re.sub(r'linear-gradient\(([^;]*?)\),\s*url\("/assets/images/Backgrounds/[^"]+"\);',
                      lambda m: "linear-gradient(%s);   /* add your own wallpaper as a second layer: , url(\"/assets/images/wallpaper.jpg\") */" % m.group(1), text, flags=re.S)
        text = text.replace("/* the old Homepage wallpaper, dimmed well below the content */", "/* optional wallpaper layer, dimmed well below the content */")
    if base == "app.py":
        text = text.replace('"AudioBooks P"', '"Private"')
    if base == "compose.yaml" and "glance-admin" in p:
        text = text.replace("ABS_RESTRICTED=AudioBooks P", "ABS_RESTRICTED=${ABS_RESTRICTED:-Private}")
        text = text.replace("BOOKSTACK_HIDE_BOOKS=finance", "BOOKSTACK_HIDE_BOOKS=${BOOKSTACK_HIDE_BOOKS:-}")
    if base == "wb-restricted-config.js":
        text = "/* generated by tools/make_pin_config.py: salted SHA-256 of the restricted-row PIN */\nwindow.WB_RESTRICTED = {salt: \"\", hash: \"\"};\n"
    if not keep_names:
        text = rename_private(text)
        if base == "infra.py":
            text = text.replace('re.compile(r"immich|', 're.compile(os.environ.get("PRIVATE_STACKS", "immich"), re.I)  # ')
    return text


# ----------------------------------------------------------------------------- data files
def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def sanitise_data(out):
    glance = os.path.join(out, "opt", "glance")
    admin = os.path.join(out, "opt", "glance-admin")
    # --- bookmarks: a generic starter set, one example private group
    bm = load_module(os.path.join(admin, "bookmarks.py"), "bm")
    with open(os.path.join(glance, "data", "bookmarks.json"), encoding="utf-8") as f:
        data = json.load(f)
    kept_groups = 0
    for col in data["columns"]:
        keep = []
        for g in col["groups"]:
            if g["title"] in PERSONAL_BOOKMARK_GROUPS or g.get("private"):
                continue
            g["links"] = [l for l in g["links"] if l["title"] not in PERSONAL_BOOKMARK_LINKS
                          and not re.search(r"(^|//)(192\.168\.|10\.|localhost|127\.)|\.wbhomelab", l["url"])]
            for l in g["links"]:
                if (l.get("icon") or "").startswith("/assets/"):
                    l["icon"] = "mdi:link-variant"              # local icon files are not part of the repo
            if g["links"]:
                keep.append(g)
                kept_groups += 1
        col["groups"] = keep
    data["columns"][2]["groups"].append({"id": "gprivateexamp", "title": "Private", "color": "85 55 60", "private": True,
                                         "links": [{"id": "lprivateexamp", "title": "Example private link", "url": "http://192.168.1.50:2283", "icon": "mdi:lock"}]})
    write(os.path.join(glance, "data", "bookmarks.json"), json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    write(os.path.join(glance, "config", "data", "bookmarks.yml"), bm.render_yaml(data))
    # --- news: drop the two local-paper feeds (they name a town), add a national England feed
    nw = load_module(os.path.join(admin, "news.py"), "nw")
    with open(os.path.join(glance, "data", "news.json"), encoding="utf-8") as f:
        news = json.load(f)
    for g in news["groups"]:
        if g["kind"] == "rss":
            before = len(g["feeds"])
            g["feeds"] = [x for x in g["feeds"] if not (RENAMES.get("drop_feeds") and re.search(RENAMES["drop_feeds"], x["url"], re.I))]
            if len(g["feeds"]) != before:
                g["feeds"].append({"url": "https://feeds.bbci.co.uk/news/england/rss.xml", "title": "BBC England"})
    write(os.path.join(glance, "data", "news.json"), json.dumps(news, indent=1, ensure_ascii=False) + "\n")
    write(os.path.join(glance, "config", "data", "news.yml"), nw.render_yaml(news))
    # --- video channels
    ch = load_module(os.path.join(admin, "channels.py"), "ch")
    with open(os.path.join(glance, "data", "channels.json"), encoding="utf-8") as f:
        chs = json.load(f)["channels"]
    write(os.path.join(glance, "config", "data", "video-news.yml"), ch.render_yaml(chs))
    # --- empty personal state
    write(os.path.join(glance, "data", "notes.json"), json.dumps({"text": "", "updated": 0}, indent=1) + "\n")
    write(os.path.join(glance, "data", "todos.json"), json.dumps({"items": []}, indent=1) + "\n")
    write(os.path.join(glance, "assets", "glance", "wb-restricted-config.js"), transform("wb-restricted-config.js", "", True))
    return kept_groups


ENV_EXAMPLE = """# Copy to /opt/glance/.env and fill in. This is the MASTER file: every host address and every secret lives here.
# tools/sync_env.py writes /opt/glance/glance.env (only the variables the Glance config uses); scripts/install.sh derives the glance-admin env.
# The names below match the sanitised config. PRIVA_* / PRIVB_* are the two PIN-locked "private" apps.

# ---- PIN for the locked rows (used by tools/make_pin_config.py; the PIN itself is never served to the browser)
GLANCE_PIN=

# ---- hosts (not secret). A change needs: cd /opt/stacks/glance && docker compose up -d
HOST_SVC=192.168.1.110        # the box that runs Glance, glance-admin and most services
HOST_JELLY=192.168.1.111
HOST_AUTO=192.168.1.112       # Home Assistant + Frigate
HOST_DEVUAN=192.168.1.106     # a second Docker host (private apps)
HOST_PVE4=192.168.1.60        # Proxmox VE nodes
HOST_PVE2=192.168.1.59
HOST_PBS=192.168.1.250        # Proxmox Backup Server
HOST_PIHOLE1=192.168.1.53
HOST_PIHOLE2=192.168.1.54
HOST_ROUTER=192.168.1.254
HOST_CORE=192.168.1.3         # switches / access point shown on the Networking page
HOST_OFFICE_SW=192.168.1.10
HOST_AP=192.168.1.52

# ---- service keys (read-only keys wherever the service allows it)
JELLYFIN_USER_ID=
JELLYFIN_KEY=
NAVIDROME_USER=
NAVIDROME_TOKEN=
NAVIDROME_SALT=
AUDIOBOOKSHELF_KEY=
ABS_KEY=
ABS_RESTRICTED=Private        # name of the Audiobookshelf library to treat as private
SABNZBD_KEY=
DEVUAN_SAB_KEY=
RADARR_KEY=
SONARR_KEY=
LIDARR_KEY=
PROWLARR_KEY=
SEERR_KEY=
SLSKD_KEY=
PIHOLE_KEY=
PRIVA_KEY=
PRIVB_KEY=
IMMICH_URL=http://192.168.1.106:2283
IMMICH_KEY=
PROXMOX_USER=api@pam!glance          # an API token id; give it the PVEAuditor role
PROXMOX_PASSWORD=                    # the token secret
PBS_PASSWORD=
TAILSCALE_OAUTH_ID=
TAILSCALE_OAUTH_SECRET=
NPM_USER=
NPM_PASS=
BOOKSTACK_TOKEN=                     # id:secret
BOOKSTACK_HIDE_BOOKS=                # comma-separated book names to leave out of the Tools page
PAPERLESS_TOKEN=
FORGEJO_TOKEN=
GITHUB_USER=                         # your GitHub login (Dev page)
GITHUB_TOKEN=                        # fine-grained, READ-ONLY personal access token (Metadata, Contents, Issues, Pull requests, Actions)

# ---- per-host Glance agent / lister tokens (stacks/glance-agent and tools/host-stack)
AGENT_TOKEN_SVC=
AGENT_TOKEN_JELLY=
AGENT_TOKEN_DEVUAN=
AGENT_TOKEN_PVE4=              # optional: pve4 disk reporter
"""

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_/+-])[A-Fa-f0-9]{32,}(?![A-Za-z0-9_-])")
ALLOWED_EMAIL = re.compile(r"@(example\.com|users\.noreply\.github\.com)$")


def scan(out, secret_values):
    problems = []
    for root, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in (".git", "images")]
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, out)
            if not is_text(path) and not f.endswith((".example", ".md", ".sh")):
                continue
            try:
                text = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for v, key in secret_values.items():
                if v in text:
                    problems.append("%s: contains the value of %s from a real .env file" % (rel, key))
            for m in EMAIL_RE.findall(text):
                if re.match(r"^[A-Z]@", m):
                    continue                        # template placeholder such as @P@.heatmap
                if not ALLOWED_EMAIL.search("@" + m.split("@", 1)[1]) and not m.endswith(("api@pam", "@pam")):
                    problems.append("%s: e-mail address %s" % (rel, m))
            if TOKEN_RE.search(text):
                problems.append("%s: a long hex string (token?)" % rel)
            if RENAMES["survivor"] and re.search(RENAMES["survivor"], text) and not KEEP[0]:
                problems.append("%s: a private-app name survived the renames" % rel)
    return problems


KEEP = [False]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--env-values", nargs="*", default=[], help="real .env files whose values must not appear in the output")
    ap.add_argument("--keep-private-names", action="store_true")
    ap.add_argument("--no-private-renames", action="store_true", help="skip the rename table (nothing to hide)")
    a = ap.parse_args()
    KEEP[0] = a.keep_private_names
    load_renames(required=not (a.keep_private_names or a.no_private_renames))
    opt = os.path.join(a.out, "opt")
    if os.path.isdir(opt):
        shutil.rmtree(opt)
    n = copy_tree(a.raw, a.out, a.keep_private_names)
    groups = sanitise_data(a.out)
    write(os.path.join(a.out, "opt", "glance", ".env.example"), ENV_EXAMPLE)
    secrets = {}
    for p in a.env_values:
        for line in open(p, encoding="utf-8", errors="replace").read().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                key = line.split("=", 1)[0].strip()
                if re.match(r"^(HOST_|.*_LABEL$)", key):
                    continue                      # addresses and labels are not secrets
                if len(v) >= 8 and not re.fullmatch(r"(\d{1,3}\.){3}\d{1,3}|https?://[\d.]+(:\d+)?", v) and v not in ("Private",):
                    secrets[v] = line.split("=", 1)[0].strip()
    problems = scan(os.path.join(a.out, "opt"), secrets)
    print("copied %d files; bookmarks kept %d groups; checked against %d secret values" % (n, groups, len(secrets)))
    if problems:
        print("SANITISER FOUND PROBLEMS:")
        for p in sorted(set(problems)):
            print("  -", p)
        sys.exit(2)
    print("scan clean")


if __name__ == "__main__":
    main()
