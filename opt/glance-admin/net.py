"""Networking summaries for the Glance Networking page (stdlib only; imported by app.py).

  tailscale() : every device in the tailnet via a read-only OAuth client (token exchanged and cached ~1 h)
  npm()       : every Nginx Proxy Manager proxy host, certificates, plus a TCP reachability check of each backend,
                via the view-only 'readonly' NPM user
Credentials stay in this container; only shaped data is returned.
"""
import datetime
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 20
_ts = {"token": "", "exp": 0}
_npm = {"token": "", "exp": 0}


def _env(n, d=""):
    return os.environ.get(n, d)


def _iso(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ----------------------------------------------------------------------------- tailscale
def _ts_token():
    if _ts["token"] and time.time() < _ts["exp"] - 120:
        return _ts["token"]
    body = urllib.parse.urlencode({"client_id": _env("TAILSCALE_OAUTH_ID"), "client_secret": _env("TAILSCALE_OAUTH_SECRET"),
                                   "grant_type": "client_credentials"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://api.tailscale.com/api/v2/oauth/token", data=body), timeout=TIMEOUT) as r:
        d = json.loads(r.read().decode())
    _ts.update(token=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)))
    return _ts["token"]


def tailscale():
    req = urllib.request.Request("https://api.tailscale.com/api/v2/tailnet/-/devices?fields=all",
                                 headers={"Authorization": "Bearer " + _ts_token()})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        devs = json.loads(r.read().decode())["devices"]
    now = time.time()
    out = []
    for d in devs:
        seen = _iso(d["lastSeen"]) if d.get("lastSeen") else None
        exp_days = None
        if d.get("expires") and not d.get("keyExpiryDisabled"):
            exp_days = int((_iso(d["expires"]) - now) / 86400)
        online = bool(d.get("connectedToControl"))
        out.append({
            "name": d.get("hostname") or d.get("name", "?"), "os": d.get("os", ""), "ip": (d.get("addresses") or [""])[0],
            "online": online,
            "seen_h": 0 if online else (int((now - seen) / 3600) if seen else None),
            "expires_days": exp_days, "key_expired": exp_days is not None and exp_days < 0,
            "expires_soon": exp_days is not None and 0 <= exp_days < 30,
            "update": bool(d.get("updateAvailable")), "tags": ", ".join((d.get("tags") or [])).replace("tag:", ""),
            "ssh": bool(d.get("sshEnabled")), "routes": len(d.get("enabledRoutes") or [])})
    out.sort(key=lambda x: (not x["online"], x["seen_h"] if x["seen_h"] is not None else 10**9, x["name"].lower()))
    return {"at": int(now), "total": len(out), "online": sum(1 for x in out if x["online"]),
            "offline": sum(1 for x in out if not x["online"]), "expired": sum(1 for x in out if x["key_expired"]),
            "updates": sum(1 for x in out if x["update"]), "devices": out}


# ----------------------------------------------------------------------------- nginx proxy manager
def _npm_get(path, retry=True):
    base = _env("NPM_URL", "http://host.docker.internal:81").rstrip("/") + "/api"
    if not _npm["token"] or time.time() > _npm["exp"] - 300:
        body = json.dumps({"identity": _env("NPM_USER"), "secret": _env("NPM_PASS")}).encode()
        req = urllib.request.Request(base + "/tokens", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode())
        _npm["token"] = d["token"]
        try:
            _npm["exp"] = _iso(d["expires"])
        except Exception:
            _npm["exp"] = time.time() + 3600
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers={"Authorization": "Bearer " + _npm["token"]}), timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            _npm["token"] = ""
            return _npm_get(path, retry=False)
        raise


def _reachable(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=1.5):
            return True
    except OSError:
        return False


def npm():
    hosts = _npm_get("/nginx/proxy-hosts?expand=certificate,access_list")
    certs = _npm_get("/nginx/certificates")
    targets = sorted({(h["forward_host"], h["forward_port"]) for h in hosts})
    with ThreadPoolExecutor(max_workers=12) as ex:
        up = dict(zip(targets, ex.map(lambda t: _reachable(*t), targets)))
    now = time.time()
    rows = []
    for h in hosts:
        names = h.get("domain_names") or ["?"]
        rows.append({"domain": names[0], "extra": max(0, len(names) - 1),
                     "target": "%s://%s:%s" % (h["forward_scheme"], h["forward_host"], h["forward_port"]),
                     "enabled": bool(h.get("enabled")), "online": bool((h.get("meta") or {}).get("nginx_online", True)),
                     "backend_up": up[(h["forward_host"], h["forward_port"])], "ssl": bool(h.get("certificate_id")),
                     "ssl_forced": bool(h.get("ssl_forced")), "ws": bool(h.get("allow_websocket_upgrade")),
                     "auth": bool(h.get("access_list_id")), "cert_id": h.get("certificate_id") or 0})
    rows.sort(key=lambda r: (r["backend_up"], r["domain"]))      # problems first
    certs_out = []
    for c in certs:
        exp = _iso(c["expires_on"].replace(" ", "T") + ("Z" if not c["expires_on"].endswith("Z") and "+" not in c["expires_on"] else "")) if c.get("expires_on") else None
        certs_out.append({"name": c.get("nice_name") or ",".join(c.get("domain_names") or []), "provider": c.get("provider", ""),
                          "days": int((exp - now) / 86400) if exp else None, "used_by": sum(1 for r in rows if r["cert_id"] == c.get("id"))})
    return {"at": int(now), "total": len(rows), "down": sum(1 for r in rows if not r["backend_up"]),
            "disabled": sum(1 for r in rows if not r["enabled"]), "errors": sum(1 for r in rows if not r["online"]),
            "redirections": len(_npm_get("/nginx/redirection-hosts")), "streams": len(_npm_get("/nginx/streams")),
            "certs": certs_out, "hosts": rows}
