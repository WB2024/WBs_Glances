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
    return {"up": up, "detail": "answering" if up else "not responding"}


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


# --------------------------------------------------------------------------- rich cards for the small tools (Tools page)
import html as _html

_CONTAINERS = {"kiwix": "nomad_kiwix_server", "kolibri": "nomad_kolibri_2", "nomad": "nomad_admin", "searxng": "searxng", "flatnotes": "nomad_flatnotes",
               "stirling": "nomad_stirling_pdf", "homebox": "nomad_homebox", "picard": "picard-web", "firefox": "browser", "vaultwarden": "vaultwarden"}


def _lister(path):
    tok = os.environ.get("TOKEN_SERVICES", "")
    return _get("http://%s:27974%s" % (HOST, path), {"Authorization": "Bearer " + tok}, timeout=25)[2]


def _container_info():
    """Per-tool container facts from the read-only lister: state, uptime text, image tag, CPU %, RAM MB."""
    try:
        cmap = {c["name"]: c for c in _lister("/containers")["containers"]}
    except Exception:
        return {}
    stats = {}
    try:
        running = [n for n in _CONTAINERS.values() if cmap.get(n, {}).get("state") == "running"]
        stats = {s["name"]: s for s in _lister("/stats?names=" + ",".join(running)).get("stats", [])}
    except Exception:
        pass            # an older lister without /stats: the cards simply omit CPU and RAM
    out = {}
    for key, name in _CONTAINERS.items():
        c = cmap.get(name)
        if not c:
            out[key] = {"found": False}
            continue
        s = stats.get(name, {})
        image = c.get("image", "")
        out[key] = {"found": True, "running": c["state"] == "running", "state": c["state"], "status": c.get("status", ""), "health": c.get("health", ""),
                    "image": image.split("/")[-1], "tag": image.rsplit(":", 1)[-1] if ":" in image.split("/")[-1] else "latest",
                    "cpu_pct": s.get("cpu_pct", -1), "mem_mb": s.get("mem_mb", -1)}
    return out


def _kiwix():
    try:
        _, _, b, _ = _get("http://%s:8090/catalog/v2/entries?count=500" % HOST, raw=True, timeout=15)
        ns = {"a": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/terms/"}
        root = ET.fromstring(b)
        libs = []
        for e in root.findall("a:entry", ns):
            def t(tag):
                x = e.find(tag, ns) if ":" in tag else e.find("{http://www.w3.org/2005/Atom}" + tag)
                return (x.text or "") if x is not None else ""
            link = next((l.get("href") for l in e.findall("a:link", ns) if l.get("type") == "text/html"), "")
            name = t("name") if e.find("{http://www.w3.org/2005/Atom}name") is not None else ""
            libs.append({"title": _html.unescape(t("title")), "name": name, "articles": int(t("articleCount") or 0), "media": int(t("mediaCount") or 0),
                         "updated": t("updated")[:10], "lang": t("language")[:3], "url": "http://%s:8090%s" % (LINK, link)})
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}

    def cat(x):
        n = (x["name"] + " " + x["title"]).lower()
        for label, keys in (("Stack Exchange Q&A", ("stackexchange",)), ("LibreTexts", ("libretexts",)), ("Medical and health", ("medlineplus", "nhs", "medicine", "medical", "pathology", "military", "travelers")),
                            ("Wikipedia and wikis", ("wikipedia", "wikibooks", "wikiversity")), ("Developer docs", ("devdocs", "freecodecamp")),
                            ("Books and talks", ("gutenberg", "ted")), ("Home, cooking and prepping", ("cook", "prep", "food", "foss", "diy", "ifixit", "zimgit"))):
            if any(k in n for k in keys):
                return label
        return "Other"
    cats = {}
    for x in libs:
        c = cats.setdefault(cat(x), {"name": cat(x), "count": 0, "articles": 0})
        c["count"] += 1
        c["articles"] += x["articles"]
    biggest = sorted(libs, key=lambda x: -x["articles"])[:6]
    return {"up": True, "libraries": len(libs), "articles": sum(x["articles"] for x in libs), "media": sum(x["media"] for x in libs),
            "newest": max((x["updated"] for x in libs), default=""), "categories": sorted(cats.values(), key=lambda c: -c["articles"]),
            "top": [{"title": x["title"], "articles": x["articles"], "url": x["url"]} for x in biggest],
            "all": [{"title": x["title"], "articles": x["articles"], "url": x["url"], "updated": x["updated"]} for x in sorted(libs, key=lambda x: x["title"].lower())]}


def _kolibri():
    try:
        info = _get("http://%s:8310/api/public/info/" % HOST)[2]
        fac = (_get("http://%s:8310/api/auth/facility/" % HOST)[2] or [{}])[0]
        try:
            channels = len(_get("http://%s:8310/api/content/channel/" % HOST)[2])
        except Exception:
            channels = 0
        return {"up": True, "version": info.get("kolibri_version", ""), "device": info.get("device_name", ""), "facility": fac.get("name", ""),
                "users": fac.get("num_users", 0), "learners": fac.get("num_learners", 0), "classrooms": fac.get("num_classrooms", 0), "channels": channels,
                "signup": bool((fac.get("dataset") or {}).get("learner_can_sign_up")), "synced": bool(fac.get("last_successful_sync"))}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def _nomad():
    try:
        svcs = _get("http://%s:8500/api/system/services" % HOST)[2]
        info = _get("http://%s:8500/api/system/info" % HOST, timeout=12)[2]
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}
    mem = info.get("mem", {})
    total = float(mem.get("total") or 1)
    fs = next((f for f in info.get("fsSize", []) if f.get("mount") == "/app/storage"), {})
    root = next((f for f in info.get("fsSize", []) if f.get("mount") == "/"), {})
    services = [{"name": s.get("friendly_name") or s.get("service_name"), "by": s.get("powered_by") or "", "running": s.get("status") == "running",
                 "status": s.get("status") or "", "update": s.get("available_update_version") or "", "image": (s.get("container_image") or "").split("/")[-1],
                 "category": s.get("category") or ""} for s in svcs if s.get("installed")]
    return {"up": True, "services": services, "running": sum(1 for s in services if s["running"]), "updates": sum(1 for s in services if s["update"]),
            "cpu_brand": (info.get("cpu", {}).get("brand") or "").replace("Core™ ", ""), "cores": info.get("cpu", {}).get("cores", 0),
            "load_pct": int(round(float(info.get("currentLoad", {}).get("currentLoad") or 0))),
            "mem_pct": int(round(100 - float(mem.get("available") or 0) / total * 100)), "mem_gb": round(total / 2**30),
            "swap_pct": int(round(float(mem.get("swapused") or 0) / float(mem.get("swaptotal") or 1) * 100)),
            "uptime_d": round(float((info.get("uptime") or {}).get("uptime") or 0) / 86400, 1), "kernel": (info.get("os") or {}).get("kernel", ""),
            "storage_pct": int(round(float(fs.get("use") or 0))), "storage_tb": round(float(fs.get("size") or 0) / 1e12, 1),
            "storage_used_tb": round(float(fs.get("used") or 0) / 1e12, 1), "root_pct": int(round(float(root.get("use") or 0))),
            "gpu_ok": bool((info.get("gpuHealth") or {}).get("ollamaGpuAccessible"))}


def _searxng():
    try:
        d = _get("http://%s:8888/config" % HOST, timeout=15)[2]
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}
    engines = d.get("engines", [])
    on = [e for e in engines if e.get("enabled")]
    cats = {}
    for e in on:
        for c in e.get("categories", []):
            cats[c] = cats.get(c, 0) + 1
    plugins = [p.get("name") for p in d.get("plugins", []) if p.get("enabled")]
    safe = {0: "off", 1: "moderate", 2: "strict"}.get(d.get("safe_search"), str(d.get("safe_search")))
    return {"up": True, "engines": len(engines), "enabled": len(on), "categories": [{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda kv: -kv[1])[:9]],
            "plugins": plugins[:10], "version": str(d.get("version", "")).split("+")[0], "name": d.get("instance_name", ""), "safe": safe,
            "autocomplete": d.get("autocomplete") or "off", "locale": d.get("default_locale") or "auto",
            "top_engines": [{"name": e["name"], "shortcut": e.get("shortcut", "")} for e in on if "general" in e.get("categories", [])][:14]}


def _flatnotes():
    try:
        notes = _get("http://%s:8200/api/search?term=*&sort=lastModified&order=desc&limit=500" % HOST)[2]
        tags = _get("http://%s:8200/api/tags" % HOST)[2]
        notes = notes if isinstance(notes, list) else []
        now = time.time()
        mods = [float(n.get("lastModified") or 0) for n in notes]
        return {"up": True, "notes": len(notes), "tags": len(tags) if isinstance(tags, list) else 0,
                "last_h": int((now - max(mods)) / 3600) if mods else -1, "week": sum(1 for m in mods if m > now - 7 * 86400)}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def _stirling():
    try:
        st = _get("http://%s:8400/api/v1/info/status" % HOST)[2]
        up = _get("http://%s:8400/api/v1/info/uptime" % HOST, raw=True)[2].decode().strip()
        av = _get("http://%s:8400/api/v1/config/endpoints-availability" % HOST, timeout=10)[2]
        total = len(av) if isinstance(av, dict) else 0
        on = sum(1 for v in av.values() if v.get("enabled")) if isinstance(av, dict) else 0
        return {"up": st.get("status") == "UP", "version": st.get("version", ""), "uptime": up, "tools": total, "enabled": on}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def _homebox():
    try:
        d = _get("http://%s:8470/api/v1/status" % HOST)[2]
        cur = (d.get("build") or {}).get("version", "")
        latest = (d.get("latest") or {}).get("version", "")
        return {"up": bool(d.get("health")), "version": cur, "latest": latest, "update": bool(latest) and latest != cur,
                "released": ((d.get("latest") or {}).get("date") or "")[:10], "message": d.get("message", "")}
    except Exception as exc:
        return {"up": False, "err": str(exc)[:80]}


def cards():
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(f) for k, f in (("kiwix", _kiwix), ("kolibri", _kolibri), ("nomad", _nomad), ("searxng", _searxng), ("flatnotes", _flatnotes),
                                             ("stirling", _stirling), ("homebox", _homebox), ("containers", _container_info))}
        out = {}
        for k, fut in futs.items():
            try:
                out[k] = fut.result(timeout=40)
            except Exception as exc:
                out[k] = {"up": False, "err": str(exc)[:80]}
    ctr = out.pop("containers", {}) or {}
    by = {"stirling": "Stirling-Tools", "flatnotes": "FlatNotes", "homebox": "Homebox", "kiwix": "Kiwix", "kolibri": "Kolibri"}
    services = (out.get("nomad") or {}).get("services", [])
    for key, powered in by.items():
        svc = next((s for s in services if s.get("by") == powered), None)
        if svc and isinstance(out.get(key), dict):
            out[key]["update"] = svc.get("update", "")
    for k, v in out.items():
        v["ctr"] = ctr.get(k, {"found": False})
    out["remote"] = {"ctr_picard": ctr.get("picard", {"found": False}), "ctr_firefox": ctr.get("firefox", {"found": False}), "ctr_vault": ctr.get("vaultwarden", {"found": False})}
    return out


DEV_KEYS = ("cyberchef", "ittools", "excalidraw", "dozzle", "termix")      # shown on the Dev page instead of the Tools page


def build():
    with ThreadPoolExecutor(max_workers=8) as ex:
        all_tiles = list(ex.map(_tile, TILES))
        p, bk = ex.submit(paperless), ex.submit(bookstack)
        tiles = [x for x in all_tiles if x["key"] not in DEV_KEYS]
        dev = sorted([x for x in all_tiles if x["key"] in DEV_KEYS], key=lambda x: DEV_KEYS.index(x["key"]))
        c = ex.submit(cards)
        out = {"at": int(time.time()), "tiles": tiles, "dev_tiles": dev, "paperless": p.result(), "bookstack": bk.result(), "cards": c.result()}
    out["up"] = sum(1 for t in tiles if t["up"])
    out["down"] = sum(1 for t in tiles if not t["up"])
    return out
