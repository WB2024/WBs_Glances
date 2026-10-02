import re, html, urllib.request, sys
for p in ("home", "downloads", "audio", "video", "infra", "networking", "tools", "dev", "shopping", "cameras", "news", "video-news", "bookmarks", "media", "feeds"):
    h = urllib.request.urlopen("http://127.0.0.1:3002/api/pages/%s/content/" % p, timeout=60).read().decode("utf-8", "ignore")
    print("==", p, len(h), "bytes, widget-error occurrences:", h.count("widget-error"))
    for m in re.finditer(r'widget-error', h):
        s = h[max(0, m.start() - 600):m.start() + 500]
        print("   ...", " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())[:400])
    txt = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S))).split())
    for k in ("Failed", "failed", "went wrong", "rror", "No data", "not found", "unable", "Unable"):
        for mm in list(re.finditer(re.escape(k), txt))[:2]:
            i = mm.start(); print("   text[%s]:" % k, txt[max(0, i - 150):i + 150])
    if p == "home":
        # monitor statuses
        print("   monitor statuses:", re.findall(r'class="monitor-site-status[^"]*"[^>]*>\s*([^<]{1,40})', h)[:30])
