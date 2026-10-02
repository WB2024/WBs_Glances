#!/usr/bin/env python3
"""glance host lister: read-only list of a Docker host's containers for the Glance dashboard (stdlib only).

Why not a Docker socket proxy: container *inspect* output contains environment variables (secrets). This service only
ever calls GET /containers/json and /version, and returns a short allow-list of fields (name, image, state, status,
stack, public ports). It never returns env vars, mounts, labels or commands, and needs a bearer token.
"""
import hmac
import http.client
import json
import os
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOCK = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
TOKEN = os.environ.get("TOKEN", "")
PORT = int(os.environ.get("PORT", "27974"))
HOSTNAME = os.environ.get("HOST_LABEL", socket.gethostname())


class _Unix(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost")
        self.path = path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(self.path)
        self.sock = s


def docker_get(path):
    c = _Unix(SOCK)
    try:
        c.request("GET", path)
        r = c.getresponse()
        data = r.read()
        if r.status != 200:
            raise RuntimeError("docker api %s -> %s" % (path, r.status))
        return json.loads(data.decode("utf-8"))
    finally:
        c.close()


def cpu_temp():
    """Hottest CPU temperature in C from the kernel's hwmon sensors, or None (e.g. LXC containers have no sensors)."""
    best = None
    base = "/sys/class/hwmon"
    try:
        for h in os.listdir(base):
            try:
                with open(os.path.join(base, h, "name")) as f:
                    name = f.read().strip()
            except OSError:
                continue
            if name not in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
                continue
            for fn in os.listdir(os.path.join(base, h)):
                if fn.startswith("temp") and fn.endswith("_input"):
                    try:
                        with open(os.path.join(base, h, fn)) as f:
                            v = int(f.read().strip()) / 1000.0
                    except (OSError, ValueError):
                        continue
                    if 0 < v < 150 and (best is None or v > best):
                        best = v
    except OSError:
        return None
    return round(best, 1) if best is not None else None


NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def one_stats(name):
    """CPU % and memory of one running container (a single stats sample). Returns only numbers, never environment or config."""
    d = docker_get("/containers/%s/stats?stream=false" % name)
    cpu, pre = d.get("cpu_stats") or {}, d.get("precpu_stats") or {}
    dc = (cpu.get("cpu_usage") or {}).get("total_usage", 0) - (pre.get("cpu_usage") or {}).get("total_usage", 0)
    ds = (cpu.get("system_cpu_usage") or 0) - (pre.get("system_cpu_usage") or 0)
    ncpu = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
    pct = round(dc / ds * ncpu * 100, 1) if ds > 0 and dc >= 0 else 0.0
    mem = d.get("memory_stats") or {}
    used = mem.get("usage", 0) - ((mem.get("stats") or {}).get("inactive_file") or (mem.get("stats") or {}).get("cache") or 0)
    return {"name": name, "cpu_pct": pct, "mem_mb": int(max(used, 0) / 2**20), "mem_limit_mb": int((mem.get("limit") or 0) / 2**20)}


def stats(names):
    names = [n for n in names if NAME_RE.fullmatch(n)][:24]
    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n, fut in [(n, ex.submit(one_stats, n)) for n in names]:
            try:
                out.append(fut.result(timeout=20))
            except Exception:
                out.append({"name": n, "cpu_pct": -1, "mem_mb": -1})
    return {"host": HOSTNAME, "stats": out}


def snapshot():
    out = []
    for c in docker_get("/containers/json?all=1"):
        labels = c.get("Labels") or {}
        status = c.get("Status") or ""
        health = "healthy" if "(healthy)" in status else "unhealthy" if "(unhealthy)" in status else ""
        ports = sorted({p["PublicPort"] for p in (c.get("Ports") or []) if p.get("PublicPort")})
        out.append({
            "name": (c.get("Names") or ["?"])[0].lstrip("/"),
            "image": (c.get("Image") or "").split("@")[0],
            "state": c.get("State") or "",
            "status": status,
            "health": health,
            "stack": labels.get("com.docker.compose.project", ""),
            "ports": ports,
        })
    out.sort(key=lambda x: (x["stack"] or "~", x["name"]))
    running = sum(1 for x in out if x["state"] == "running")
    return {"host": HOSTNAME, "docker": docker_get("/version").get("Version", ""),
            "running": running, "stopped": len(out) - running, "cpu_temp_c": cpu_temp(), "containers": out}


class H(BaseHTTPRequestHandler):
    server_version = "glance-lister/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/health":
            return self._send(200, {"ok": True})
        if path not in ("/containers", "/stats"):
            return self._send(404, {"error": "not found"})
        auth = self.headers.get("Authorization", "")
        given = auth[7:] if auth.lower().startswith("bearer ") else self.headers.get("X-Token", "")
        if not hmac.compare_digest(given.encode(), TOKEN.encode()):
            return self._send(401, {"error": "unauthorized"})
        try:
            if path == "/stats":
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                names = (re.search(r"(?:^|&)names=([^&]*)", q) or [None, ""])[1].split(",")
                return self._send(200, stats([n for n in names if n]))
            self._send(200, snapshot())
        except Exception as exc:
            print("error:", exc, flush=True)
            self._send(502, {"error": "docker unavailable"})

    do_POST = do_PUT = do_DELETE = do_PATCH = lambda self: self._send(405, {"error": "read-only"})


if __name__ == "__main__":
    if len(TOKEN) < 16:
        sys.exit("TOKEN must be set (16+ chars)")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
