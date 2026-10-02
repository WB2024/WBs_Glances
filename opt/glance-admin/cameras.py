"""Camera summary for the Glance Cameras page (stdlib only; imported by app.py).

Reads Frigate's internal API (port 5000 on the automation LXC, no login) and returns a shaped document:
version, uptime, detector speed, CPU, recording storage, per-camera status (fps, recording, usage) and the recent detections.
Cameras are discovered from Frigate's own config, so a camera added in Frigate appears on the dashboard automatically.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

BASE = os.environ.get("FRIGATE_URL", "http://192.168.1.112:5000").rstrip("/")


def _get(path, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"User-Agent": "glance-admin/1"}), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _shape(e, now):
    score = e.get("top_score")
    if score is None:
        score = (e.get("data") or {}).get("top_score")
    end = e.get("end_time")
    return {"id": e["id"], "camera": e.get("camera", ""), "label": e.get("label", ""), "sub": e.get("sub_label") or "",
            "score": int(round(float(score) * 100)) if score else 0, "start": int(e["start_time"]),
            "age_min": max(0, int((now - e["start_time"]) / 60)), "seconds": int(end - e["start_time"]) if end else 0,
            "ongoing": end is None, "clip": bool(e.get("has_clip")), "snapshot": bool(e.get("has_snapshot")), "zones": ", ".join(e.get("zones") or []),
            "description": str((e.get("data") or {}).get("description") or "")[:600]}


EVENT_ID = re.compile(r"\d{9,11}\.\d{1,8}-[a-z0-9]{4,12}")


def events(label="", camera="", after=0, before=0, limit=60, q="", mode="description"):
    """Date/time-range listing, or (with q) Frigate's semantic search ordered by relevance. Every parameter is validated first."""
    now = time.time()
    p = {"limit": max(1, min(int(limit), 200))}
    if label:
        if not re.fullmatch(r"[A-Za-z0-9_ -]{1,30}", label):
            raise ValueError("bad label")
        p["labels"] = label
    if camera:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", camera):
            raise ValueError("bad camera")
        p["cameras"] = camera
    after, before = int(float(after or 0)), int(float(before or 0))
    if after and not (now - 400 * 86400 < after <= now + 86400):
        raise ValueError("bad start time")
    if before and not (now - 400 * 86400 < before <= now + 86400):
        raise ValueError("bad end time")
    if after:
        p["after"] = after
    if before:
        p["before"] = before
    q = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]", " ", q or "")).strip()
    if q:
        if len(q) > 160:
            raise ValueError("search text is too long")
        if mode not in ("description", "thumbnail"):
            raise ValueError("bad search mode")
        p.update(query=q, search_type=mode)
        rows = _get("/api/events/search?" + urllib.parse.urlencode(p), timeout=60)
        out = []
        for e in rows:
            s = _shape(e, now)
            d = e.get("search_distance")
            s["match"] = int(round(max(0.0, 1.0 - float(d)) * 100)) if d is not None else 0
            out.append(s)
        return {"events": out, "count": len(out), "capped": len(out) >= p["limit"], "query": q, "mode": mode}
    rows = _get("/api/events?" + urllib.parse.urlencode(p), timeout=20)
    return {"events": [_shape(e, now) for e in rows], "count": len(rows), "capped": len(rows) >= p["limit"], "query": "", "mode": ""}


MAX_CLIP = 40 * 1024 * 1024


def clip(eid):
    """The event's clip as an MP4 a browser will play: Frigate streams it chunked (no length, no ranges) and tags HEVC as 'hev1', which
    browsers reject. Re-tagging hev1 as hvc1 is what `ffmpeg -c copy -tag:v hvc1` does (the parameter sets are already in the file)."""
    if not EVENT_ID.fullmatch(eid or ""):
        raise ValueError("bad event id")
    with urllib.request.urlopen(urllib.request.Request(BASE + "/api/events/%s/clip.mp4" % eid, headers={"User-Agent": "glance-admin/1"}), timeout=60) as r:
        data = r.read(MAX_CLIP + 1)
    if len(data) > MAX_CLIP:
        raise ValueError("clip too large")
    head = data[:8192]
    if b"hev1" in head:
        data = data[:8192].replace(b"hev1", b"hvc1", 1) + data[8192:]
    return data


def event(eid):
    if not EVENT_ID.fullmatch(eid or ""):
        raise ValueError("bad event id")
    return _shape(_get("/api/events/" + eid), time.time())


def build():
    now = time.time()
    cfg = _get("/api/config")
    st = _get("/api/stats")
    try:
        rec = _get("/api/recordings/storage")
    except Exception:
        rec = {}
    events = _get("/api/events?limit=30")
    try:
        week = _get("/api/events?limit=3000&after=%d" % int(now - 7 * 86400))
    except Exception:
        week = []
    day = [e for e in week if e.get("start_time", 0) >= now - 86400]
    svc = st.get("service", {})
    stor = (svc.get("storage") or {}).get("/media/frigate/recordings") or {}
    total, used = float(stor.get("total", 0)), float(stor.get("used", 0))
    cams = []
    for name, c in cfg.get("cameras", {}).items():
        s = (st.get("cameras") or {}).get(name, {})
        r = rec.get(name, {})
        cams.append({
            "name": name, "enabled": bool(c.get("enabled", True)), "online": float(s.get("camera_fps") or 0) > 0,
            "recording": bool((c.get("record") or {}).get("enabled")), "detect": bool((c.get("detect") or {}).get("enabled")),
            "width": (c.get("detect") or {}).get("width"), "height": (c.get("detect") or {}).get("height"),
            "camera_fps": round(float(s.get("camera_fps") or 0), 1), "process_fps": round(float(s.get("process_fps") or 0), 1),
            "detect_fps": round(float(s.get("detection_fps") or 0), 1), "skipped_fps": round(float(s.get("skipped_fps") or 0), 1),
            "objects": ", ".join((c.get("objects") or {}).get("track") or []),
            "rec_gb": round(float(r.get("usage", 0)) / 1024, 1), "rec_pct": round(float(r.get("usage_percent", 0)), 1),
            "seen_24h": sum(1 for e in day if e.get("camera") == name)})
    cams.sort(key=lambda x: x["name"])
    recent = [_shape(e, now) for e in events]
    labels = Counter(e.get("label", "?") for e in day)
    # one row per detection type: the newest 30 of each (fetched per label so rare types such as cat or dog still get a row)
    try:
        names = [x for x in _get("/api/labels") if isinstance(x, str) and x != "on_demand"]
    except Exception:
        names = sorted({e.get("label", "?") for e in week})
    by_label = []
    for lab in names:
        try:
            mine = _get("/api/events?" + urllib.parse.urlencode({"labels": lab, "limit": 30}))
        except Exception:
            continue
        if mine:
            by_label.append({"label": lab, "count_24h": labels.get(lab, 0), "events": [_shape(e, now) for e in mine]})
    by_label.sort(key=lambda r: (-r["count_24h"], -r["events"][0]["start"]))
    by_label = by_label[:8]
    hourly = [0] * 24                                  # detections per hour, oldest first, last bucket = the current hour
    for e in day:
        hourly[min(23, max(0, 23 - int((now - e["start_time"]) // 3600)))] += 1
    top = max(hourly + [1])
    hours = [{"h": time.strftime("%H", time.localtime(now - (23 - i) * 3600)), "n": n, "pct": int(round(n * 100 / top))} for i, n in enumerate(hourly)]
    peak = max(hours, key=lambda x: x["n"]) if day else {"h": "", "n": 0}
    det = next(iter((st.get("detectors") or {}).values()), {})
    cpu = (st.get("cpu_usages") or {}).get("frigate.full_system", {})
    return {
        "at": int(now), "version": svc.get("version", "").split("-")[0], "latest": svc.get("latest_version"),
        "update": bool(svc.get("latest_version")) and svc.get("version", "").split("-")[0] != svc.get("latest_version"),
        "uptime_d": round(float(svc.get("uptime", 0)) / 86400, 1),
        "detector": next(iter((cfg.get("detectors") or {}).values()), {}).get("type", ""),
        "inference_ms": round(float(det.get("inference_speed") or 0), 1),
        "cpu_pct": int(float(cpu.get("cpu") or 0)), "mem_pct": int(float(cpu.get("mem") or 0)),
        "retain_days": (cfg.get("record") or {}).get("retain", {}).get("days") or (cfg.get("record") or {}).get("continuous", {}).get("days"),
        "storage": {"total_tb": round(total / 1e6, 2), "used_tb": round(used / 1e6, 2), "free_tb": round((total - used) / 1e6, 2),
                    "pct": int(round(used / total * 100)) if total else 0},
        "cameras": cams, "recent": recent, "events_24h": len(day), "events_7d": len(week), "by_label": by_label,
        "hourly": hours, "hourly_max": max([x["n"] for x in hours] + [1]), "peak_hour": peak["h"], "peak_n": peak["n"],
        "label_names": [r["label"] for r in by_label],
        "labels_24h": [{"label": k, "count": v} for k, v in labels.most_common(6)]}
