"""Remote management bridge for the Glance 'Remote' page (stdlib only; imported by app.py).

  hosts()   : the hosts defined in Termix (the single source of truth), shaped for the page: capabilities (files / docker / tunnels /
              metrics / tmux), Termix's own online status (TCP probe only where Termix has no status) and recent-use from its audit log.
  metrics(id): live CPU / RAM / disk / load / uptime for one host, from Termix (cached 10 s).

TERMIX_API_KEY stays in this container and is only ever sent to Termix; the browser gets names, ids, kinds and addresses, never credentials.
Adding a host in Termix adds it to the page within about 30 seconds, with no edit here.
"""
import json
import os
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 8
CACHE_SECONDS = 15
_cache = {"at": 0.0, "data": None}
_mcache = {}


def _env(n, d=""):
    return os.environ.get(n, d)


def configured():
    return bool(_env("TERMIX_URL") and _env("TERMIX_API_KEY"))


def _kind(h):
    """desktop = VNC/RDP hosts, ssh = hosts with a terminal; anything else is not listed."""
    t = h.get("connectionType")
    if t in ("vnc", "rdp"):
        return "desktop"
    if t == "ssh" and h.get("enableTerminal") is not False:
        return "ssh"
    return None


def _reachable(addr, port):
    """True/False for a TCP connect; None when the name only resolves inside another Docker network (shown as unknown)."""
    try:
        with socket.create_connection((addr, int(port)), timeout=1.2):
            return True
    except socket.gaierror:
        return None
    except (OSError, ValueError, TypeError):
        return False


def _fetch(path="/host/db/host"):
    req = urllib.request.Request(_env("TERMIX_URL").rstrip("/") + path,
                                 headers={"Authorization": "Bearer " + _env("TERMIX_API_KEY")})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("Termix rejected the API key")
        if e.code == 404:
            return None
        raise ValueError("Termix returned HTTP %d" % e.code)


def _opt(path):
    """Optional Termix data: a failure here must never take the host list down."""
    try:
        return _fetch(path)
    except (ValueError, urllib.error.URLError, OSError):
        return None


def hosts():
    if not configured():
        raise RuntimeError("TERMIX_URL / TERMIX_API_KEY not set")
    if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_raw, f_st, f_au = ex.submit(_fetch), ex.submit(_opt, "/status"), ex.submit(_opt, "/audit-logs")
        try:
            raw = f_raw.result()
        except (ValueError, urllib.error.URLError, OSError):
            if _cache["data"] is not None:       # Termix hiccup: keep serving the last good list, marked stale
                return dict(_cache["data"], stale=True)
            raise
        status, audit = f_st.result(), f_au.result()
    status = status if isinstance(status, dict) else {}
    recent = {}
    for e in (audit or {}).get("logs", []) if isinstance(audit, dict) else []:
        if str(e.get("action", "")).endswith("_connect") and e.get("success") is not False and e.get("resourceId") is not None:
            r = recent.setdefault(str(e["resourceId"]), {"last": "", "n": 0})
            r["n"] += 1
            r["last"] = max(r["last"], str(e.get("timestamp") or ""))
    rows = []
    for h in raw if isinstance(raw, list) else []:
        kind = _kind(h)
        if not kind or h.get("id") is None:
            continue
        sc = h.get("statsConfig") or {}
        st = status.get(str(h["id"])) or {}
        up = None if not st else (st.get("status") == "online")
        rows.append({"id": int(h["id"]), "name": str(h.get("name") or h.get("ip") or h["id"])[:80], "kind": kind,
                     "protocol": h.get("connectionType"), "address": str(h.get("ip") or ""), "port": h.get("port"),
                     "folder": str(h.get("folder") or "")[:40], "up": up, "pin": bool(h.get("pin")),
                     "caps": {"files": bool(h.get("enableFileManager")), "docker": bool(h.get("enableDocker")),
                              "tunnels": bool(h.get("enableTunnel")), "tmux": bool(h.get("enableTmuxMonitor")),
                              "metrics": bool(sc.get("metricsEnabled")) and kind == "ssh"},
                     "recent": recent.get(str(h["id"]), {}).get("last", ""), "uses": recent.get(str(h["id"]), {}).get("n", 0)})
    todo = [r for r in rows if r["up"] is None]          # no Termix status: fall back to a TCP probe
    if todo:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for row, up in zip(todo, ex.map(lambda r: _reachable(r["address"], r["port"]), todo)):
                row["up"] = up
    rows.sort(key=lambda r: (r["kind"] != "desktop", r["folder"].lower() == "", r["folder"].lower(), r["name"].lower()))
    data = {"at": int(time.time()), "termix_port": int(_env("REMOTE_TERMIX_PORT", "8080")),
            "ssh": sum(1 for r in rows if r["kind"] == "ssh"), "desktop": sum(1 for r in rows if r["kind"] == "desktop"), "hosts": rows}
    _cache.update(at=time.time(), data=data)
    return data


def metrics(host_id):
    """Compact live stats for one SSH host. Returns {} when Termix has none for it (not collected / offline)."""
    host_id = int(host_id)
    if not configured():
        raise RuntimeError("TERMIX_URL / TERMIX_API_KEY not set")
    c = _mcache.get(host_id)
    if c and time.time() - c[0] < 10:
        return c[1]
    m = _fetch("/metrics/%d" % host_id)
    out = {}
    if isinstance(m, dict) and m:
        g = lambda k: m.get(k) if isinstance(m.get(k), dict) else {}
        temp = g("temperature")
        out = {"cpu": g("cpu").get("percent"), "cores": g("cpu").get("cores"), "load": g("cpu").get("load"),
               "mem": g("memory").get("percent"), "mem_used": g("memory").get("usedGiB"), "mem_total": g("memory").get("totalGiB"),
               "disk": g("disk").get("percent"), "disk_used": g("disk").get("usedHuman"), "disk_total": g("disk").get("totalHuman"),
               "uptime": g("uptime").get("formatted"), "os": g("system").get("os"), "kernel": g("system").get("kernel"),
               "temp": temp.get("highestCelsius"), "procs": g("processes").get("total")}
    if len(_mcache) > 64:
        _mcache.clear()
    _mcache[host_id] = (time.time(), out)
    return out
