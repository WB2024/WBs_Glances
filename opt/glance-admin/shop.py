"""Shopping page for Glance (stdlib only; imported by app.py).

State (shopping.json): shopping list, wishlist (with gift ideas and target prices), purchases, deal-alert terms, saved eBay searches.
Live data (cached): deals (HotUKDeals + Reddit RSS, matched against your terms), Raspberry Pi stock, eBay search results (official
Browse API: needs EBAY_APP_ID / EBAY_CERT_ID), Discogs collection and wantlist (DISCOGS_TOKEN), and price / stock watches
(a changedetection.io container: CHANGEDETECTION_URL / CHANGEDETECTION_KEY).
Everything is validated before it is stored; nothing here talks to a shop except through those APIs and public RSS feeds.
"""
import base64
import datetime
import email.utils
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
CATS = ("Tech", "Music", "Home", "DIY", "Tools", "Other")
LIMITS = {"list": 300, "wishlist": 300, "purchases": 3000, "terms": 40, "ebay": 12}


# ----------------------------------------------------------------------------- state
def default_state():
    return {"list": [], "wishlist": [], "purchases": [], "terms": ["ddr3", "thinkcentre", "quadro t1000", "i7-4790s", "mergerfs"],
            "ebay": [{"id": "e0000seed1", "q": "ddr3 8gb 1600 udimm", "max": 25.0, "cond": "any", "opts": "any"},
                     {"id": "e0000seed2", "q": "thinkcentre m73", "max": 60.0, "cond": "any", "opts": "any"},
                     {"id": "e0000seed3", "q": "nvidia quadro t1000 low profile", "max": 150.0, "cond": "any", "opts": "any"}]}


def new_id(p):
    return p + uuid.uuid4().hex[:9]


def _s(v, n):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]", " ", str(v or ""))).strip()[:n]


def _price(v):
    if v in (None, ""):
        return None
    try:
        f = round(float(str(v).replace("£", "").replace(",", "").strip()), 2)
    except ValueError:
        raise ValueError("price must be a number")
    if not 0 <= f <= 1_000_000:
        raise ValueError("price is out of range")
    return f


def _url(v, required=False):
    u = _s(v, 600)
    if not u:
        if required:
            raise ValueError("enter a web address")
        return ""
    if "://" not in u:
        u = "https://" + u
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc or not re.fullmatch(r"[A-Za-z0-9._-]+(:\d+)?", p.netloc.split("@")[-1]):
        raise ValueError("only http(s) addresses are allowed")
    return u


def _cat(v):
    c = _s(v, 20).lower()
    return next((k for k in CATS if k.lower() == c), "Other")


def _find(state, key, iid):
    for i, it in enumerate(state[key]):
        if it["id"] == iid:
            return i, it
    raise KeyError(iid)


def _cap(state, key):
    if len(state[key]) >= LIMITS[key if key in LIMITS else "list"]:
        raise ValueError("too many entries (limit %d)" % LIMITS[key])


def list_add(state, text, qty="", store="", cat=""):
    text = _s(text, 120)
    if not text:
        raise ValueError("enter an item")
    _cap(state, "list")
    it = {"id": new_id("s"), "text": text, "qty": _s(qty, 12), "store": _s(store, 30), "cat": _cat(cat), "done": False, "added": int(time.time())}
    state["list"].append(it)
    return it


def list_patch(state, iid, body):
    _, it = _find(state, "list", iid)
    if "done" in body:
        it["done"] = bool(body["done"])
    for k, n in (("text", 120), ("qty", 12), ("store", 30)):
        if k in body:
            it[k] = _s(body[k], n)
    if "cat" in body:
        it["cat"] = _cat(body["cat"])
    if not it["text"]:
        raise ValueError("enter an item")
    return it


def list_clear_done(state):
    n = len(state["list"])
    state["list"] = [i for i in state["list"] if not i["done"]]
    return n - len(state["list"])


def wish_add(state, title, url="", target=None, priority=2, cat="", notes="", gift=False):
    title = _s(title, 120)
    if not title:
        raise ValueError("enter what you want")
    _cap(state, "wishlist")
    it = {"id": new_id("w"), "title": title, "url": _url(url), "target": _price(target), "priority": min(3, max(1, int(priority or 2))), "cat": _cat(cat),
          "notes": _s(notes, 200), "gift": bool(gift), "watch": "", "added": int(time.time())}
    state["wishlist"].append(it)
    return it


def wish_patch(state, iid, body):
    _, it = _find(state, "wishlist", iid)
    if "title" in body:
        it["title"] = _s(body["title"], 120) or it["title"]
    if "url" in body:
        it["url"] = _url(body["url"])
    if "target" in body:
        it["target"] = _price(body["target"])
    if "priority" in body:
        it["priority"] = min(3, max(1, int(body["priority"] or 2)))
    if "notes" in body:
        it["notes"] = _s(body["notes"], 200)
    if "cat" in body:
        it["cat"] = _cat(body["cat"])
    if "watch" in body:
        it["watch"] = _s(body["watch"], 40) if re.fullmatch(r"[0-9a-f-]{36}", str(body["watch"] or "")) or not body["watch"] else it["watch"]
    return it


def purchase_add(state, title, price, store="", cat="", date=""):
    title = _s(title, 120)
    if not title:
        raise ValueError("enter what you bought")
    p = _price(price)
    if p is None:
        raise ValueError("enter the price")
    d = _s(date, 10)
    if d:
        try:
            datetime.date.fromisoformat(d)
        except ValueError:
            raise ValueError("date must look like 2026-10-02")
    else:
        d = datetime.date.today().isoformat()
    _cap(state, "purchases")
    it = {"id": new_id("p"), "title": title, "price": p, "store": _s(store, 30), "cat": _cat(cat), "date": d}
    state["purchases"].append(it)
    return it


def wish_bought(state, iid, price, store="", date=""):
    i, w = _find(state, "wishlist", iid)
    p = purchase_add(state, w["title"], price if price not in (None, "") else w.get("target"), store, w["cat"], date)
    del state["wishlist"][i]
    return p


def remove(state, key, iid):
    i, it = _find(state, key, iid)
    del state[key][i]
    return it


def term_add(state, term):
    term = _s(term, 40).lower()
    if len(term) < 2:
        raise ValueError("enter a word or phrase of at least 2 characters")
    if term in state["terms"]:
        raise ValueError("already on the list")
    if len(state["terms"]) >= LIMITS["terms"]:
        raise ValueError("too many terms")
    state["terms"].append(term)
    return term


def term_remove(state, term):
    term = _s(term, 40).lower()
    if term not in state["terms"]:
        raise KeyError(term)
    state["terms"].remove(term)


def ebay_add(state, q, max_price=None, cond="any", opts="any"):
    q = _s(q, 80)
    if len(q) < 2:
        raise ValueError("enter something to search for")
    if len(state["ebay"]) >= LIMITS["ebay"]:
        raise ValueError("too many saved searches (limit %d)" % LIMITS["ebay"])
    it = {"id": new_id("e"), "q": q, "max": _price(max_price), "cond": cond if cond in ("any", "new", "used") else "any",
          "opts": opts if opts in ("any", "bin", "auction") else "any"}
    state["ebay"].append(it)
    return it


def normalise(state):
    d = default_state()
    for k in ("list", "wishlist", "purchases", "terms", "ebay"):
        state.setdefault(k, d[k])
    return state


# ----------------------------------------------------------------------------- generic fetch + cache
def _get(url, headers=None, timeout=15, raw=False):
    h = {"User-Agent": UA, "Accept": "*/*"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        body = r.read(6_000_000)
        return body if raw else json.loads(body.decode("utf-8"))


_cache = {}
_cache_lock = threading.Lock()


def cached(key, ttl, fn):
    """fn() result kept for ttl seconds; a failing refresh keeps the previous value (marked stale)."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
    except Exception as exc:
        if hit:
            val = dict(hit[1]) if isinstance(hit[1], dict) else hit[1]
            if isinstance(val, dict):
                val["stale"] = str(exc)[:80]
            return val
        return {"ok": False, "err": str(exc)[:100]}
    with _cache_lock:
        _cache[key] = (now, val)
    return val


def _age_min(ts):
    return max(0, int((time.time() - ts) / 60)) if ts else None


def _iso(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


# ----------------------------------------------------------------------------- deals (public RSS)
HUKD = "https://www.hotukdeals.com/rss/"
DEAL_FEEDS = [("HotUKDeals", "hukd", HUKD + "trending"), ("HotUKDeals · computing", "hukd", HUKD + "tag/computing"),
              ("HotUKDeals · electronics", "hukd", HUKD + "tag/electronics"), ("HotUKDeals · DIY", "hukd", HUKD + "tag/diy"),
              ("HotUKDeals · music", "hukd", HUKD + "tag/music"), ("HotUKDeals · vinyl", "hukd", HUKD + "tag/vinyl"),
              ("HotUKDeals · audio", "hukd", HUKD + "tag/audio"),
              ("r/UKDeals", "reddit", "https://www.reddit.com/r/UKDeals/.rss"), ("r/buildapcsalesuk", "reddit", "https://www.reddit.com/r/buildapcsalesuk/.rss")]
PRICE_RE = re.compile(r"£\s?\d[\d,]*(?:\.\d\d)?")


def _strip(html_text):
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", html_text or ""))).strip()


def _feed(label, url):
    root = ET.fromstring(_get(url, timeout=15, raw=True))
    out = []
    items = [e for e in root.iter() if e.tag.split("}")[-1] in ("item", "entry")]
    for e in items:
        def child(name):
            return next((c for c in e if c.tag.split("}")[-1] == name), None)
        t = child("title")
        title = _strip(t.text if t is not None else "")
        link = ""
        for c in e:
            if c.tag.split("}")[-1] == "link":
                link = c.get("href") or (c.text or "")
                break
        when = 0
        d = next((x for x in (child("pubDate"), child("updated"), child("published")) if x is not None and x.text), None)
        if d is not None:
            try:
                when = email.utils.parsedate_to_datetime(d.text).timestamp()
            except Exception:
                when = _iso(d.text)
        merchant = next((c.get("name") for c in e if c.tag.split("}")[-1] == "merchant"), "")
        thumb = next((c.get("url") for c in e if c.tag.split("}")[-1] == "thumbnail"), "")
        desc = next((x for x in (child("description"), child("content"), child("summary")) if x is not None), None)
        text = _strip(desc.text if desc is not None else "")
        if not title or not link:
            continue
        m = PRICE_RE.search(title) or PRICE_RE.search(text[:300])
        out.append({"title": title[:160], "url": link, "source": label, "merchant": merchant, "when": when, "price": m.group(0).replace(" ", "") if m else "",
                    "thumb": thumb if label.startswith("HotUKDeals") else "", "desc": text[:200]})
    return out


def _matches(item, terms):
    hay = (item["title"] + " " + item["desc"] + " " + item["merchant"]).lower()
    hits = [t for t in terms if all(w in hay for w in t.split())]
    return hits


def deals(group="hukd"):
    """One group of feeds: 'hukd' (HotUKDeals, fetched often) or 'reddit' (rate-limited, fetched rarely and one at a time)."""
    wanted = [(lab, url) for lab, g, url in DEAL_FEEDS if (g == "reddit") == (group == "reddit")]
    results, errors = [], []
    if group == "reddit":
        for lab, url in wanted:
            try:
                results += _feed(lab, url)
            except urllib.error.HTTPError as exc:
                if exc.code != 429:                      # 429 = Reddit asking us to slow down: skip quietly, try again next time
                    errors.append("%s: HTTP %d" % (lab, exc.code))
            except Exception as exc:
                errors.append("%s: %s" % (lab, str(exc)[:50]))
            time.sleep(2.5)
    else:
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [(lab, ex.submit(_feed, lab, url)) for lab, url in wanted]
            for lab, f in futs:
                try:
                    results += f.result(timeout=40)
                except Exception as exc:
                    errors.append("%s: %s" % (lab, str(exc)[:50]))
    return {"ok": bool(results), "items": results, "errors": errors, "fetched": int(time.time())}


def merge_deals(*parts):
    items, errors = [], []
    for p in parts:
        if isinstance(p, dict):
            items += p.get("items", [])
            errors += p.get("errors", []) + ([p["err"]] if p.get("err") else [])
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: -x.get("when", 0)):
        key = re.sub(r"[?#].*", "", it["url"])
        if key in seen:
            continue
        seen.add(key)
        c = dict(it)
        c["age_min"] = max(0, int((time.time() - c["when"]) / 60)) if c.get("when") else -1
        c.pop("when", None)
        uniq.append(c)
    return {"ok": bool(uniq), "items": uniq[:120], "errors": errors, "fetched": int(time.time())}


def deals_for(terms, raw):
    """Applies the user's alert terms to cached deals (cheap: done per request, so editing terms is instant)."""
    items = raw.get("items", []) if isinstance(raw, dict) else []
    out = []
    for it in items:
        c = dict(it)
        c["hits"] = _matches(c, terms)
        out.append(c)
    matches = [i for i in out if i["hits"]]
    return {"ok": raw.get("ok", False) if isinstance(raw, dict) else False, "matches": matches[:20], "match_count": len(matches), "latest": out[:40],
            "errors": raw.get("errors", []) if isinstance(raw, dict) else [], "fetched": raw.get("fetched", 0) if isinstance(raw, dict) else 0,
            "terms": terms, "err": raw.get("err", "") if isinstance(raw, dict) else ""}


def stock():
    items = []
    try:
        root = ET.fromstring(_get("https://rpilocator.com/feed/?country=GB", raw=True))
        for e in root.iter():
            if e.tag.split("}")[-1] == "item":
                g = lambda n: next((c.text or "" for c in e if c.tag.split("}")[-1] == n), "")
                when = 0
                try:
                    when = email.utils.parsedate_to_datetime(g("pubDate")).timestamp()
                except Exception:
                    pass
                items.append({"title": _strip(g("title"))[:120], "url": g("link"), "age_min": _age_min(when) if when else -1})
    except Exception as exc:
        return {"ok": False, "err": str(exc)[:80], "items": []}
    return {"ok": True, "items": items[:12], "fetched": int(time.time())}


# ----------------------------------------------------------------------------- eBay (official Browse API)
_ebay_tok = {"v": "", "exp": 0}


def ebay_configured():
    return bool(os.environ.get("EBAY_APP_ID") and os.environ.get("EBAY_CERT_ID"))


def _ebay_token():
    if _ebay_tok["v"] and time.time() < _ebay_tok["exp"] - 60:
        return _ebay_tok["v"]
    auth = base64.b64encode(("%s:%s" % (os.environ["EBAY_APP_ID"], os.environ["EBAY_CERT_ID"])).encode()).decode()
    req = urllib.request.Request("https://api.ebay.com/identity/v1/oauth2/token", method="POST",
                                 data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": "Basic " + auth})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    _ebay_tok.update(v=d["access_token"], exp=time.time() + int(d.get("expires_in", 7200)))
    return _ebay_tok["v"]


def ebay_results(searches):
    if not ebay_configured():
        return {"configured": False, "searches": []}
    try:
        tok = _ebay_token()
    except Exception as exc:
        return {"configured": True, "ok": False, "err": "eBay sign-in failed: %s" % str(exc)[:60], "searches": []}
    out = []
    for s in searches:
        flt = []
        if s.get("max"):
            flt.append("price:[..%s],priceCurrency:GBP" % s["max"])
        if s.get("cond") == "new":
            flt.append("conditions:{NEW}")
        elif s.get("cond") == "used":
            flt.append("conditions:{USED}")
        if s.get("opts") == "bin":
            flt.append("buyingOptions:{FIXED_PRICE}")
        elif s.get("opts") == "auction":
            flt.append("buyingOptions:{AUCTION}")
        params = {"q": s["q"], "limit": 8, "sort": "newlyListed"}
        if flt:
            params["filter"] = ",".join(flt)
        entry = {"id": s["id"], "q": s["q"], "max": s.get("max"), "cond": s.get("cond"), "opts": s.get("opts"), "items": [], "total": 0}
        try:
            d = _get("https://api.ebay.com/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params),
                     {"Authorization": "Bearer " + tok, "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB", "Accept": "application/json"}, timeout=20)
            entry["total"] = d.get("total", 0)
            for i in d.get("itemSummaries", []):
                price = (i.get("price") or {})
                ship = ((i.get("shippingOptions") or [{}])[0].get("shippingCost") or {})
                entry["items"].append({"title": _s(i.get("title"), 90), "url": i.get("itemWebUrl", ""), "price": price.get("value", ""), "ccy": price.get("currency", "GBP"),
                                       "ship": ship.get("value", ""), "img": ((i.get("thumbnailImages") or [{}])[0].get("imageUrl")) or (i.get("image") or {}).get("imageUrl", ""),
                                       "cond": i.get("condition", ""), "auction": "AUCTION" in (i.get("buyingOptions") or []),
                                       "ends": (i.get("itemEndDate") or "")[:19], "age_min": _age_min(_iso(i.get("itemCreationDate"))),
                                       "seller": (i.get("seller") or {}).get("username", ""), "fb": (i.get("seller") or {}).get("feedbackPercentage", "")})
        except urllib.error.HTTPError as exc:
            entry["err"] = "eBay answered %d" % exc.code
        except Exception as exc:
            entry["err"] = str(exc)[:60]
        out.append(entry)
    return {"configured": True, "ok": True, "searches": out, "fetched": int(time.time())}


# ----------------------------------------------------------------------------- Discogs
def discogs():
    tok = os.environ.get("DISCOGS_TOKEN", "")
    if not tok:
        return {"configured": False}
    H = {"Authorization": "Discogs token=" + tok, "User-Agent": "glance-admin/1 +homelab"}
    api = "https://api.discogs.com"
    me = _get(api + "/oauth/identity", H)["username"]
    prof = _get("%s/users/%s" % (api, me), H)
    value = {}
    try:
        value = _get("%s/users/%s/collection/value" % (api, me), H)
    except Exception:
        pass

    def money(s):
        m = re.search(r"[\d,]+(?:\.\d+)?", s or "")
        return float(m.group(0).replace(",", "")) if m else 0.0
    folders = []
    try:
        folders = [{"name": f["name"], "count": f["count"]} for f in _get("%s/users/%s/collection/folders" % (api, me), H).get("folders", []) if f["id"] != 0][:8]
    except Exception:
        pass
    recent = []
    try:
        rel = _get("%s/users/%s/collection/folders/0/releases?per_page=14&sort=added&sort_order=desc" % (api, me), H).get("releases", [])
        for r in rel:
            b = r.get("basic_information", {})
            recent.append({"title": _s(b.get("title"), 80), "artist": _s(", ".join(a.get("name", "") for a in b.get("artists", [])[:2]), 60), "year": b.get("year") or "",
                           "thumb": b.get("thumb") or b.get("cover_image") or "", "fmt": _s(", ".join(f.get("name", "") for f in b.get("formats", [])[:2]), 30),
                           "url": "https://www.discogs.com/release/%s" % b.get("id", ""), "added_days": max(0, int((time.time() - _iso(r.get("date_added"))) / 86400)) if r.get("date_added") else -1})
    except Exception:
        pass
    wants = []
    if prof.get("num_wantlist", 0):
        try:
            w = _get("%s/users/%s/wants?per_page=20&sort=added&sort_order=desc" % (api, me), H).get("wants", [])
            for x in w:
                b = x.get("basic_information", {})
                low, n = None, 0
                try:
                    st = _get("%s/marketplace/stats/%s?curr_abbr=GBP" % (api, b.get("id")), H)
                    low = (st.get("lowest_price") or {}).get("value")
                    n = st.get("num_for_sale", 0)
                except Exception:
                    pass
                wants.append({"title": _s(b.get("title"), 80), "artist": _s(", ".join(a.get("name", "") for a in b.get("artists", [])[:2]), 60), "year": b.get("year") or "",
                              "thumb": b.get("thumb") or "", "lowest": low, "for_sale": n, "url": "https://www.discogs.com/release/%s" % b.get("id", "")})
                time.sleep(1.1)
        except Exception:
            pass
    return {"configured": True, "ok": True, "items": prof.get("num_collection", 0), "wantlist": prof.get("num_wantlist", 0), "for_sale": prof.get("num_for_sale", 0),
            "value_min": money(value.get("minimum")), "value_median": money(value.get("median")), "value_max": money(value.get("maximum")),
            "folders": folders, "recent": recent, "wants": wants, "profile_url": "https://www.discogs.com/user/%s/collection" % me, "fetched": int(time.time())}


# ----------------------------------------------------------------------------- changedetection.io price / stock watches
def cd_configured():
    return bool(os.environ.get("CHANGEDETECTION_URL") and os.environ.get("CHANGEDETECTION_KEY"))


def _cd(method, path, body=None, timeout=20):
    req = urllib.request.Request(os.environ["CHANGEDETECTION_URL"].rstrip("/") + "/api/v1" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-api-key": os.environ["CHANGEDETECTION_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode()) if raw else {}
    except ValueError:
        return raw.decode("utf-8", "ignore")


SNAP_RE = re.compile(r"In Stock:\s*(True|False)(?:\s*-\s*Price:\s*([\d.,]+))?", re.I)


def _snap(uid, ts):
    txt = _cd("GET", "/watch/%s/history/%s" % (uid, ts), timeout=15)
    m = SNAP_RE.search(txt if isinstance(txt, str) else "")
    if not m:
        return None
    return {"in_stock": m.group(1).lower() == "true", "price": float(m.group(2).replace(",", "")) if m.group(2) else None}


def apply_targets(data, targets):
    """Marks watches that are at or below the wishlist target (done per request so editing a target is instant)."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    out["items"] = []
    for it in data.get("items", []):
        c = dict(it)
        c["target"] = targets.get(c["id"])
        c["at_target"] = bool(c["price"] is not None and c["target"] and c["price"] <= c["target"])
        out["items"].append(c)
    out["items"].sort(key=lambda x: (not x["at_target"], bool(x["error"]), x["title"].lower()))
    return out


def watches():
    if not cd_configured():
        return {"configured": False, "items": []}
    try:
        lst = _cd("GET", "/watch")
    except Exception as exc:
        return {"configured": True, "ok": False, "err": "changedetection.io not reachable: %s" % str(exc)[:60], "items": []}
    items = []
    for uid, w in lst.items():
        it = {"id": uid, "title": _s(w.get("title") or w.get("page_title") or w.get("url"), 90), "url": w.get("url", ""), "age_min": _age_min(w.get("last_checked")),
              "changed_min": _age_min(w.get("last_changed")) if w.get("last_changed") else -1, "price": None, "prev": None, "in_stock": None, "target": None,
              "error": ""}
        err = w.get("last_error")
        if err:
            e = str(err)
            it["error"] = ("blocked by the shop (403): it refuses automatic checks" if "403" in e else "page not found (404)" if "404" in e else _s(e, 80))
        try:
            hist = _cd("GET", "/watch/%s/history" % uid, timeout=15)
            stamps = sorted(hist.keys(), key=lambda x: int(x))[-6:]
            snaps = [s for s in (_snap(uid, t) for t in reversed(stamps[-2:])) if s]
            if snaps:
                it["price"], it["in_stock"] = snaps[0]["price"], snaps[0]["in_stock"]
                if len(snaps) > 1:
                    it["prev"] = snaps[1]["price"]
        except Exception:
            pass
        if it["price"] is not None and it["prev"] not in (None, 0):
            it["change_pct"] = round((it["price"] - it["prev"]) / it["prev"] * 100, 1)
        else:
            it["change_pct"] = 0
        it["at_target"] = False
        items.append(it)
    return {"configured": True, "ok": True, "items": items, "fetched": int(time.time())}


def watch_add(url, title="", browser=False):
    url = _url(url, required=True)
    body = {"url": url, "title": _s(title, 90), "processor": "restock_diff", "tag": "glance", "time_between_check": {"hours": 6}}
    if browser:
        body["fetch_backend"] = "html_webdriver"
    d = _cd("POST", "/watch", body)
    if not isinstance(d, dict) or "uuid" not in d:
        raise ValueError("changedetection.io did not accept that address")
    return d["uuid"]


def watch_remove(uid):
    if not re.fullmatch(r"[0-9a-f-]{36}", uid or ""):
        raise ValueError("bad watch id")
    _cd("DELETE", "/watch/" + uid)


def watch_recheck(uid):
    if not re.fullmatch(r"[0-9a-f-]{36}", uid or ""):
        raise ValueError("bad watch id")
    _cd("GET", "/watch/%s?recheck=1" % uid)
