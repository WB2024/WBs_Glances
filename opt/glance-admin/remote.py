"""Remote management bridge for the Glance 'Remote' page (stdlib only; imported by app.py).

  hosts() : the hosts defined in Termix (the single source of truth), shaped for the page, with a quick TCP reachability check.

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
CACHE_SECONDS = 30
_cache = {"at": 0.0, "data": None}


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


def _fetch():
    req = urllib.request.Request(_env("TERMIX_URL").rstrip("/") + "/host/db/host",
                                 headers={"Authorization": "Bearer " + _env("TERMIX_API_KEY")})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError("Termix rejected the API key")
        raise ValueError("Termix returned HTTP %d" % e.code)


def hosts():
    if not configured():
        raise RuntimeError("TERMIX_URL / TERMIX_API_KEY not set")
    if _cache["data"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    raw = _fetch()
    rows = []
    for h in raw if isinstance(raw, list) else []:
        kind = _kind(h)
        if not kind or h.get("id") is None:
            continue
        rows.append({"id": int(h["id"]), "name": str(h.get("name") or h.get("ip") or h["id"])[:80], "kind": kind,
                     "protocol": h.get("connectionType"), "address": str(h.get("ip") or ""), "port": h.get("port"),
                     "folder": str(h.get("folder") or "")[:40]})
    with ThreadPoolExecutor(max_workers=12) as ex:
        for row, up in zip(rows, ex.map(lambda r: _reachable(r["address"], r["port"]), rows)):
            row["up"] = up
    rows.sort(key=lambda r: (r["kind"] != "desktop", r["folder"].lower() == "", r["folder"].lower(), r["name"].lower()))
    data = {"at": int(time.time()), "termix_port": int(_env("REMOTE_TERMIX_PORT", "8080")),
            "ssh": sum(1 for r in rows if r["kind"] == "ssh"), "desktop": sum(1 for r in rows if r["kind"] == "desktop"), "hosts": rows}
    _cache.update(at=time.time(), data=data)
    return data
