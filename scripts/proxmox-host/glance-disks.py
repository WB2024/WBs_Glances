#!/usr/bin/env python3
"""glance-disks: read-only mount/usage reporter for a Proxmox host (stdlib only).

GET /disks  (Authorization: Bearer <token>)  ->  {"mounts": [{"dev","mount","fstype","size_gb","used_gb","pct","kind"}]}
Returns only device, mount point, filesystem type and capacity numbers. No file names, no paths below the mount point.
Config: GLANCE_DISKS_TOKEN (required), GLANCE_DISKS_PORT (default 27975).
"""
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("GLANCE_DISKS_TOKEN", "")
PORT = int(os.environ.get("GLANCE_DISKS_PORT", "27975"))
KEEP_FS = {"ext4", "ext3", "xfs", "btrfs", "vfat", "exfat", "ntfs", "zfs", "fuse.mergerfs", "nfs", "nfs4", "cifs", "fuseblk"}
SKIP_MOUNT = re.compile(r"^/(proc|sys|dev|run|etc/pve|var/lib/lxcfs|var/lib/pve-cluster|boot/efi)(/|$)|/vzsnap|^/mnt/inspect")


def mounts():
    seen, out = set(), []
    for line in open("/proc/self/mounts", encoding="utf-8", errors="replace"):
        dev, mnt, fs = line.split()[:3]
        mnt = mnt.replace("\\040", " ")
        if fs not in KEEP_FS or SKIP_MOUNT.search(mnt) or (dev, mnt) in seen:
            continue
        seen.add((dev, mnt))
        try:
            st = os.statvfs(mnt)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        if not total:
            continue
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        kind = "pool" if fs == "fuse.mergerfs" else "network" if fs.startswith("nfs") or fs == "cifs" else "local"
        out.append({"dev": dev, "mount": mnt, "fstype": fs, "size_gb": round(total / 2**30, 1), "used_gb": round(used / 2**30, 1),
                    "pct": int(round(used / total * 100)), "kind": kind})
    return sorted(out, key=lambda m: m["mount"])


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if not TOKEN or not hmac.compare_digest(auth, "Bearer " + TOKEN):
            return self._send(401, {"error": "unauthorized"})
        if self.path.split("?")[0] == "/disks":
            return self._send(200, {"mounts": mounts()})
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("GLANCE_DISKS_TOKEN not set")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
