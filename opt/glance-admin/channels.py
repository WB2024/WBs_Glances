"""YouTube channel management for the Glance 'Video News Feed' page (stdlib only; imported by app.py).

resolve(text) accepts a channel ID (UC...), a /channel/UC... URL, an @handle, or a youtube.com URL of a handle/user/custom name,
finds the real channel ID from the page's canonical link, then VERIFIES it by fetching the channel's public RSS feed and using
the feed's own title as the channel name (so a wrong ID can never be saved silently).
render_yaml(channels) builds the whole page file; Glance reloads it when the file changes.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UC_RE = re.compile(r"UC[0-9A-Za-z_-]{22}")
HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
       "Accept-Language": "en-GB,en;q=0.8", "Cookie": "CONSENT=YES+1; SOCS=CAI"}


def _fetch(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def feed_title(cid):
    try:
        xml = _fetch("https://www.youtube.com/feeds/videos.xml?channel_id=" + cid)
    except urllib.error.HTTPError as e:
        raise ValueError("YouTube has no feed for that channel id (HTTP %d)" % e.code)
    return ET.fromstring(xml).findtext("{http://www.w3.org/2005/Atom}title") or cid


def resolve(text):
    s = (text or "").strip()
    if not s or len(s) > 300:
        raise ValueError("enter a channel @handle, URL or ID")
    cid = None
    m = UC_RE.fullmatch(s)
    if m:
        cid = m.group(0)
    elif "/channel/" in s:
        m = UC_RE.search(s.split("/channel/", 1)[1])
        cid = m.group(0) if m else None
    if not cid:
        if "youtube.com" in s or "youtu.be" in s:
            url = s if s.startswith("http") else "https://" + s
            p = urllib.parse.urlparse(url)
            if "youtube.com" not in (p.netloc or ""):
                raise ValueError("paste a youtube.com channel link or an @handle")
            url = "https://www.youtube.com" + p.path
        else:
            url = "https://www.youtube.com/" + (s if s.startswith("@") else "@" + s.lstrip("@/"))
        try:
            page = _fetch(url)
        except urllib.error.HTTPError as e:
            raise ValueError("no YouTube channel found at that address (HTTP %d)" % e.code)
        m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"', page) \
            or re.search(r'<meta itemprop="(?:identifier|channelId)" content="(UC[0-9A-Za-z_-]{22})"', page)
        if not m:
            raise ValueError("could not find a channel at that address")
        cid = m.group(1)
    name = feed_title(cid)
    return {"id": cid, "name": name}


def _q(text):
    return json.dumps(str(text).replace("${", "$ {"), ensure_ascii=False)


def render_yaml(channels):
    out = ["- name: Video News Feed", "  slug: video-news", "  width: wide", "  columns:", "    - size: full", "      widgets:",
           "        - type: html", "          source: |",
           '            <div class="widget-header"><h2 class="uppercase">Channels</h2></div>',
           '            <div data-wb="channels" data-wb-noindex></div>']
    for c in channels:
        out += ["", "        - type: videos", "          title: " + _q(c["name"]),
                "          title-url: " + _q("https://www.youtube.com/channel/" + c["id"]),
                "          channels:", "            - " + c["id"],
                "          style: horizontal-cards", "          limit: 14", "          cache: 30m"]
    return "\n".join(out) + "\n"
