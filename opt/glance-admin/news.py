"""News Feeds page for Glance: RSS feeds and subreddits you can add and remove from the page itself (stdlib only; imported by app.py).

State is news.json (groups of feeds / subreddits); render_yaml(state) builds the whole page file that Glance includes
(config/data/news.yml). Layout is the one gen_news.py used to write: three columns (left small, centre full, right small);
Top stories (Hacker News + Lobsters) and Markets are fixed, every other widget is a group from the state.

add_*() verify before anything is saved: a feed must parse as RSS/Atom (the feed's own title is used), a subreddit must exist.
"""
import json
import re
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0 glance-admin", "Accept": "*/*"}
SUB_RE = re.compile(r"[A-Za-z0-9_]{2,21}")
MAX_FEEDS, MAX_SUBS, MAX_GROUPS = 100, 150, 24
COLUMNS = ("left", "centre", "right")


def _g(gid, kind, title, column, **kw):
    d = {"id": gid, "kind": kind, "title": title, "column": column}
    d.update(kw)
    return d


SEED = {"groups": [
    _g("tech", "rss", "Tech news", "left", style="vertical-list", limit=20, collapse=8, extra="", feeds=[
        {"url": "https://www.theregister.com/headlines.atom", "title": "The Register"},
        {"url": "https://feeds.arstechnica.com/arstechnica/index", "title": "Ars Technica"},
        {"url": "https://feeds.bbci.co.uk/news/technology/rss.xml", "title": "BBC Tech"}]),
    _g("uk", "rss", "UK & local", "left", style="vertical-list", limit=18, collapse=6, extra="", feeds=[
        {"url": "https://feeds.bbci.co.uk/news/uk/rss.xml", "title": "BBC UK"},
        {"url": "https://feeds.bbci.co.uk/news/england/rss.xml", "title": "BBC England"},
        {"url": "https://feeds.bbci.co.uk/news/england/manchester/rss.xml", "title": "BBC Manchester"}]),
    _g("music", "rss", "Music", "centre", style="horizontal-cards", limit=30, collapse=8, extra="  card-height: 24\n", feeds=[
        {"url": "https://pitchfork.com/feed/feed-album-reviews/rss", "title": "Pitchfork reviews"},
        {"url": "https://thequietus.com/feed", "title": "The Quietus"},
        {"url": "https://www.stereogum.com/feed", "title": "Stereogum"},
        {"url": "https://www.nme.com/news/music/feed", "title": "NME"},
        {"url": "https://blog.musicbrainz.org/feed/", "title": "MusicBrainz blog"}]),
    _g("r_music", "reddit", "Reddit: music", "centre", subs=["Lidarr", "Soulseek", "musichoarder", "navidrome", "spotify", "jukeboxes", "vinyl"]),
    _g("r_taste", "reddit", "Reddit: taste", "centre", subs=["SongsThatFeelLikeThis", "Courtneylove", "Hole"]),
    _g("homelab", "rss", "Homelab & self-hosting", "centre", style="detailed-list", limit=24, collapse=6, extra="", feeds=[
        {"url": "https://selfh.st/rss/", "title": "selfh.st"},
        {"url": "https://pi-hole.net/feed/", "title": "Pi-hole"},
        {"url": "https://www.home-assistant.io/atom.xml", "title": "Home Assistant"},
        {"url": "https://tailscale.com/blog/index.xml", "title": "Tailscale"},
        {"url": "https://forum.proxmox.com/forums/-/index.rss", "title": "Proxmox forum"},
        {"url": "https://torrentfreak.com/feed/", "title": "TorrentFreak"}]),
    _g("r_self", "reddit", "Reddit: self-hosting", "centre", subs=["selfhosted", "homelab", "Proxmox", "pihole", "homeassistant", "jellyfin"]),
    _g("r_data", "reddit", "Reddit: data hoarding", "centre", subs=["DataHoarder", "datacurator", "opendirectories", "backup", "Softwarr", "MXLinux", "linuxmint"]),
    _g("r_excel", "reddit", "Reddit: Excel & work", "right", subs=["excel", "ExcelPowerQuery"]),
    _g("r_media", "reddit", "Reddit: media & obscure", "right", subs=["Piracy", "PiratedGames", "ObscureMedia", "lostmedia", "FanTheories", "MoviesThatFeelLike"]),
]}


# ----------------------------------------------------------------------------- page file
def _q(text):
    """Quoted YAML scalar. '${' would be expanded by Glance's environment substitution, so it is broken up."""
    return json.dumps(str(text).replace("${", "$ {"), ensure_ascii=False)


def _block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def _reddit(sub, limit=12, collapse=6):
    return "- type: reddit\n  title: r/%s\n  subreddit: %s\n  style: vertical-list\n  limit: %d\n  collapse-after: %d\n  cache: 30m\n" % (sub, sub, limit, collapse)


def _widget(g):
    if g["kind"] == "reddit":
        return "- type: group\n  widgets:\n" + "".join(_block(_reddit(s), 4) for s in g["subs"])
    feeds = "".join("    - url: %s\n      title: %s\n" % (_q(f["url"]), _q(f["title"])) for f in g["feeds"])
    return "- type: rss\n  title: %s\n  style: %s\n  limit: %d\n  collapse-after: %d\n%s  feeds:\n%s" % (
        _q(g["title"]), g["style"], g["limit"], g["collapse"], g.get("extra", ""), feeds)


TOP_STORIES = "- type: group\n  widgets:\n    - type: hacker-news\n      limit: 15\n      collapse-after: 8\n    - type: lobsters\n      limit: 12\n      collapse-after: 8\n"
MARKETS = ("- type: markets\n  title: Markets\n  markets:\n    - { symbol: GBPUSD=X, name: GBP / USD }\n    - { symbol: GBPEUR=X, name: GBP / EUR }\n"
           "    - { symbol: BTC-GBP,  name: Bitcoin }\n    - { symbol: ^FTSE,    name: FTSE 100 }\n    - { symbol: BP.L,     name: BP }\n"
           "    - { symbol: NVDA,     name: NVIDIA }\n")
EDITOR = ("- type: html\n  source: |\n    <div class=\"widget-header\"><h2 class=\"uppercase\">Feeds</h2></div>\n"
          "    <div data-wb=\"news\" data-wb-noindex></div>\n")


def _col(size, widgets):
    out = "    - size: %s\n      widgets:\n" % size
    for w in widgets:
        lines = w.rstrip("\n").split("\n")
        out += "        " + lines[0] + "\n" + "".join("        " + l + "\n" for l in lines[1:]) + "\n"
    return out


def render_yaml(state):
    cols = {"left": [TOP_STORIES], "centre": [EDITOR], "right": [MARKETS]}
    for g in state["groups"]:
        if (g["kind"] == "rss" and g["feeds"]) or (g["kind"] == "reddit" and g["subs"]):
            cols[g["column"] if g["column"] in cols else "centre"].append(_widget(g))
    return ("- name: News Feeds\n  slug: news\n  width: wide\n  columns:\n" + _col("small", cols["left"]) + _col("full", cols["centre"]) + _col("small", cols["right"]))


# ----------------------------------------------------------------------------- state helpers
def public(state):
    out = []
    for g in state["groups"]:
        d = {"id": g["id"], "kind": g["kind"], "title": g["title"], "column": g["column"]}
        d["items"] = [{"key": f["url"], "label": f["title"]} for f in g["feeds"]] if g["kind"] == "rss" else [{"key": s, "label": "r/" + s} for s in g["subs"]]
        out.append(d)
    return {"groups": out}


def _slug(title, taken):
    base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:24] or "group"
    gid, n = base, 2
    while gid in taken:
        gid = "%s_%d" % (base, n)
        n += 1
    return gid


# ----------------------------------------------------------------------------- verification
def _fetch(url, timeout=15, limit=2_000_000):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.headers.get("Content-Type", ""), r.read(limit).decode("utf-8", "ignore")


def _feed_title(body):
    root = ET.fromstring(body.lstrip("﻿ \r\n\t"))
    tag = root.tag.split("}")[-1].lower()
    if tag == "rss":
        ch = root.find("channel")
        return (ch.findtext("title") if ch is not None else None) or ""
    if tag == "feed":
        return root.findtext("{http://www.w3.org/2005/Atom}title") or ""
    if tag == "rdf":
        ch = root.find("{http://purl.org/rss/1.0/}channel")
        return (ch.findtext("{http://purl.org/rss/1.0/}title") if ch is not None else None) or ""
    raise ValueError("that address is not an RSS or Atom feed")


def verify_feed(text):
    s = (text or "").strip()
    if not s or len(s) > 400 or re.search(r"\s", s):
        raise ValueError("enter a feed address (https://...)")
    if "://" not in s:
        s = "https://" + s
    p = urllib.parse.urlparse(s)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("feeds must be http or https addresses")
    try:
        final, ctype, body = _fetch(s)
    except urllib.error.HTTPError as e:
        raise ValueError("the feed server answered HTTP %d" % e.code)
    except Exception:
        raise ValueError("could not reach that address")
    try:
        title = _feed_title(body)
    except (ET.ParseError, ValueError):
        # a normal web page: follow its <link rel="alternate"> feed announcement, one hop only
        m = re.search(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>', body, re.I)
        href = re.search(r'href="([^"]+)"', m.group(0)) if m else None
        if not href:
            raise ValueError("that address is not an RSS or Atom feed and the page does not announce one")
        final = urllib.parse.urljoin(final, href.group(1).replace("&amp;", "&"))
        try:
            _, _, body = _fetch(final)
            title = _feed_title(body)
        except Exception:
            raise ValueError("found a feed link on that page but it could not be read")
    return {"url": final, "title": (title or urllib.parse.urlparse(final).netloc).strip()[:80]}


def parse_sub(text):
    s = (text or "").strip()
    m = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", s)
    if m:
        s = m.group(1)
    s = re.sub(r"^/?r/", "", s).strip("/")
    return s if SUB_RE.fullmatch(s) else None


def looks_like_sub(text):
    s = (text or "").strip()
    return bool(re.search(r"reddit\.com/r/", s)) or bool(re.fullmatch(r"/?(r/)?[A-Za-z0-9_]{2,21}", s))


def verify_sub(text):
    """Returns (name, verified). Reddit blocks most server-side requests (403/429), so only a clear 404 rejects a name."""
    sub = parse_sub(text)
    if not sub:
        raise ValueError("a subreddit name looks like r/selfhosted (letters, numbers, underscores)")
    try:
        _, _, body = _fetch("https://www.reddit.com/r/%s/.rss" % sub, timeout=15, limit=200_000)
        m = re.search(r"<title>\s*(?:r/)?([A-Za-z0-9_]{2,21})\s*</title>", body)
        return (m.group(1) if m and m.group(1).lower() == sub.lower() else sub), True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError("r/%s does not exist" % sub)
    except Exception:
        pass
    return sub, False


# ----------------------------------------------------------------------------- mutations (caller holds the lock and saves)
def _find(state, gid):
    for g in state["groups"]:
        if g["id"] == gid:
            return g
    raise KeyError(gid)


def _new_group(state, kind, title):
    title = (title or "").strip()[:40]
    if not title:
        raise ValueError("give the new group a name")
    if len(state["groups"]) >= MAX_GROUPS:
        raise ValueError("too many groups (limit %d)" % MAX_GROUPS)
    g = _g(_slug(title, {x["id"] for x in state["groups"]}), kind, title, "centre")
    if kind == "rss":
        g.update(style="vertical-list", limit=20, collapse=8, extra="", feeds=[])
    else:
        g["subs"] = []
    state["groups"].append(g)
    return g


def add(state, text, group, new_title=""):
    """Adds a feed or subreddit (kind decided by what was typed). Returns (group, label)."""
    kind = "reddit" if looks_like_sub(text) else "rss"
    if group in ("__new",):
        g = None
    else:
        try:
            g = _find(state, group)
        except KeyError:
            raise ValueError("unknown group")
        if g["kind"] != kind:
            raise ValueError("that is %s, but the chosen group holds %s" % ("a subreddit" if kind == "reddit" else "an RSS feed", "subreddits" if g["kind"] == "reddit" else "RSS feeds"))
    if kind == "reddit":
        sub, verified = verify_sub(text)
        if any(sub.lower() == s.lower() for x in state["groups"] if x["kind"] == "reddit" for s in x["subs"]):
            raise ValueError("r/%s is already on the page" % sub)
        if sum(len(x["subs"]) for x in state["groups"] if x["kind"] == "reddit") >= MAX_SUBS:
            raise ValueError("too many subreddits (limit %d)" % MAX_SUBS)
        g = g or _new_group(state, "reddit", new_title)
        g["subs"].append(sub)
        return g, "r/" + sub + ("" if verified else " (Reddit would not confirm it from here: check it appears)")
    found = verify_feed(text)
    if any(found["url"] == f["url"] for x in state["groups"] if x["kind"] == "rss" for f in x["feeds"]):
        raise ValueError("%s is already on the page" % found["title"])
    if sum(len(x["feeds"]) for x in state["groups"] if x["kind"] == "rss") >= MAX_FEEDS:
        raise ValueError("too many feeds (limit %d)" % MAX_FEEDS)
    g = g or _new_group(state, "rss", new_title)
    g["feeds"].append(found)
    return g, found["title"]


def remove(state, group, key):
    g = _find(state, group)
    if g["kind"] == "reddit":
        before = len(g["subs"])
        g["subs"] = [s for s in g["subs"] if s != key]
        return len(g["subs"]) != before
    before = len(g["feeds"])
    g["feeds"] = [f for f in g["feeds"] if f["url"] != key]
    return len(g["feeds"]) != before
