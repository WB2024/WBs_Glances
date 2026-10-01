"""Bookmarks for the Glance Bookmarks page (stdlib only; imported by app.py).

The single source of truth is JSON ({"columns":[{"size","groups":[{"id","title","color","links":[{"id","title","url","icon"}]}]}]}).
render_yaml() turns it into the whole page file (with an "Edit bookmarks" panel on top) which Glance reloads automatically.
New links get their page title and a favicon fetched here, and icons are cached locally so no icon lookups go to third parties.
"""
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

FAV_DIR = os.environ.get("FAVICON_DIR", "/favicons")
FAV_URL = "/assets/favicons/"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MAX_LINKS = 1500
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg",
       "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/ico": "ico"}
DEFAULT_ICON = "mdi:link-variant"


def new_id(prefix):
    return prefix + uuid.uuid4().hex[:10]


def ensure_ids(data):
    """Seeds and old data may lack ids; give every group/link one."""
    for col in data["columns"]:
        for g in col["groups"]:
            g.setdefault("id", new_id("g"))
            for l in g["links"]:
                l.setdefault("id", new_id("l"))
    return data


# --------------------------------------------------------------------------- validation
def clean_url(u):
    u = (u or "").strip()
    if not u:
        raise ValueError("enter a web address")
    if "://" not in u:
        # "javascript:..." / "mailto:..." etc. must not be mistaken for a bare host; "host:8080" and "example.com/x" are fine
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", u) and not re.match(r"^[\w.-]+:\d+(/|$)", u):
            raise ValueError("only http(s) addresses are allowed")
        host = re.split(r"[/?#]", u, 1)[0]
        local = bool(re.match(r"^(\d{1,3}\.){3}\d{1,3}(:\d+)?$", host) or re.search(r":\d+$", host)
                     or host.lower().endswith((".wbhomelab", ".local", ".lan", ".home.arpa")) or "." not in host)
        u = ("http://" if local else "https://") + u          # local services rarely have HTTPS
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc or len(u) > 600:
        raise ValueError("only http(s) addresses are allowed")
    try:
        p.port                                   # raises for a malformed port
    except ValueError:
        raise ValueError("that address does not look valid")
    if not p.hostname or not re.fullmatch(r"[A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\]", p.hostname):
        raise ValueError("that address does not look valid")
    return u


def clean_title(t, fallback=""):
    t = re.sub(r"\s+", " ", html.unescape(t or "")).strip() or fallback
    if not t:
        raise ValueError("enter a title")
    return t[:80]


# --------------------------------------------------------------------------- fetching title + icon
def _fetch(url, limit, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), (r.headers.get("Content-Type") or "").split(";")[0].strip().lower(), r.geturl()


def page_info(url):
    """(title, [icon candidate urls]) from the page itself; both best-effort."""
    p = urllib.parse.urlparse(url)
    cands = []
    title = ""
    try:
        body, ctype, final = _fetch(url, 200_000)
        text = body.decode("utf-8", "ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        for tag in re.findall(r"<link[^>]+>", text, re.I):
            if re.search(r'rel=["\'][^"\']*icon', tag, re.I):
                h = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
                if h:
                    cands.append(urllib.parse.urljoin(final, html.unescape(h.group(1))))
    except Exception:
        pass
    cands.append("%s://%s/favicon.ico" % (p.scheme, p.netloc))
    return title, cands


def fetch_icon(url, cands):
    """Download the first usable icon to FAV_DIR and return its /assets path, else the default mdi icon."""
    host = urllib.parse.urlparse(url).netloc.lower()
    key = hashlib.sha1(host.encode()).hexdigest()[:16]
    try:
        for fn in os.listdir(FAV_DIR):
            if fn.startswith(key + "."):
                return FAV_URL + fn
    except OSError:
        return DEFAULT_ICON
    for c in cands[:4]:
        try:
            body, ctype, _ = _fetch(c, 300_000)
            ext = EXT.get(ctype) or ("ico" if c.lower().split("?")[0].endswith(".ico") else None)
            if not ext or len(body) < 50:
                continue
            os.makedirs(FAV_DIR, exist_ok=True)
            tmp = os.path.join(FAV_DIR, key + ".tmp")
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, os.path.join(FAV_DIR, "%s.%s" % (key, ext)))
            return "%s%s.%s" % (FAV_URL, key, ext)
        except Exception:
            continue
    return DEFAULT_ICON


def prepare_link(url, title):
    url = clean_url(url)
    page_title, cands = page_info(url)
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return {"id": new_id("l"), "title": clean_title(title or page_title, host), "url": url, "icon": fetch_icon(url, cands)}


# --------------------------------------------------------------------------- operations (all pure on the data dict)
def find_group(data, gid):
    for ci, col in enumerate(data["columns"]):
        for g in col["groups"]:
            if g["id"] == gid:
                return ci, g
    raise KeyError("group")


def find_link(data, lid):
    for col in data["columns"]:
        for g in col["groups"]:
            for i, l in enumerate(g["links"]):
                if l["id"] == lid:
                    return g, i, l
    raise KeyError("link")


def count_links(data):
    return sum(len(g["links"]) for c in data["columns"] for g in c["groups"])


def add_group(data, title, column, color=None, private=False):
    title = clean_title(title)
    if any(g["title"].lower() == title.lower() for c in data["columns"] for g in c["groups"]):
        raise ValueError("a group called \"%s\" already exists" % title)
    column = int(column)
    if not 0 <= column < len(data["columns"]):
        raise ValueError("unknown column")
    if not color or not re.fullmatch(r"\d{1,3} \d{1,3} \d{1,3}", color):
        h = int(hashlib.sha1(title.encode()).hexdigest()[:4], 16) % 360
        color = "%d 55 60" % h
    g = {"id": new_id("g"), "title": title, "color": color, "links": []}
    if private:
        g["private"] = True          # rendered inside its own PIN-locked widget
    data["columns"][column]["groups"].append(g)
    return g


# --------------------------------------------------------------------------- yaml
def _q(text):
    return json.dumps(str(text).replace("${", "$ {"), ensure_ascii=False)


def _group_lines(g):
    out = ["            - title: " + _q(g["title"]), "              color: " + _q(g.get("color") or "0 0 60"),
           "              links:" if g["links"] else "              links: []"]
    for l in g["links"]:
        out += ["                - title: " + _q(l["title"]), "                  url: " + _q(l["url"])]
        if l.get("icon"):
            out.append("                  icon: " + _q(l["icon"]))
        if l.get("description"):
            out.append("                  description: " + _q(l["description"]))
    return out


def render_yaml(data):
    out = ["- name: Bookmarks", "  slug: bookmarks", "  width: wide", "  columns:"]
    for ci, col in enumerate(data["columns"]):
        out += ["    - size: %s" % col["size"], "      widgets:"]
        if ci == 1:                      # the editor panel sits at the top of the middle column
            out += ["        - type: html", "          source: |",
                    '            <div class="widget-header"><h2 class="uppercase">Bookmarks</h2></div>',
                    '            <div data-wb="bookmarks" data-wb-noindex></div>', ""]
        public = [g for g in col["groups"] if not g.get("private")]
        private = [g for g in col["groups"] if g.get("private")]
        if public or not private:
            out += ["        - type: bookmarks", "          groups:"]
            for g in public:
                out += _group_lines(g)
            out.append("")
        if private:                      # one locked widget per column: wb-restricted.js hides its content until the PIN is entered
            out += ["        - type: bookmarks", "          title: Private bookmarks", "          css-class: wb-restricted", "          groups:"]
            for g in private:
                out += _group_lines(g)
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
