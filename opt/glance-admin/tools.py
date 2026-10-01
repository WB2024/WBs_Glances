"""Tools summary for the Glance Tools page (stdlib only; imported by app.py).

Builds one cached document with
  * tiles : a status/detail tile for every small tool (reachability + one useful fact each)
  * paperless / forgejo / bookstack : richer cards (counts, versions, recent activity)
Privacy rules: Paperless shows counts only (never document titles); BookStack recent pages skip the books listed in
BOOKSTACK_HIDE_BOOKS (default: finance); nothing secret is returned and tokens stay in this container.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

HOST = os.environ.get("TOOLS_HOST", "host.docker.internal")      # services LXC, as seen from this container
LINK = os.environ.get("SVC_HOST", "192.168.1.110")               # address the browser should use for links
UA = {"User-Agent": "glance-admin/1"}


def _get(url, headers=None, timeout=6, raw=False):
    h = dict(UA)
    h.update(headers or {})
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        body = r.read()
        return r.status, dict(r.headers), (body if raw else json.loads(body.decode("utf-8"))), int((time.time() - t0) * 1000)


def _up(port, path="/", timeout=4):
    """(up, http-status, latency-ms). 3xx/4xx still mean the service answered."""
    try:
        t0 = time.time()
        urllib.request.urlopen(urllib.request.Request("http://%s:%d%s" % (HOST, port, path), headers=UA), timeout=timeout).read(64)
        return True, 200, int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code < 500, e.code, 0
    except Exception:
        return False, 0, 0


def _age_h(iso):
    import datetime
    try:
        ts = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        return max(0, int((time.time() - ts) / 3600))
    except Exception:
        return None


# --------------------------------------------------------------------------- small tools (tiles)
def t_basic(port, path="/"):
    up, code, ms = _up(port, path)
    return {"up": up, "detail": ("answering in %d ms" % ms) if up and ms else ("answering" if up else "not responding")}


def t_stirling():
    try:
        s, h, d, ms = _get("http://%s:8400/api/v1/info/status" % HOST)
        return {"up": d.get("status") == "UP", "detail": "v%s · %s" % (d.get("version"), d.get("status"))}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_flatnotes():
    try:
        s, h, d, ms = _get("http://%s:8200/api/search?term=*&sort=lastModified&order=desc&limit=500" % HOST)
        n = len(d) if isinstance(d, list) else 0
        return {"up": True, "detail": "%d note%s" % (n, "" if n == 1 else "s")}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_kiwix():
    try:
        s, h, b, ms = _get("http://%s:8090/catalog/v2/entries?count=200" % HOST, raw=True)
        n = len(ET.fromstring(b).findall("{http://www.w3.org/2005/Atom}entry"))
        return {"up": True, "detail": "%d offline libraries" % n}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_kolibri():
    try:
        s, h, d, ms = _get("http://%s:8310/api/public/info/" % HOST)
        return {"up": True, "detail": "v%s · %s" % (d.get("kolibri_version"), d.get("device_name") or "")}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_dozzle():
    try:
        s, h, b, ms = _get("http://%s:9999/api/version" % HOST, raw=True)
        v = re.sub(r"<[^>]+>", "", b.decode()).strip()
        return {"up": True, "detail": "%s · container logs" % v}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_nomad():
    try:
        s, h, d, ms = _get("http://%s:8500/api/system/services" % HOST)
        run = sum(1 for x in d if x.get("status") == "running")
        bad = [x.get("friendly_name") or x.get("service_name") for x in d if x.get("installed") and x.get("status") != "running"]
        return {"up": True, "detail": "%d / %d services running%s" % (run, len(d), (" · " + ", ".join(bad) + " down") if bad else ""),
                "warn": bool(bad)}
    except Exception:
        return {"up": False, "detail": "not responding"}


def t_homebox():
    up, code, ms = _up(8470)
    return {"up": up, "detail": "answering" if up else "not running (crash loop: needs HBOX_AUTH_API_KEY_PEPPER)"}


def t_vaultwarden():
    """Served over Tailscale HTTPS only; judge it by container state through the lister on this host."""
    try:
        tok = os.environ.get("TOKEN_SERVICES", "")
        s, h, d, ms = _get("http://%s:27974/containers" % HOST, {"Authorization": "Bearer " + tok})
        c = next((x for x in d["containers"] if x["name"] == "vaultwarden"), None)
        return {"up": bool(c and c["state"] == "running"), "detail": (c["status"] if c else "container missing")}
    except Exception:
        return {"up": False, "detail": "state unknown"}


# (key, name, group, link-port-or-url, probe function)
TILES = [
    ("flatnotes", "Flatnotes", "Documents & notes", "http://%s:8200" % LINK, t_flatnotes),
    ("stirling", "Stirling PDF", "Documents & notes", "http://%s:8400" % LINK, t_stirling),
    ("cyberchef", "CyberChef", "Utilities", "http://%s:8100" % LINK, lambda: t_basic(8100)),
    ("ittools", "IT Tools", "Utilities", "http://%s:8430" % LINK, lambda: t_basic(8430)),
    ("excalidraw", "Excalidraw", "Utilities", "http://%s:8440" % LINK, lambda: t_basic(8440)),
    ("picard", "Picard (MusicBrainz tagger)", "Utilities", "http://%s:8086" % LINK, lambda: t_basic(8086)),
    ("searxng", "SearXNG", "Utilities", "http://searxng.wbhomelab", lambda: t_basic(8888, "/healthz")),
    ("firefox", "Firefox (remote browser)", "Utilities", "http://%s:5800" % LINK, lambda: t_basic(5800)),
    ("kiwix", "Kiwix", "Reference & learning", "http://%s:8090" % LINK, t_kiwix),
    ("kolibri", "Kolibri", "Reference & learning", "http://%s:8310" % LINK, t_kolibri),
    ("dozzle", "Dozzle", "Admin & ops", "http://%s:9999" % LINK, t_dozzle),
    ("nomad", "NOMAD admin", "Admin & ops", "http://%s:8500" % LINK, t_nomad),
    ("termix", "Termix (SSH)", "Admin & ops", "http://%s:8080" % LINK, lambda: t_basic(8080)),
    ("homebox", "Homebox", "Admin & ops", "http://%s:8470" % LINK, t_homebox),
    ("vaultwarden", "Vaultwarden", "Admin & ops", "https://services.example.ts.net:8443", t_vaultwarden),
]


def _tile(spec):
    key, name, group, url, fn = spec
    try:
        r = fn()
    except Exception as exc:
        r = {"up": False, "detail": "error: %s" % str(exc)[:60]}
    return {"key": key, "name": name, "group": group, "url": url, "up": bool(r["up"]), "detail": r["detail"], "warn": bool(r.get("warn"))}


# --------------------------------------------------------------------------- richer cards
def paperless():
    tok = os.environ.get("PAPERLESS_TOKEN", "")
    h = {"Authorization": "Token " + tok}
    b = "http://%s:8010/api" % HOST
    try:
        _, _, st, _ = _get(b + "/statistics/", h, timeout=30)
        _, _, sx, _ = _get(b + "/status/", h, timeout=30)
        _, _, inbox, _ = _get(b + "/documents/?is_in_inbox=true&page_size=1&fields=id", h, timeout=60)
        _, _, newest, _ = _get(b + "/documents/?ordering=-added&page_size=1&fields=id,added", h, timeout=60)
        total = float(sx["storage"]["total"]) / 1e12
        return {"up": True, "version": sx.get("pngx_version"), "docs": st.get("documents_total"), "inbox": inbox.get("count", 0),
                "tags": st.get("tag_count"), "db_ok": (sx.get("database") or {}).get("status") == "OK",
                "free_tb": round(float(sx["storage"]["available"]) / 1e12, 1), "total_tb": round(total, 1),
                "last_added_h": _age_h(newest["results"][0]["added"]) if newest.get("results") else None}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def forgejo():
    tok = os.environ.get("FORGEJO_TOKEN", "")
    h = {"Authorization": "token " + tok}
    b = "http://%s:3001/api/v1" % HOST
    try:
        _, _, v, _ = _get(b + "/version", h)
        _, hd, repos, _ = _get(b + "/repos/search?sort=updated&order=desc&limit=6", h, timeout=20)
        _, hi, _, _ = _get(b + "/repos/issues/search?state=open&type=issues&limit=1", h, timeout=20)
        recent = [{"name": r["full_name"], "age_h": _age_h(r["updated_at"]), "private": r.get("private", False),
                   "lang": r.get("language") or ""} for r in repos["data"]]
        return {"up": True, "version": str(v.get("version", "")).split("+")[0], "repos": int(hd.get("X-Total-Count", len(recent))),
                "open_issues": int(hi.get("X-Total-Count", 0)), "recent": recent}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def bookstack():
    tok = os.environ.get("BOOKSTACK_TOKEN", "")
    h = {"Authorization": "Token " + tok}
    b = "http://%s:6875/api" % HOST
    hide = {x.strip() for x in os.environ.get("BOOKSTACK_HIDE_BOOKS", "finance").split(",") if x.strip()}
    try:
        counts = {}
        for k in ("books", "pages", "chapters", "shelves"):
            counts[k] = _get("%s/%s?count=1" % (b, k), h, timeout=20)[2].get("total", 0)
        pages = _get(b + "/pages?count=30&sort=-updated_at", h, timeout=20)[2]["data"]
        recent = [{"name": p["name"][:70], "book": p.get("book_slug", ""), "age_h": _age_h(p["updated_at"])}
                  for p in pages if p.get("book_slug") not in hide][:6]
        return dict(up=True, recent=recent, **counts)
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def build():
    with ThreadPoolExecutor(max_workers=8) as ex:
        tiles = list(ex.map(_tile, TILES))
        p, f, bk = ex.submit(paperless), ex.submit(forgejo), ex.submit(bookstack)
        out = {"at": int(time.time()), "tiles": tiles, "paperless": p.result(), "forgejo": f.result(), "bookstack": bk.result()}
    out["up"] = sum(1 for t in tiles if t["up"])
    out["down"] = sum(1 for t in tiles if not t["up"])
    return out
