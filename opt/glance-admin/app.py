#!/usr/bin/env python3
"""glance-admin: small companion service for the Glance dashboard (stdlib only).

Phase 2 features
  * server-side notes          GET/PUT  /api/notes
  * server-side to-do          GET/POST /api/todos, PATCH/DELETE /api/todos/<id>
  * cross-tab find index       GET /api/find?q=..., POST /api/find/reindex, GET /api/find/status
Later phases add bookmarks, video channels and search engines.
State lives in STATE_DIR as plain JSON files (written atomically).
"""
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATE_DIR = os.environ.get("STATE_DIR", "/state")
GLANCE_URL = os.environ.get("GLANCE_URL", "http://host.docker.internal:3002").rstrip("/")
PAGES = [p.split(":", 1) for p in os.environ.get(
    "PAGES",
    "home:Home,downloads:Downloads,audio:Audio,video:Video,infra:Infra,networking:Networking,"
    "tools:Tools,dev:Dev,shopping:Shopping,cameras:Cameras,news:News Feeds,video-news:Video News Feed,bookmarks:Bookmarks").split(",")]
WARM_SECONDS = int(os.environ.get("WARM_SECONDS", "15"))     # 0 turns the page warmer off
REINDEX_SECONDS = int(os.environ.get("REINDEX_SECONDS", "300"))
LIDARR_URL = os.environ.get("LIDARR_URL", "http://host.docker.internal:8686").rstrip("/")
LIDARR_KEY = os.environ.get("LIDARR_KEY", "")
LIDARR_CAL_DAYS = int(os.environ.get("LIDARR_CAL_DAYS", "30"))
LIDARR_REFRESH_SECONDS = int(os.environ.get("LIDARR_REFRESH_SECONDS", "300"))
NAVIDROME_URL = os.environ.get("NAVIDROME_URL", "http://host.docker.internal:4534").rstrip("/")
NAVIDROME_USER = os.environ.get("NAVIDROME_USER", "")
NAVIDROME_TOKEN = os.environ.get("NAVIDROME_TOKEN", "")
NAVIDROME_SALT = os.environ.get("NAVIDROME_SALT", "")
ABS_URL = os.environ.get("ABS_URL", "http://host.docker.internal:13378").rstrip("/")
ABS_KEY = os.environ.get("ABS_KEY", "")
ABS_RESTRICTED = [n.strip() for n in os.environ.get("ABS_RESTRICTED", "Private").split(",") if n.strip()]
ABS_REFRESH_SECONDS = int(os.environ.get("ABS_REFRESH_SECONDS", "90"))
PRIVB_URL = os.environ.get("PRIVB_URL", "http://192.168.1.106:9999").rstrip("/")
PRIVB_KEY = os.environ.get("PRIVB_KEY", "")
IMMICH_URL = os.environ.get("IMMICH_URL", "").rstrip("/")
IMMICH_KEY = os.environ.get("IMMICH_KEY", "")
PRIVATE_REFRESH_SECONDS = int(os.environ.get("PRIVATE_REFRESH_SECONDS", "120"))
COVER_DIR = os.path.join(STATE_DIR, "covers")
MAX_COVER_BYTES = 4 * 1024 * 1024
MAX_BODY = 256 * 1024
MAX_NOTE = 100_000
MAX_TODO_TEXT = 500
MAX_TODOS = 500

_lock = threading.Lock()


# --------------------------------------------------------------------------- storage
def _path(name):
    return os.path.join(STATE_DIR, name)


def _read(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(name, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = _path(name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(name))


# --------------------------------------------------------------------------- find index
VOID = {"br", "img", "input", "hr", "meta", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
CAP_CLASSES = {"wb-card", "wb-tile", "monitor-site", "docker-container"}
SKIP_TAGS = {"script", "style", "textarea", "svg", "select", "option"}


class _PageParser(HTMLParser):
    """Extracts widget titles and item texts (li / tr / card / monitor / container / standalone links)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.widget = ""
        self.stack = []          # [tag, classes, is_cap, is_skip, is_title]
        self.skip = 0
        self.cap = None          # {"buf": [], "href": ""}
        self.title_buf = None

    @staticmethod
    def _classes(attrs):
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        classes = self._classes(attrs)
        d = dict(attrs)
        skip = tag in SKIP_TAGS or "data-wb-noindex" in d or "wb-restricted" in classes
        if skip:
            self.skip += 1
        if "widget" in classes and not self.skip:
            self.widget = ""
        is_title = tag == "h2" and any(e[1] & {"widget-header"} for e in self.stack) and not self.skip
        if is_title:
            self.title_buf = []
        is_cap = False
        in_header = any(e[1] & {"widget-header"} for e in self.stack)
        if in_header and self.cap is None:
            pass  # header links are covered by the widget-title item
        elif not self.skip and self.cap is None:
            if tag in ("li", "tr", "a") or classes & CAP_CLASSES:
                is_cap = True
                self.cap = {"buf": [], "href": d.get("href", "") if tag == "a" else ""}
        elif self.cap is not None and tag == "a" and not self.cap["href"]:
            self.cap["href"] = d.get("href", "")
        self.stack.append([tag, classes, is_cap, skip, is_title])

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for e in self.stack[i:][::-1]:
                    self._close(e)
                del self.stack[i:]
                return

    def _close(self, e):
        tag, classes, is_cap, skip, is_title = e
        if is_title and self.title_buf is not None:
            title = " ".join("".join(self.title_buf).split())
            self.title_buf = None
            if title:
                self.widget = title
                self.items.append({"widget": title, "text": title, "href": "", "kind": "widget"})
        if is_cap and self.cap is not None:
            text = " ".join("".join(self.cap["buf"]).split())
            if text:
                self.items.append({"widget": self.widget, "text": text[:240], "href": self.cap["href"], "kind": "item"})
            self.cap = None
        if skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            return
        if self.title_buf is not None:
            self.title_buf.append(data)
        if self.cap is not None:
            self.cap["buf"].append(data)


_index = {"items": [], "built": 0, "pages": {}}


def build_index():
    items, status = [], {}
    for order, (slug, name) in enumerate(PAGES):
        try:
            with urllib.request.urlopen("%s/api/pages/%s/content/" % (GLANCE_URL, slug), timeout=90) as r:
                html = r.read().decode("utf-8", "ignore")
            p = _PageParser()
            p.feed(html)
            seen = set()
            n = 0
            for it in p.items:
                key = (it["widget"], it["text"])
                if key in seen:
                    continue
                seen.add(key)
                it.update(page=slug, pageName=name, order=order)
                items.append(it)
                n += 1
            status[slug] = n
        except Exception as exc:  # keep the previous index for this page if the fetch fails
            status[slug] = "error: %s" % exc
            items.extend(i for i in _index["items"] if i.get("page") == slug)
    _index.update(items=items, built=int(time.time()), pages=status)


def _indexer():
    time.sleep(5)
    while True:
        try:
            build_index()
        except Exception as exc:
            print("index error:", exc, flush=True)
        time.sleep(REINDEX_SECONDS)


def find(q):
    q = q.strip().lower()
    if len(q) < 2:
        return []
    out = []
    for it in _index["items"]:
        if q in it["text"].lower():
            out.append({k: it[k] for k in ("page", "pageName", "widget", "text", "href", "kind")})
            if len(out) >= 300:
                break
    return out


# --------------------------------------------------------------------------- lidarr calendar cache
# Lidarr's calendar takes ~7 s when its own cache is cold, longer than Glance's 5 s request timeout, so
# Glance asks us instead: we refresh in the background with a long timeout and answer instantly.
_lcal = {"data": None, "at": 0, "err": ""}


def refresh_lidarr():
    import datetime
    today = datetime.date.today()
    url = "%s/api/v1/calendar?start=%s&end=%s&includeArtist=true" % (
        LIDARR_URL, today.isoformat(), (today + datetime.timedelta(days=LIDARR_CAL_DAYS)).isoformat())
    req = urllib.request.Request(url, headers={"X-Api-Key": LIDARR_KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    _lcal.update(data=data, at=int(time.time()), err="")
    _persist("lidarr", {"at": _lcal["at"], "data": data})


def _lidarr_loop():
    time.sleep(3)
    while True:
        try:
            refresh_lidarr()
            wait = LIDARR_REFRESH_SECONDS
        except Exception as exc:
            _lcal["err"] = str(exc)
            wait = 60
        time.sleep(wait)


# --------------------------------------------------------------------------- audio: covers + audiobookshelf
# Covers are proxied (and cached on disk) so no Navidrome token or Audiobookshelf key ever reaches the browser.
_ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _cover_upstream(kind, cid, size):
    if kind == "nd":
        from urllib.parse import urlencode
        q = urlencode({"id": cid, "size": size, "u": NAVIDROME_USER, "t": NAVIDROME_TOKEN, "s": NAVIDROME_SALT,
                       "v": "1.16.1", "c": "glance"})
        return urllib.request.Request("%s/rest/getCoverArt.view?%s" % (NAVIDROME_URL, q))
    if kind == "privb":
        return urllib.request.Request("%s/scene/%s/screenshot" % (PRIVB_URL, cid), headers={"ApiKey": PRIVB_KEY})
    if kind == "immich":
        return urllib.request.Request("%s/api/assets/%s/thumbnail?size=thumbnail" % (IMMICH_URL, cid),
                                      headers={"x-api-key": IMMICH_KEY})
    return urllib.request.Request("%s/api/items/%s/cover?width=%d&format=webp" % (ABS_URL, cid, size),
                                  headers={"Authorization": "Bearer " + ABS_KEY})


def get_cover(kind, cid, size):
    """Returns (bytes, content-type) or None."""
    if not _ID_OK.match(cid):
        return None
    size = max(60, min(size, 600))
    base = os.path.join(COVER_DIR, kind, "%s_%d" % (cid, size))
    cacheable = kind in ("nd", "abs")      # private content (privb / immich) is never written to disk
    if cacheable:
        try:
            with open(base + ".img", "rb") as f, open(base + ".ct") as c:
                return f.read(), c.read().strip()
        except OSError:
            pass
    try:
        with urllib.request.urlopen(_cover_upstream(kind, cid, size), timeout=20) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read(MAX_COVER_BYTES + 1)
    except Exception:
        return None
    if not ctype.startswith("image/") or not data or len(data) > MAX_COVER_BYTES:
        return None
    if not cacheable:
        return data, ctype
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + ".img.tmp", "wb") as f:
        f.write(data)
    os.replace(base + ".img.tmp", base + ".img")
    with open(base + ".ct", "w") as f:
        f.write(ctype)
    return data, ctype


_abs = {"at": 0, "continue": [], "recent": [], "stats": {}, "libs": [], "err": ""}


def refresh_abs():
    hdr = {"Authorization": "Bearer " + ABS_KEY}

    def get(path):
        with urllib.request.urlopen(urllib.request.Request(ABS_URL + path, headers=hdr), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    libs = get("/api/libraries")["libraries"]
    restricted_ids = {l["id"] for l in libs if l["name"] in ABS_RESTRICTED}
    prog = {}
    for m in get("/api/me").get("mediaProgress", []):
        prog[(m.get("libraryItemId"), m.get("episodeId"))] = m
    cont = []
    for x in get("/api/me/items-in-progress").get("libraryItems", []):
        md = x["media"]["metadata"]
        ep = x.get("recentEpisode") or {}
        p = prog.get((x["id"], ep.get("id"))) or prog.get((x["id"], None)) or {}
        cont.append({"id": x["id"], "title": md.get("title") or "", "author": md.get("authorName") or md.get("author") or "",
                     "sub": ep.get("title") or "", "type": x.get("mediaType"),
                     "progress": int(round(float(p.get("progress") or 0) * 100)),
                     "updated": x.get("progressLastUpdate") or 0, "restricted": x.get("libraryId") in restricted_ids})
    cont.sort(key=lambda i: i["updated"], reverse=True)
    recent, stats, shelves = [], {"books": 0, "podcasts": 0, "restricted": 0}, []
    for l in libs:
        r = get("/api/libraries/%s/items?sort=addedAt&desc=1&limit=400&minified=1" % l["id"])
        is_r = l["id"] in restricted_ids
        total = int(r.get("total") or 0)
        if is_r:
            stats["restricted"] += total
        elif l.get("mediaType") == "podcast":
            stats["podcasts"] += total
        else:
            stats["books"] += total
        items = []
        for x in r.get("results", []):
            md = x["media"]["metadata"]
            items.append({"id": x["id"], "title": md.get("title") or "", "author": md.get("authorName") or md.get("author") or "",
                          "type": x.get("mediaType"), "library": l["name"], "added": x.get("addedAt") or 0, "restricted": is_r})
        recent.extend(items[:16])
        shelves.append({"id": l["id"], "name": l["name"], "type": l.get("mediaType"), "total": total, "restricted": is_r, "items": items})
    recent.sort(key=lambda i: i["added"], reverse=True)
    _abs.update(at=int(time.time()), **{"continue": cont, "recent": recent, "stats": stats, "libs": shelves, "err": ""})
    _persist("abs", {"at": _abs["at"], "continue": [i for i in cont if not i["restricted"]],
                     "recent": [i for i in recent if not i["restricted"]], "stats": {**stats, "restricted": 0},
                     "libs": [s for s in shelves if not s["restricted"]]})


_tailscale = {"at": 0, "data": None, "err": ""}
_npmst = {"at": 0, "data": None, "err": ""}

# Last good summaries are kept on disk so a restart answers immediately instead of serving 503s (Glance would cache the
# error for a couple of minutes). Private data (Private B, Immich) is never persisted; restricted audiobooks are stripped.
CACHE_DIR = os.path.join(STATE_DIR, "cache")


def _persist(name, obj):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = os.path.join(CACHE_DIR, name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, os.path.join(CACHE_DIR, name + ".json"))
    except OSError:
        pass


def _restore(name):
    try:
        with open(os.path.join(CACHE_DIR, name + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _net_loop(name, state, seconds):
    import net
    fn = getattr(net, name)
    time.sleep(10)
    while True:
        try:
            state.update(data=fn(), at=int(time.time()), err="")
            _persist(name, {"at": state["at"], "data": state["data"]})
            wait = seconds
        except Exception as exc:
            state["err"] = str(exc)[:200]
            wait = 60
        time.sleep(wait)


CFG_DATA_DIR = os.environ.get("CFG_DATA_DIR", "/cfgdata")
SEED_CHANNELS = [{"id": "UCu3IhMzYtC93HTzuIua090A", "name": "Oloff"}, {"id": "UC4eYXhJI4-7wSWc8UNRwD4A", "name": "NPR Music"}]


def channels_load():
    d = _read("channels.json", None)
    if d is None:
        d = {"channels": SEED_CHANNELS}
        _write("channels.json", d)
    return d["channels"]


def channels_publish(chs):
    """Write the Video News page file for Glance, only when its content changed (an unchanged rewrite would reload Glance)."""
    import channels as ch
    text = ch.render_yaml(chs)
    path = os.path.join(CFG_DATA_DIR, "video-news.yml")
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(CFG_DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def news_load():
    import news as nw
    d = _read("news.json", None)
    if d is None:
        d = json.loads(json.dumps(nw.SEED))
        _write("news.json", d)
    return d


def news_publish(state):
    """Write the News Feeds page file for Glance, only when its content changed."""
    import news as nw
    text = nw.render_yaml(state)
    path = os.path.join(CFG_DATA_DIR, "news.yml")
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(CFG_DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def bookmarks_load():
    return _read("bookmarks.json", None)


def bookmarks_save_publish(data):
    """Save the JSON and write the Bookmarks page file for Glance (only if its content changed)."""
    import bookmarks as bm
    _write("bookmarks.json", data)
    text = bm.render_yaml(data)
    path = os.path.join(CFG_DATA_DIR, "bookmarks.yml")
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


_camst = {"at": 0, "data": None, "err": ""}


def _cam_loop():
    import cameras
    time.sleep(9)
    while True:
        try:
            _camst.update(data=cameras.build(), at=int(time.time()), err="")
            _persist("cameras", {"at": _camst["at"], "data": _camst["data"]})
            wait = int(os.environ.get("CAMERAS_REFRESH_SECONDS", "20"))
        except Exception as exc:
            _camst["err"] = str(exc)[:200]
            wait = 30
        time.sleep(wait)


_shopst = {"at": 0, "data": None, "err": ""}


def shop_state():
    import shop
    st = _read("shopping.json", None)
    if st is None:
        st = shop.default_state()
        _write("shopping.json", st)
    return shop.normalise(st)


def shop_summary_build():
    """Everything slow or external (deals, stock, eBay, Discogs, watches); each part has its own cache lifetime inside shop.py."""
    import hashlib
    import shop
    st = shop_state()
    key = hashlib.md5(json.dumps(st["ebay"], sort_keys=True).encode()).hexdigest()[:8]
    return {"at": int(time.time()), "deals_raw": shop.merge_deals(shop.cached("deals:hukd", 900, lambda: shop.deals("hukd")), shop.cached("deals:reddit", 2400, lambda: shop.deals("reddit"))), "stock": shop.cached("stock", 900, shop.stock),
            "ebay": shop.cached("ebay:" + key, 900, lambda: shop.ebay_results(st["ebay"])), "discogs": shop.cached("discogs", 3600, shop.discogs),
            "watches": shop.cached("watches", 120, shop.watches)}


def shop_loop():
    time.sleep(14)
    while True:
        try:
            _shopst.update(data=shop_summary_build(), at=int(time.time()), err="")
            _persist("shopping", {"at": _shopst["at"], "data": _shopst["data"]})
            wait = 90
        except Exception as exc:
            _shopst["err"] = str(exc)[:200]
            wait = 120
        time.sleep(wait)


def shop_kick():
    """Rebuilds the cached Shopping data in the background right after you change something that affects it."""
    def run():
        try:
            _shopst.update(data=shop_summary_build(), at=int(time.time()), err="")
        except Exception as exc:
            _shopst["err"] = str(exc)[:200]
    threading.Thread(target=run, daemon=True).start()


def shop_summary():
    """The cached build plus the parts that depend on state you can edit (alert terms, watch targets), applied fresh."""
    import shop
    st = shop_state()
    d = dict(_shopst["data"])
    d["deals"] = shop.deals_for(st["terms"], d.pop("deals_raw", {}))
    d["watches"] = shop.apply_targets(d.get("watches"), {w["watch"]: w["target"] for w in st["wishlist"] if w.get("watch")})
    d["ebay_configured"] = shop.ebay_configured()
    d["counts"] = {"list_open": sum(1 for i in st["list"] if not i["done"]), "wishlist": sum(1 for w in st["wishlist"] if not w.get("gift")), "gifts": sum(1 for w in st["wishlist"] if w.get("gift")),
                   "watches": len((d["watches"] or {}).get("items", [])), "at_target": sum(1 for w in (d["watches"] or {}).get("items", []) if w.get("at_target"))}
    return d


_devst = {"at": 0, "data": None, "err": ""}


def _dev_loop():
    import dev
    time.sleep(12)
    while True:
        try:
            _devst.update(data=dev.build(), at=int(time.time()), err="")
            _persist("dev", {"at": _devst["at"], "data": dev.public_part(_devst["data"])})      # private repos/events never touch the disk
            wait = int(os.environ.get("DEV_REFRESH_SECONDS", "300" if os.environ.get("GITHUB_TOKEN") else "1800"))
        except Exception as exc:
            _devst["err"] = str(exc)[:200]
            wait = 120
        time.sleep(wait)


_relst = {"at": 0, "data": None, "err": ""}


def _rel_loop():
    import releases
    time.sleep(15)
    while True:
        try:
            d = releases.build()
            if d["ok"] or _relst["data"] is None:          # never replace good data with an all-failed run
                _relst.update(data=d, at=int(time.time()), err="")
                _persist("releases", {"at": _relst["at"], "data": d})
            wait = int(os.environ.get("RELEASES_REFRESH_SECONDS", "10800"))
        except Exception as exc:
            _relst["err"] = str(exc)[:200]
            wait = 600
        time.sleep(wait)


_toolsst = {"at": 0, "data": None, "err": ""}


def _tools_loop():
    import tools
    time.sleep(12)
    while True:
        try:
            _toolsst.update(data=tools.build(), at=int(time.time()), err="")
            _persist("tools", {"at": _toolsst["at"], "data": _toolsst["data"]})
        except Exception as exc:
            _toolsst["err"] = str(exc)[:200]
        time.sleep(int(os.environ.get("TOOLS_REFRESH_SECONDS", "90")))


_infra = {"at": 0, "data": None, "err": ""}


def _infra_loop():
    import infra
    time.sleep(8)
    while True:
        try:
            _infra.update(data=infra.build(), at=int(time.time()), err="")
            _persist("infra", {"at": _infra["at"], "data": _infra["data"]})
        except Exception as exc:
            _infra["err"] = str(exc)
        time.sleep(int(os.environ.get("INFRA_REFRESH_SECONDS", "60")))


def _http_json(url, headers=None, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------- private rows: privb + immich summaries
_privb = {"at": 0, "data": None, "err": ""}
_immich = {"at": 0, "data": None, "err": ""}


def refresh_privb():
    q = ('{ version { version } stats { scene_count image_count performer_count studio_count tag_count scenes_size scenes_duration images_size } '
         'findScenes(filter:{per_page:14, sort:"created_at", direction:DESC}){ scenes{ id title date created_at studio{name} '
         'performers{name} files{path duration} } } }')
    d = _http_json(PRIVB_URL + "/graphql", {"ApiKey": PRIVB_KEY}, {"query": q})["data"]
    s = d["stats"]
    recent = []
    for sc in d["findScenes"]["scenes"]:
        f = (sc.get("files") or [{}])[0]
        name = sc.get("title") or os.path.splitext(os.path.basename(f.get("path") or ""))[0] or "Scene %s" % sc["id"]
        recent.append({"id": sc["id"], "title": name[:120], "studio": (sc.get("studio") or {}).get("name") or "",
                       "performers": ", ".join(p["name"] for p in (sc.get("performers") or [])[:2]),
                       "minutes": int(round(float(f.get("duration") or 0) / 60)), "added": sc.get("created_at") or ""})
    _privb.update(at=int(time.time()), err="", data={
        "version": d["version"]["version"],
        "stats": {"scenes": s["scene_count"], "images": s["image_count"], "performers": s["performer_count"],
                  "studios": s["studio_count"], "tags": s["tag_count"],
                  "size_tb": round(float(s["scenes_size"]) / 1e12, 2), "hours": int(float(s["scenes_duration"]) / 3600),
                  "images_gb": round(float(s["images_size"]) / 1e9, 1)},
        "recent": recent})


def refresh_immich():
    h = {"x-api-key": IMMICH_KEY}
    about = _http_json(IMMICH_URL + "/api/server/about", h)
    st = _http_json(IMMICH_URL + "/api/server/statistics", h)
    disk = _http_json(IMMICH_URL + "/api/server/storage", h)
    jobs = {"active": 0, "waiting": 0, "failed": 0}
    for v in _http_json(IMMICH_URL + "/api/jobs", h).values():
        for k in jobs:
            jobs[k] += int((v.get("jobCounts") or {}).get(k, 0))
    items = _http_json(IMMICH_URL + "/api/search/metadata", h, {"size": 14, "order": "desc"})["assets"]["items"]
    recent = [{"id": i["id"], "type": i.get("type"), "taken": i.get("fileCreatedAt") or "", "video": i.get("type") == "VIDEO"} for i in items]
    _immich.update(at=int(time.time()), err="", data={
        "version": about.get("version"), "photos": st.get("photos"), "videos": st.get("videos"),
        "disk": {"used": disk.get("diskUse"), "size": disk.get("diskSize"), "percent": round(float(disk.get("diskUsagePercentage") or 0))},
        "jobs": jobs, "recent": recent})


def _private_loop(fn, state):
    time.sleep(6)
    while True:
        try:
            fn()
            wait = PRIVATE_REFRESH_SECONDS
        except Exception as exc:
            state["err"] = str(exc)
            wait = 60
        time.sleep(wait)


def _warm_loop():
    """Keeps Glance's widget caches fresh. Glance refetches an expired widget while the page request waits (1-4 s); requesting every
    page now and then makes that happen here, in the background, so a real visit is answered from cache."""
    time.sleep(20)
    while True:
        for slug, _ in PAGES:
            try:
                with urllib.request.urlopen("%s/api/pages/%s/content/" % (GLANCE_URL, slug), timeout=60) as r:
                    r.read()
            except Exception:
                pass
        time.sleep(WARM_SECONDS)


def _abs_loop():
    time.sleep(4)
    while True:
        try:
            refresh_abs()
            wait = ABS_REFRESH_SECONDS
        except Exception as exc:
            _abs["err"] = str(exc)
            wait = 60
        time.sleep(wait)


# --------------------------------------------------------------------------- http
class H(BaseHTTPRequestHandler):
    server_version = "glance-admin/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj=None):
        body = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-WB-VPN")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_bytes(self, data, ctype, private=False):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600" if private else "public, max-age=604800")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("body too large")
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_OPTIONS(self):
        self._send(204)

    def _route(self, method):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        if path == "/health":
            return self._send(200, {"ok": True, "indexed": len(_index["items"]), "built": _index["built"],
                                    "lidarr_calendar_cached": _lcal["data"] is not None, "lidarr_calendar_age": int(time.time()) - _lcal["at"] if _lcal["at"] else None})

        if path == "/api/notes":
            with _lock:
                if method == "GET":
                    return self._send(200, _read("notes.json", {"text": "", "updated": 0}))
                if method == "PUT":
                    text = str(self._body().get("text", ""))[:MAX_NOTE]
                    data = {"text": text, "updated": int(time.time())}
                    _write("notes.json", data)
                    return self._send(200, data)

        if path == "/api/todos":
            with _lock:
                data = _read("todos.json", {"items": []})
                if method == "GET":
                    return self._send(200, data)
                if method == "POST":
                    text = str(self._body().get("text", "")).strip()[:MAX_TODO_TEXT]
                    if not text:
                        return self._send(400, {"error": "empty"})
                    if len(data["items"]) >= MAX_TODOS:
                        return self._send(400, {"error": "too many items"})
                    item = {"id": uuid.uuid4().hex[:10], "text": text, "done": False, "created": int(time.time())}
                    data["items"].insert(0, item)
                    _write("todos.json", data)
                    return self._send(201, item)

        m = re.fullmatch(r"/api/todos/([0-9a-f]{10})", path)
        if m:
            with _lock:
                data = _read("todos.json", {"items": []})
                idx = next((i for i, t in enumerate(data["items"]) if t["id"] == m.group(1)), -1)
                if idx < 0:
                    return self._send(404, {"error": "not found"})
                if method == "PATCH":
                    b = self._body()
                    if "done" in b:
                        data["items"][idx]["done"] = bool(b["done"])
                    if "text" in b and str(b["text"]).strip():
                        data["items"][idx]["text"] = str(b["text"]).strip()[:MAX_TODO_TEXT]
                    _write("todos.json", data)
                    return self._send(200, data["items"][idx])
                if method == "DELETE":
                    del data["items"][idx]
                    _write("todos.json", data)
                    return self._send(200, {"ok": True})

        m = re.fullmatch(r"/api/(nd|abs|privb|immich)/cover/([A-Za-z0-9_-]{1,80})", path)
        if m and method == "GET":
            have = {"nd": NAVIDROME_TOKEN, "abs": ABS_KEY, "privb": PRIVB_KEY, "immich": IMMICH_KEY and IMMICH_URL}
            if not have[m.group(1)]:
                return self._send(503, {"error": "not configured"})
            try:
                size = int((parse_qs(u.query).get("s") or ["300"])[0])
            except ValueError:
                size = 300
            got = get_cover(m.group(1), m.group(2), size)
            if not got:
                return self._send(404, {"error": "no cover"})
            return self._send_bytes(got[0], got[1], private=m.group(1) in ("privb", "immich"))

        if path in ("/api/tailscale/summary", "/api/npm/summary") and method == "GET":
            st = _tailscale if "tailscale" in path else _npmst
            if st["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": st["err"]})
            return self._send(200, st["data"])

        if path in ("/api/vpn/summary", "/api/vpn/command"):
            import vpn
            if not vpn.configured():
                return self._send(503, {"error": "VPN panel not configured (VPN_URL / VPN_KEY)"})
            try:
                if path == "/api/vpn/summary" and method == "GET":
                    return self._send(200, vpn.summary())
                if path == "/api/vpn/command" and method == "POST":
                    # Writes change network routing: browsers must come from this host and send the custom header (forces a CORS preflight)
                    if not vpn.origin_ok(self.headers.get("Origin"), self.headers.get("Host")) or self.headers.get("X-WB-VPN") != "1":
                        return self._send(403, {"error": "forbidden"})
                    return self._send(202, vpn.command(self._body()))
            except (urllib.error.URLError, OSError):
                return self._send(502, {"error": "VPN panel unreachable"})

        if path == "/api/remote/hosts" and method == "GET":
            import remote
            if not remote.configured():
                return self._send(503, {"error": "Termix not configured (TERMIX_URL / TERMIX_API_KEY)"})
            try:
                return self._send(200, remote.hosts())
            except ValueError as e:
                return self._send(502, {"error": str(e)})
            except (urllib.error.URLError, OSError):
                return self._send(502, {"error": "Termix unreachable"})

        if path == "/api/channels":
            if method == "GET":
                with _lock:
                    return self._send(200, {"channels": channels_load()})
            if method == "POST":
                import channels as ch
                try:
                    found = ch.resolve(str(self._body().get("input", "")))      # network call: done outside the lock
                except ValueError:
                    raise
                except Exception:
                    return self._send(502, {"error": "could not reach YouTube just now, try again"})
                with _lock:
                    chs = channels_load()
                    if any(c["id"] == found["id"] for c in chs):
                        return self._send(409, {"error": "%s is already on the page" % found["name"], "channel": found})
                    if len(chs) >= 40:
                        return self._send(400, {"error": "too many channels (limit 40)"})
                    chs.append(found)
                    _write("channels.json", {"channels": chs})
                    channels_publish(chs)
                return self._send(201, {"channel": found, "channels": chs})

        m = re.fullmatch(r"/api/channels/(UC[0-9A-Za-z_-]{22})", path)
        if m and method == "DELETE":
            with _lock:
                chs = channels_load()
                keep = [c for c in chs if c["id"] != m.group(1)]
                if len(keep) == len(chs):
                    return self._send(404, {"error": "not found"})
                _write("channels.json", {"channels": keep})
                channels_publish(keep)
            return self._send(200, {"ok": True, "channels": keep})

        if path.startswith("/api/news"):
            import news as nw
            if path == "/api/news" and method == "GET":
                with _lock:
                    return self._send(200, nw.public(news_load()))
            if path == "/api/news/add" and method == "POST":
                b = self._body()
                with _lock:
                    st = news_load()
                    import copy
                    work = copy.deepcopy(st)
                try:
                    g, label = nw.add(work, str(b.get("input", "")), str(b.get("group", "")), str(b.get("new_title", "")))     # network calls: outside the lock
                except ValueError as exc:
                    return self._send(400, {"error": str(exc)})
                with _lock:
                    cur = news_load()
                    if cur != st:
                        return self._send(409, {"error": "the feed list changed while this was being checked, try again"})
                    _write("news.json", work)
                    news_publish(work)
                return self._send(201, {"added": label, "group": g["title"], **nw.public(work)})
            if path == "/api/news/remove" and method == "POST":
                b = self._body()
                with _lock:
                    st = news_load()
                    try:
                        gone = nw.remove(st, str(b.get("group", "")), str(b.get("key", "")))
                    except KeyError:
                        return self._send(404, {"error": "unknown group"})
                    if not gone:
                        return self._send(404, {"error": "not found"})
                    _write("news.json", st)
                    news_publish(st)
                    return self._send(200, {"ok": True, **nw.public(st)})

        if path.startswith("/api/bookmarks"):
            import bookmarks as bm
            if path == "/api/bookmarks" and method == "GET":
                with _lock:
                    d = bookmarks_load()
                return self._send(200, d) if d else self._send(404, {"error": "no bookmarks data yet"})
            if path == "/api/bookmarks/link" and method == "POST":
                b = self._body()
                try:
                    new = bm.prepare_link(str(b.get("url", "")), str(b.get("title", "")))   # network: outside the lock
                except ValueError:
                    raise
                except Exception:
                    return self._send(502, {"error": "could not reach that address; the link was not added"})
                with _lock:
                    d = bookmarks_load()
                    try:
                        _, g = bm.find_group(d, str(b.get("group_id", "")))
                    except KeyError:
                        return self._send(404, {"error": "unknown group"})
                    if any(l["url"].rstrip("/") == new["url"].rstrip("/") for l in g["links"]):
                        return self._send(409, {"error": "that link is already in %s" % g["title"]})
                    if bm.count_links(d) >= bm.MAX_LINKS:
                        return self._send(400, {"error": "too many bookmarks"})
                    g["links"].append(new)
                    bookmarks_save_publish(d)
                return self._send(201, {"link": new, "group": g["title"]})
            m = re.fullmatch(r"/api/bookmarks/link/(l[0-9a-f]{10})", path)
            if m and method in ("PATCH", "DELETE"):
                with _lock:
                    d = bookmarks_load()
                    try:
                        g, i, l = bm.find_link(d, m.group(1))
                    except KeyError:
                        return self._send(404, {"error": "not found"})
                    if method == "DELETE":
                        del g["links"][i]
                    else:
                        b = self._body()
                        if "title" in b:
                            l["title"] = bm.clean_title(b["title"])
                        if "url" in b:
                            l["url"] = bm.clean_url(b["url"])
                        if "group_id" in b and b["group_id"] != g["id"]:
                            try:
                                _, dest = bm.find_group(d, str(b["group_id"]))
                            except KeyError:
                                return self._send(404, {"error": "unknown group"})
                            del g["links"][i]
                            dest["links"].append(l)
                    bookmarks_save_publish(d)
                return self._send(200, {"ok": True})
            if path == "/api/bookmarks/group" and method == "POST":
                b = self._body()
                with _lock:
                    d = bookmarks_load()
                    g = bm.add_group(d, str(b.get("title", "")), b.get("column", 1), b.get("color"), bool(b.get("private")))
                    bookmarks_save_publish(d)
                return self._send(201, {"group": {"id": g["id"], "title": g["title"]}})
            m = re.fullmatch(r"/api/bookmarks/group/(g[0-9a-f]{10})", path)
            if m and method == "DELETE":
                with _lock:
                    d = bookmarks_load()
                    try:
                        ci, g = bm.find_group(d, m.group(1))
                    except KeyError:
                        return self._send(404, {"error": "not found"})
                    if g["links"]:
                        return self._send(400, {"error": "move or remove its %d links first" % len(g["links"])})
                    d["columns"][ci]["groups"].remove(g)
                    bookmarks_save_publish(d)
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})

        if path == "/api/cameras/events" and method == "GET":
            import cameras as cam
            q = parse_qs(u.query)
            try:
                res = cam.events((q.get("label") or [""])[0], (q.get("camera") or [""])[0], (q.get("after") or ["0"])[0],
                                 (q.get("before") or ["0"])[0], (q.get("limit") or ["60"])[0], (q.get("q") or [""])[0], (q.get("mode") or ["description"])[0])
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception:
                return self._send(502, {"error": "Frigate did not answer"})
            return self._send(200, res)

        if path.startswith("/api/shopping"):
            import shop
            sub = path[len("/api/shopping"):].strip("/").split("/")
            try:
                if sub == ["summary"] and method == "GET":
                    if _shopst["data"] is None:
                        return self._send(503, {"error": "not cached yet", "detail": _shopst["err"]})
                    return self._send(200, shop_summary())
                if sub == ["state"] and method == "GET":
                    with _lock:
                        return self._send(200, shop_state())
                b = self._body() if method in ("POST", "PATCH") else {}
                with _lock:
                    st = shop_state()
                    res = None
                    k = sub[0] if sub else ""
                    iid = sub[1] if len(sub) > 1 else ""
                    if k == "list":
                        if method == "POST" and not iid:
                            res = shop.list_add(st, b.get("text"), b.get("qty"), b.get("store"), b.get("cat"))
                        elif method == "POST" and iid == "clear":
                            res = {"cleared": shop.list_clear_done(st)}
                        elif method == "PATCH":
                            res = shop.list_patch(st, iid, b)
                        elif method == "DELETE":
                            res = shop.remove(st, "list", iid)
                        else:
                            return self._send(405, {"error": "bad request"})
                    elif k == "wish":
                        if method == "POST" and not iid:
                            res = shop.wish_add(st, b.get("title"), b.get("url"), b.get("target"), b.get("priority", 2), b.get("cat"), b.get("notes"), b.get("gift"))
                        elif method == "PATCH":
                            res = shop.wish_patch(st, iid, b)
                        elif method == "DELETE":
                            res = shop.remove(st, "wishlist", iid)
                        elif method == "POST" and len(sub) == 3 and sub[2] == "bought":
                            res = shop.wish_bought(st, iid, b.get("price"), b.get("store"), b.get("date"))
                        elif method == "POST" and len(sub) == 3 and sub[2] == "watch":
                            _, w = shop._find(st, "wishlist", iid)
                            if not w["url"]:
                                raise ValueError("add a link to this wish first")
                            w["watch"] = shop.watch_add(w["url"], w["title"], bool(b.get("browser")))
                            shop._cache.pop("watches", None)
                            shop_kick()
                            res = w
                        else:
                            return self._send(405, {"error": "bad request"})
                    elif k == "purchase":
                        if method == "POST":
                            res = shop.purchase_add(st, b.get("title"), b.get("price"), b.get("store"), b.get("cat"), b.get("date"))
                        elif method == "DELETE":
                            res = shop.remove(st, "purchases", iid)
                        else:
                            return self._send(405, {"error": "bad request"})
                    elif k == "terms":
                        if method == "POST":
                            res = {"term": shop.term_add(st, b.get("term"))}
                        elif method == "DELETE":
                            shop.term_remove(st, urllib.parse.unquote(iid))
                            res = {"ok": True}
                        else:
                            return self._send(405, {"error": "bad request"})
                    elif k == "ebay":
                        if method == "POST":
                            res = shop.ebay_add(st, b.get("q"), b.get("max"), b.get("cond"), b.get("opts"))
                            shop_kick()
                        elif method == "DELETE":
                            res = shop.remove(st, "ebay", iid)
                        else:
                            return self._send(405, {"error": "bad request"})
                    elif k == "watch":
                        if method == "POST" and not iid:
                            uid = shop.watch_add(b.get("url"), b.get("title"), bool(b.get("browser")))
                            shop._cache.pop("watches", None)
                            shop_kick()
                            res = {"id": uid}
                        elif method == "POST" and len(sub) == 3 and sub[2] == "recheck":
                            shop.watch_recheck(iid)
                            shop._cache.pop("watches", None)
                            shop_kick()
                            res = {"ok": True}
                        elif method == "DELETE":
                            shop.watch_remove(iid)
                            for w in st["wishlist"]:
                                if w.get("watch") == iid:
                                    w["watch"] = ""
                            shop._cache.pop("watches", None)
                            shop_kick()
                            res = {"ok": True}
                        else:
                            return self._send(405, {"error": "bad request"})
                    else:
                        return self._send(404, {"error": "not found"})
                    _write("shopping.json", st)
                return self._send(201 if method == "POST" else 200, {"result": res})
            except KeyError:
                return self._send(404, {"error": "not found"})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except urllib.error.URLError:
                return self._send(502, {"error": "that service did not answer"})

        if path == "/api/dev/summary" and method == "GET":
            if _devst["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": _devst["err"]})
            return self._send(200, _devst["data"])

        if path == "/api/cameras/clip" and method == "GET":
            import cameras as cam
            try:
                data = cam.clip((parse_qs(u.query).get("id") or [""])[0])
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception:
                return self._send(404, {"error": "clip not available"})
            total, start, end, code = len(data), 0, len(data) - 1, 200
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else total - 1
                else:
                    start = max(total - int(m.group(2)), 0)
                end = min(end, total - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % total)
                    self.end_headers()
                    return
                code = 206
            body = data[start:end + 1]
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(body)))
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, total))
            self.send_header("Cache-Control", "private, max-age=600")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        if path == "/api/cameras/event" and method == "GET":
            import cameras as cam
            try:
                return self._send(200, cam.event((parse_qs(u.query).get("id") or [""])[0]))
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception:
                return self._send(404, {"error": "event not found"})

        if path == "/api/cameras/summary" and method == "GET":
            if _camst["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": _camst["err"]})
            return self._send(200, _camst["data"])

        if path == "/api/releases/summary" and method == "GET":
            if _relst["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": _relst["err"]})
            return self._send(200, _relst["data"])

        if path == "/api/tools/summary" and method == "GET":
            if _toolsst["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": _toolsst["err"]})
            return self._send(200, _toolsst["data"])

        if path == "/api/infra/summary" and method == "GET":
            if _infra["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": _infra["err"]})
            return self._send(200, _infra["data"])

        if path in ("/api/privb/summary", "/api/immich/summary") and method == "GET":
            st = _privb if "privb" in path else _immich
            if st["data"] is None:
                return self._send(503, {"error": "not cached yet", "detail": st["err"]})
            return self._send(200, st["data"])

        if path in ("/api/abs/continue", "/api/abs/recent") and method == "GET":
            q = parse_qs(u.query)
            group = (q.get("group") or ["open"])[0]
            if _abs["at"] == 0:
                return self._send(503, {"error": "not cached yet", "detail": _abs["err"]})
            want_restricted = group == "restricted"
            items = [i for i in _abs["continue" if path.endswith("continue") else "recent"] if i["restricted"] == want_restricted]
            try:
                limit = max(1, min(int((q.get("limit") or ["16"])[0]), 40))
            except ValueError:
                limit = 16
            return self._send(200, items[:limit])

        if path == "/api/abs/shelves" and method == "GET":
            # one random sample per library (Glance's own cache decides how often the sample changes)
            q = parse_qs(u.query)
            if _abs["at"] == 0:
                return self._send(503, {"error": "not cached yet", "detail": _abs["err"]})
            want_restricted = (q.get("group") or ["open"])[0] == "restricted"
            try:
                n = max(1, min(int((q.get("n") or ["14"])[0]), 40))
            except ValueError:
                n = 14
            out = []
            for s in _abs["libs"]:
                if s["restricted"] != want_restricted or not s["items"]:
                    continue
                out.append({"id": s["id"], "name": s["name"], "type": s["type"], "total": s["total"],
                            "items": random.sample(s["items"], min(n, len(s["items"])))})
            return self._send(200, out)

        if path == "/api/abs/stats" and method == "GET":
            if _abs["at"] == 0:
                return self._send(503, {"error": "not cached yet", "detail": _abs["err"]})
            return self._send(200, _abs["stats"])

        if path == "/api/lidarr/calendar" and method == "GET":
            if _lcal["data"] is None:
                return self._send(503, {"error": "calendar not cached yet", "detail": _lcal["err"]})
            return self._send(200, _lcal["data"])

        if path == "/api/find" and method == "GET":
            q = (parse_qs(u.query).get("q") or [""])[0]
            res = find(q)
            return self._send(200, {"q": q, "count": len(res), "results": res, "built": _index["built"]})
        if path == "/api/find/reindex" and method == "POST":
            threading.Thread(target=build_index, daemon=True).start()
            return self._send(202, {"ok": True})
        if path == "/api/find/status" and method == "GET":
            return self._send(200, {"items": len(_index["items"]), "built": _index["built"], "pages": _index["pages"]})

        self._send(404, {"error": "not found"})

    def _handle(self, method):
        try:
            self._route(method)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            print("error:", method, self.path, exc, flush=True)
            self._send(500, {"error": "internal error"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_PATCH(self):
        self._handle("PATCH")

    def do_DELETE(self):
        self._handle("DELETE")


if __name__ == "__main__":
    os.makedirs(STATE_DIR, exist_ok=True)
    for _name, _state in (("tailscale", _tailscale), ("npm", _npmst), ("infra", _infra), ("lidarr", _lcal), ("tools", _toolsst), ("releases", _relst), ("cameras", _camst), ("dev", _devst)):
        _c = _restore(_name)
        if _c and _c.get("data") is not None:
            _state.update(data=_c["data"], at=_c.get("at", 0))
    _c = _restore("shopping")
    if _c and _c.get("data"):
        _shopst.update(data=_c["data"], at=_c.get("at", 0))
    _c = _restore("abs")
    if _c:
        _abs.update(at=_c.get("at", 0), **{"continue": _c.get("continue", []), "recent": _c.get("recent", []), "stats": _c.get("stats", {}), "libs": _c.get("libs", [])})
    try:
        channels_publish(channels_load())          # make sure the page file exists and matches the saved list
        news_publish(news_load())
        _b = bookmarks_load()
        if _b:
            bookmarks_save_publish(_b)
    except Exception as _exc:
        print("page publish failed:", _exc, flush=True)
    threading.Thread(target=_indexer, daemon=True).start()
    if WARM_SECONDS > 0:
        threading.Thread(target=_warm_loop, daemon=True).start()
    if LIDARR_KEY:
        threading.Thread(target=_lidarr_loop, daemon=True).start()
    if ABS_KEY:
        threading.Thread(target=_abs_loop, daemon=True).start()
    if os.environ.get("PROXMOX_PASSWORD"):
        threading.Thread(target=_infra_loop, daemon=True).start()
    threading.Thread(target=_tools_loop, daemon=True).start()
    threading.Thread(target=_rel_loop, daemon=True).start()
    threading.Thread(target=_cam_loop, daemon=True).start()
    threading.Thread(target=_dev_loop, daemon=True).start()
    threading.Thread(target=shop_loop, daemon=True).start()
    if os.environ.get("TAILSCALE_OAUTH_SECRET"):
        threading.Thread(target=_net_loop, args=("tailscale", _tailscale, 120), daemon=True).start()
    if os.environ.get("NPM_PASS"):
        threading.Thread(target=_net_loop, args=("npm", _npmst, 60), daemon=True).start()
    if PRIVB_KEY:
        threading.Thread(target=_private_loop, args=(refresh_privb, _privb), daemon=True).start()
    if IMMICH_KEY and IMMICH_URL:
        threading.Thread(target=_private_loop, args=(refresh_immich, _immich), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 3005), H).serve_forever()
