"""Latest stable releases of the projects you run, for the Glance Tools page (stdlib only; imported by app.py).

Glance's own `releases` widget uses the GitHub REST API, which allows only 60 anonymous requests per hour per IP; with ~30 repos
and a dashboard that reloads its config often that limit is hit constantly. This module needs no token and no API:
  * the latest *stable* tag comes from the redirect of github.com/<repo>/releases/latest
  * the release date comes from the public Atom feed github.com/<repo>/releases.atom
Results are cached for hours.
"""
import datetime
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

GROUPS = [
    ("Tools I use", ["metabrainz/picard", "beetbox/beets", "yt-dlp/yt-dlp", "Nicotine-Plus/nicotine-plus", "anthropics/claude-code"]),
    ("Media stack", ["Lidarr/Lidarr", "Radarr/Radarr", "Sonarr/Sonarr", "Prowlarr/Prowlarr", "sabnzbd/sabnzbd", "jellyfin/jellyfin",
                     "navidrome/navidrome", "seerr-team/seerr", "slskd/slskd", "TypNull/Tubifarry"]),
    ("Infrastructure", ["pi-hole/pi-hole", "pi-hole/FTL", "tailscale/tailscale", "louislam/dockge", "NginxProxyManager/nginx-proxy-manager",
                        "glanceapp/glance", "blakeblackshear/frigate", "home-assistant/core", "immich-app/immich",
                        "paperless-ngx/paperless-ngx", "BookStackApp/BookStack", "dani-garcia/vaultwarden"]),
]
UA = {"User-Agent": "Mozilla/5.0 (glance-admin releases)"}
ATOM = "{http://www.w3.org/2005/Atom}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _latest_tag(repo):
    op = urllib.request.build_opener(_NoRedirect)
    try:
        op.open(urllib.request.Request("https://github.com/%s/releases/latest" % repo, headers=UA), timeout=15)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        if "/releases/tag/" in loc:
            return urllib.parse.unquote(loc.rsplit("/releases/tag/", 1)[1]), loc
    return None, None


def _dates(repo):
    with urllib.request.urlopen(urllib.request.Request("https://github.com/%s/releases.atom" % repo, headers=UA), timeout=15) as r:
        root = ET.fromstring(r.read())
    out = {}
    for e in root.findall(ATOM + "entry"):
        link = e.find(ATOM + "link").get("href", "")
        tag = urllib.parse.unquote(link.rsplit("/releases/tag/", 1)[-1])
        out[tag] = e.findtext(ATOM + "updated") or ""
    return out


def _one(repo):
    item = {"repo": repo, "name": repo.split("/")[1], "tag": "", "age_h": None, "url": "https://github.com/%s/releases" % repo, "ok": False}
    try:
        tag, loc = _latest_tag(repo)
        if tag:
            item.update(tag=tag, url=loc, ok=True)
            try:
                iso = _dates(repo).get(tag)
                if iso:
                    ts = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
                    item["age_h"] = max(0, int((time.time() - ts) / 3600))
            except Exception:
                pass
    except Exception as exc:
        item["err"] = str(exc)[:60]
    return item


def build():
    repos = [r for _, rs in GROUPS for r in rs]
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = dict(zip(repos, ex.map(_one, repos)))
    groups = [{"title": t, "items": [res[r] for r in rs]} for t, rs in GROUPS]
    return {"at": int(time.time()), "groups": groups, "ok": sum(1 for v in res.values() if v["ok"]), "total": len(res)}
