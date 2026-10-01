"""Infra summary for the Glance Infra page (stdlib only; imported by app.py).

One cached JSON document built every REFRESH seconds from:
  * the Proxmox API (nodes, LXC/VM guests, failed tasks)         - PROXMOX_USER / PROXMOX_PASSWORD (API token)
  * the Proxmox Backup Server API (datastores, groups, tasks)     - PBS_PASSWORD (API token)
  * per-host Glance agent (CPU/mem/disks) + glance-lister (containers, CPU temp), each with its own bearer token
Nothing secret is ever returned; templates only see shaped numbers and names.
"""
import json
import re
import os
import ssl
import time
import urllib.request

_CTX = ssl._create_unverified_context()      # Proxmox / PBS use self-signed certificates on the LAN
TIMEOUT = 20


def _get(url, headers=None, tls=False):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX if tls else None) as r:
        return json.loads(r.read().decode("utf-8"))


# Proxmox/PBS list a task as "failed" for warnings and for console sessions that simply ended; neither is an outage.
NOISE_TYPES = {"vncshell", "vncproxy", "spiceshell", "aptupdate"}


def _real_failure(t):
    return t.get("worker_type", t.get("type", "")) not in NOISE_TYPES and not str(t.get("status", "")).startswith("WARNINGS")


def _pct(a, b):
    return int(round(float(a) / float(b) * 100)) if b else 0


def _env(name, default=""):
    return os.environ.get(name, default)


# What each physical disk is for (static: edit when disks change). Keys are (node, device path). No private service names here:
# this text is shown on the unlocked Infra page.
ROLES = {
    ("pve4", "/dev/sda"): ("/mnt/wd-4tb", "Proxmox dir storage 'wd-4tb': templates, dumps; nightly copy of the devuan 4 TB drive"),
    ("pve4", "/dev/sdb"): ("/mnt/sdb1", "backup-20tb pool member (mergerfs): nightly rsync of Main20TB"),
    ("pve4", "/dev/sdc"): ("/mnt/sdc1", "backup-20tb pool member (mergerfs): nightly rsync of Main20TB"),
    ("pve4", "/dev/sdd"): ("/mnt/Main20TB", "Main20TB: the main media pool; bind-mounted into CT103 + CT104, NFS/SMB export"),
    ("pve4", "/dev/sde"): ("/mnt/pbs-nfs", "PBS datastore: NFS export to the Backup Server (.250)"),
    ("pve4", "/dev/sdf"): ("/mnt/st-500gb", "misc pool member (mergerfs /mnt/misc): scratch + downloads, NFS export"),
    ("pve4", "/dev/sdg"): ("/mnt/sdg1", "backup-20tb pool member (mergerfs): nightly rsync of Main20TB"),
    ("pve4", "/dev/sdh"): ("/mnt/hgst-1tb", "misc pool member (mergerfs /mnt/misc): scratch + downloads, NFS export"),
    ("pve4", "/dev/sdi"): ("boot + root", "Proxmox boot + root (LVM) and half of the local-lvm pool"),
    ("pve4", "/dev/sdj"): ("local-lvm", "local-lvm thin pool: CT103 + CT104 root disks"),
    ("pve4", "/dev/sdk"): ("not mounted", "USB stick, not in use"),
    ("pve2", "/dev/sda"): ("boot + root", "Proxmox boot + root; CT200 automation lives here"),
}
# devuan disks as reported by its Glance agent (name -> where / what)
DEVUAN_ROLES = {
    "Root disk": ("/", "OS + Docker data (SSD)"),
    "1 TB drive": ("/srv/1tb", "btrfs pool of two 1 TB drives: private libraries and downloads"),
    "4 TB drive": ("/srv/4tb", "ext4: camera recordings, downloads, shared to pve4 over NFS (nightly copy to wd-4tb)"),
}


def pve_disks(node, ip, auth):
    """Physical disks as Proxmox sees them (model, size, SMART health, SSD wear), merged with the ROLES text."""
    out = []
    try:
        rows = _get("https://%s:8006/api2/json/nodes/%s/disks/list" % (ip, node), auth, tls=True)["data"]
    except Exception:
        return out
    for d in sorted(rows, key=lambda x: x.get("devpath", "")):
        mount, role = ROLES.get((node, d.get("devpath")), ("", ""))
        wear = d.get("wearout")
        out.append({"dev": d.get("devpath", ""), "model": str(d.get("model", "")).replace("_", " "), "size_gb": round(d.get("size", 0) / 1e9),
                    "type": d.get("type", ""), "fs": d.get("used", ""), "health": d.get("health", ""),
                    "wear_left": wear if isinstance(wear, int) else None, "mount": mount, "role": role})
    return out


def pve_storage(node, ip, auth):
    try:
        rows = _get("https://%s:8006/api2/json/nodes/%s/storage" % (ip, node), auth, tls=True)["data"]
    except Exception:
        return []
    return [{"name": s["storage"], "type": s.get("type", ""), "used_gb": round(s.get("used", 0) / 2**30), "total_gb": round(s.get("total", 0) / 2**30),
             "pct": _pct(s.get("used", 0), s.get("total", 0))} for s in rows if s.get("active") and s.get("total")]


def pve_node(name, ip):
    auth = {"Authorization": "PVEAPIToken=%s=%s" % (_env("PROXMOX_USER"), _env("PROXMOX_PASSWORD"))}
    base = "https://%s:8006/api2/json/nodes/%s" % (ip, name)
    n = {"name": name, "ip": ip, "ok": False, "guests": []}
    try:
        s = _get(base + "/status", auth, tls=True)["data"]
        n.update(ok=True, cpu_pct=int(round(s["cpu"] * 100)), cpus=s["cpuinfo"]["cpus"],
                 mem_used_gb=round(s["memory"]["used"] / 2**30, 1), mem_total_gb=round(s["memory"]["total"] / 2**30, 1),
                 mem_pct=_pct(s["memory"]["used"], s["memory"]["total"]), load=round(float(s["loadavg"][0]), 2),
                 rootfs_pct=_pct(s["rootfs"]["used"], s["rootfs"]["total"]), uptime_d=round(s["uptime"] / 86400, 1),
                 pve=s["pveversion"].split("/")[1] if "/" in s["pveversion"] else s["pveversion"],
                 kernel=s["current-kernel"]["release"])
    except Exception as exc:
        n["err"] = str(exc)[:120]
        return n
    for kind in ("lxc", "qemu"):
        try:
            for g in _get("%s/%s" % (base, kind), auth, tls=True)["data"]:
                n["guests"].append({
                    "vmid": g["vmid"], "name": g.get("name", ""), "kind": kind, "status": g.get("status", ""),
                    "cpu_pct": int(round(g.get("cpu", 0) * 100)), "cpus": g.get("cpus"),
                    "mem_mb": int(g.get("mem", 0) / 2**20), "maxmem_mb": int(g.get("maxmem", 0) / 2**20),
                    "mem_pct": _pct(g.get("mem", 0), g.get("maxmem", 0)),
                    "disk_gb": round(g.get("disk", 0) / 2**30, 1), "maxdisk_gb": round(g.get("maxdisk", 0) / 2**30, 1),
                    "disk_pct": _pct(g.get("disk", 0), g.get("maxdisk", 0)), "uptime_d": round(g.get("uptime", 0) / 86400, 1)})
        except Exception:
            pass
    n["guests"].sort(key=lambda g: g["vmid"])
    n["disks"] = pve_disks(name, ip, auth)
    n["storage"] = pve_storage(name, ip, auth) if name == "pve4" else []
    try:
        now = time.time()
        rows = [t for t in _get(base + "/tasks?errors=1&limit=100", auth, tls=True)["data"] if _real_failure(t)]
        week = [t for t in rows if t.get("starttime", 0) >= now - 7 * 86400]
        n["failed_7d"] = len(week)
        n["failed_latest"] = [{"type": t.get("type", ""), "id": t.get("id", ""), "age_h": int((now - t.get("starttime", now)) / 3600),
                               "status": str(t.get("status", ""))[:40]} for t in rows[:3]]
    except Exception:
        n["failed_7d"] = None
        n["failed_latest"] = []
    return n


def pbs():
    auth = {"Authorization": "PBSAPIToken=root@pam!homepage:%s" % _env("PBS_PASSWORD")}
    b = "https://%s:8007/api2/json" % _env("PBS_HOST", "192.168.1.250")
    out = {"ok": False, "datastores": [], "groups": [], "recent": []}
    try:
        st = _get(b + "/nodes/localhost/status", auth, tls=True)["data"]
        out.update(ok=True, mem_pct=_pct(st["memory"]["used"], st["memory"]["total"]), load=round(st["loadavg"][0], 2),
                   uptime_d=round(st["uptime"] / 86400, 1))
        for d in _get(b + "/status/datastore-usage", auth, tls=True)["data"]:
            out["datastores"].append({"store": d["store"], "used_gb": round(d["used"] / 2**30), "total_gb": round(d["total"] / 2**30),
                                      "pct": _pct(d["used"], d["total"])})
        now = time.time()
        if out["datastores"]:
            groups = _get(b + "/admin/datastore/%s/groups" % out["datastores"][0]["store"], auth, tls=True)["data"]
            for g in sorted(groups, key=lambda x: x.get("last-backup", 0), reverse=True):
                age = int((now - g.get("last-backup", 0)) / 3600)
                out["groups"].append({"type": g["backup-type"], "id": g["backup-id"], "count": g.get("backup-count"),
                                      "age_h": age, "stale": age > 72})
        for t in _get(b + "/nodes/localhost/tasks?limit=8&typefilter=backup", auth, tls=True)["data"]:
            out["recent"].append({"name": t.get("worker_id", ""), "status": t.get("status") or "running",
                                  "age_h": int((now - t.get("starttime", now)) / 3600)})
        failed = _get(b + "/nodes/localhost/tasks?limit=100&errors=1", auth, tls=True)["data"]
        out["failed_7d"] = len([t for t in failed if t.get("starttime", 0) >= now - 7 * 86400 and _real_failure(t)])
    except Exception as exc:
        out["err"] = str(exc)[:120]
    return out


# stacks whose names should only show in PIN-locked widgets
PRIVATE_RE = re.compile(os.environ.get("PRIVATE_STACKS", "immich"), re.I)  # privb|priva", re.I)


def docker_host(label, ip, token):
    """Containers (grouped by compose stack) + CPU temp from the glance-lister; CPU/mem/disks from the Glance agent."""
    h = {"label": label, "ip": ip, "ok": False, "stacks": [], "disks": []}
    hdr = {"Authorization": "Bearer " + token}
    try:
        d = _get("http://%s:27974/containers" % ip, hdr)
        h.update(ok=True, docker=d.get("docker"), running=d.get("running"), stopped=d.get("stopped"), temp_c=d.get("cpu_temp_c"))
        stacks = {}
        for c in d.get("containers", []):
            stacks.setdefault(c["stack"] or "(no stack)", []).append(
                {k: c[k] for k in ("name", "image", "state", "health", "ports", "status")})
        h["stacks"] = [{"name": k, "containers": v, "private": bool(PRIVATE_RE.search(k + " " + " ".join(c["name"] for c in v)))}
                       for k, v in sorted(stacks.items())]
    except Exception as exc:
        h["err"] = str(exc)[:120]
    try:
        a = _get("http://%s:27973/api/sysinfo/all" % ip, hdr)
        h["agent"] = {"load_pct": a["cpu"].get("load1_percent"), "mem_pct": a["memory"].get("used_percent"),
                      "mem_used_mb": a["memory"].get("used_mb"), "mem_total_mb": a["memory"].get("total_mb"),
                      "uptime_d": round((time.time() - a.get("boot_time", time.time())) / 86400, 1)}
        for m in a.get("mountpoints", []):
            h["disks"].append({"name": m.get("name") or m["path"], "pct": m.get("used_percent"),
                               "used_gb": round(m.get("used_mb", 0) / 1024), "total_gb": round(m.get("total_mb", 0) / 1024)})
        if a["cpu"].get("temperature_is_available") and not h.get("temp_c"):
            h["temp_c"] = a["cpu"].get("temperature_c")
    except Exception:
        pass
    return h


def build():
    now = int(time.time())
    nodes = [pve_node(n.split("=")[0], n.split("=")[1])
             for n in _env("PVE_NODES", "pve4=192.168.1.60,pve2=192.168.1.59").split(",") if "=" in n]
    guests = {g["vmid"]: g for n in nodes for g in n.get("guests", [])}
    hosts = {}
    spec = [("services", _env("SVC_HOST", "192.168.1.110"), _env("TOKEN_SERVICES"), 103),
            ("jellyfin", _env("JELLY_HOST", "192.168.1.111"), _env("TOKEN_JELLYFIN"), 104),
            ("devuan", _env("DEVUAN_HOST", "192.168.1.106"), _env("TOKEN_DEVUAN"), None)]
    for label, ip, token, vmid in spec:
        h = docker_host(label, ip, token) if token else {"label": label, "ip": ip, "ok": False, "stacks": [], "disks": [], "err": "no token"}
        g = guests.get(vmid) if vmid else None
        if g:   # LXC guests: the agent would report the whole Proxmox host, so CPU / RAM / root disk come from Proxmox
            h["kind"] = "lxc"
            h["vmid"] = vmid
            h["cpu_pct"] = g["cpu_pct"]
            h["mem_pct"], h["mem_used_mb"], h["mem_total_mb"] = g["mem_pct"], g["mem_mb"], g["maxmem_mb"]
            h["uptime_d"] = g["uptime_d"]
            h["disks"] = [{"name": "Root disk", "pct": g["disk_pct"], "used_gb": round(g["disk_gb"]), "total_gb": round(g["maxdisk_gb"])}] + \
                         [d for d in h["disks"] if d["name"] not in ("Root disk",)]
        elif h.get("agent"):
            h["kind"] = "physical"
            h["cpu_pct"] = h["agent"]["load_pct"]
            h["mem_pct"], h["mem_used_mb"], h["mem_total_mb"] = h["agent"]["mem_pct"], h["agent"]["mem_used_mb"], h["agent"]["mem_total_mb"]
            h["uptime_d"] = h["agent"]["uptime_d"]
        if label == "devuan":
            for d in h["disks"]:
                d["mount"], d["role"] = DEVUAN_ROLES.get(d["name"], ("", ""))
        h.pop("agent", None)
        hosts[label] = h
    pb = pbs()
    # backup coverage: does PBS hold a recent backup group for each guest and each Proxmox host?
    age = {(g["type"], str(g["id"])): g["age_h"] for g in pb.get("groups", [])}
    for n in nodes:
        a = age.get(("host", n["name"]))
        n["backed_up"], n["backup_h"] = a is not None, a if a is not None else 0
        for g in n.get("guests", []):
            a = age.get(("ct" if g["kind"] == "lxc" else "vm", str(g["vmid"])))
            g["backed_up"], g["backup_h"] = a is not None, a if a is not None else 0
    # shared 20 TB pool as seen from the jellyfin LXC
    pool = next((d for d in hosts["jellyfin"].get("disks", []) if d["name"] == "Main20TB"), None)
    return {"at": now, "nodes": nodes, "pbs": pb, "hosts": hosts, "main20tb": pool}
