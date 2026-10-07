"""VPN control bridge for the Glance Networking page (stdlib only; imported by app.py).

  summary()       : every device managed by wbs-vpn-dashboard (status, current country, last result), shaped for the page
  command(body)   : forward ONE allow-listed command (connect / disconnect / killswitch / tailscale / dns_mode (pihole_dns is the legacy on/off)) to a device
  origin_ok(...)  : browser-CSRF guard for the write endpoint (the page must come from this host)

The panel's API key lives only in this container (VPN_KEY); the browser never sees it. wbs-vpn-dashboard is the source of truth:
https://github.com/WB2024/WBs-VPN-Dashboard
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 8
CACHE_SECONDS = 2
_cache = {"at": 0.0, "data": None}

ID_RE = re.compile(r"[0-9a-f]{8}")
COUNTRY_RE = re.compile(r"[A-Za-z][A-Za-z_ ]{1,38}")
TYPES = {"connect", "disconnect", "killswitch", "pihole_dns", "tailscale", "dns_mode"}
DNS_MODES = ("nord", "split", "pihole")
TOGGLES = {"killswitch", "pihole_dns", "tailscale"}


def _env(n, d=""):
    return os.environ.get(n, d)


def configured():
    return bool(_env("VPN_URL") and _env("VPN_KEY"))


def _call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_env("VPN_URL").rstrip("/") + path, data=data, method=method,
                                 headers={"X-API-Key": _env("VPN_KEY"), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", "")
        except Exception:
            msg = ""
        raise ValueError(msg or "VPN panel returned HTTP %d" % e.code)


def summary():
    if not configured():
        raise RuntimeError("VPN_URL / VPN_KEY not set")
    if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    raw = _call("GET", "/api/v1/devices")
    now = int(time.time())
    out = []
    for d in raw.get("devices", []):
        s = d.get("status") or {}
        last = (d.get("results") or [None])[0]
        out.append({
            "id": d["id"], "name": d["name"], "online": bool(d.get("online")),
            "seen_s": (now - d["last_seen"]) if d.get("last_seen") else None,
            "nord": bool(s.get("nord_installed")), "connected": bool(s.get("connected")),
            "country": s.get("country", ""), "city": s.get("city", ""), "ip": s.get("ip", ""),
            "kill_switch": bool(s.get("kill_switch")), "pihole_dns": bool(s.get("pihole_dns")),
            "dns_mode": s.get("dns_mode") or ("pihole" if s.get("pihole_dns") else "nord"),
            "tailscale": s.get("tailscale", "absent"), "error": s.get("error", ""),
            "busy": bool(d.get("inflight") or d.get("pending")),
            "last": {"ok": bool(last["ok"]), "type": last["type"], "message": last["message"], "age_s": now - last["at"]} if last else None,
        })
    out.sort(key=lambda x: (not x["online"], x["name"].lower()))
    data = {"at": now, "total": len(out), "online": sum(1 for x in out if x["online"]),
            "connected": sum(1 for x in out if x["connected"]), "countries": raw.get("countries", []), "devices": out}
    _cache.update(at=time.time(), data=data)
    return data


def command(body):
    """Validate against the allow-list, then queue it on the panel. Returns the panel's reply."""
    if not configured():
        raise RuntimeError("VPN_URL / VPN_KEY not set")
    dev = str(body.get("id", ""))
    typ = str(body.get("type", ""))
    if not ID_RE.fullmatch(dev):
        raise ValueError("bad device id")
    if typ not in TYPES:
        raise ValueError("unknown command")
    cmd = {"type": typ}
    if typ == "connect":
        country = str(body.get("country", ""))
        if not COUNTRY_RE.fullmatch(country):
            raise ValueError("bad country")
        cmd["country"] = country
    elif typ in TOGGLES:
        if body.get("value") not in ("on", "off"):
            raise ValueError("value must be on or off")
        cmd["value"] = body["value"]
    elif typ == "dns_mode":
        if body.get("value") not in DNS_MODES:
            raise ValueError("dns mode must be nord, split or pihole")
        cmd["value"] = body["value"]
    res = _call("POST", "/api/v1/devices/%s/command" % urllib.parse.quote(dev), cmd)
    _cache["data"] = None          # show the queued state on the next poll
    return res


def origin_ok(origin, host_header):
    """Allow a write only when the browser's Origin is this same host (any port: Glance is :3002, this service :3005),
    or one listed in VPN_ORIGINS. A missing Origin means a non-browser client (curl, the server itself)."""
    if not origin:
        return True
    try:
        o = urllib.parse.urlparse(origin).hostname or ""
    except ValueError:
        return False
    h = (host_header or "").split(":")[0].lower()
    extra = {x.strip().lower() for x in _env("VPN_ORIGINS").split(",") if x.strip()}
    return o.lower() == h or o.lower() in extra
