"""Dev summary for the Glance Dev page (stdlib only; imported by app.py).

One cached document with a "github" part (profile, repositories, activity feed, open PRs / issues, CI runs, contribution heatmap,
language mix, API rate limit) and a "forgejo" part (the local forge: the same things, plus version and heatmap).

Privacy: private repositories, and activity that happens in them, are collected into a separate "private" block of each part.
The page shows that block only inside a PIN-locked widget, and app.py never writes it to disk.
GitHub is read-only: GITHUB_TOKEN (optional) should be a fine-grained personal access token with read access only.
Without a token only public data is returned (60 API requests per hour), and per-repository extras (CI, last commit, heatmap) are skipped.
"""
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GH = "https://api.github.com"
UA = {"User-Agent": "glance-admin/1", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "HTML": "#e34c26", "CSS": "#563d7c", "Shell": "#89e051",
    "Go": "#00ADD8", "Rust": "#dea584", "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Java": "#b07219", "Kotlin": "#A97BFF",
    "Dart": "#00B4AB", "PHP": "#4F5D95", "Ruby": "#701516", "Lua": "#000080", "Dockerfile": "#384d54", "Jupyter Notebook": "#DA5B0B",
    "PowerShell": "#012456", "Batchfile": "#C1F12E", "Swift": "#F05138", "Vue": "#41b883", "SCSS": "#c6538c", "Makefile": "#427819",
    "VBA": "#867db1", "Visual Basic": "#945db7", "AutoHotkey": "#6594b9", "Smali": "#cccccc",
}


def _now():
    return time.time()


def _ts(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _age_min(iso):
    t = _ts(iso)
    return max(0, int((_now() - t) / 60)) if t else None


def _http(url, headers=None, data=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "null"), dict(r.headers)


def _first_line(s, n=90):
    return (str(s or "").strip().split("\n", 1)[0])[:n]


def _levels(counts):
    """0-4 intensity per day from the non-zero distribution (like the contribution graph)."""
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return lambda c: 0
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if len(nz) >= 4 else [1, 2, 3]
    return lambda c: 0 if c <= 0 else 1 if c <= q[0] else 2 if c <= q[1] else 3 if c <= q[2] else 4


def _weeks(day_counts, levels=None):
    """{'YYYY-MM-DD': n} -> up to 53 week columns of 7 days (Sunday first), ending with the current week."""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=364)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)       # back to Sunday
    lv = levels or _levels(list(day_counts.values()))
    weeks, d = [], start
    while d <= today:
        col = []
        for _ in range(7):
            n = day_counts.get(d.isoformat(), 0) if d <= today else -1
            col.append({"d": d.isoformat(), "n": n, "l": lv(n) if n >= 0 else -1})
            d += datetime.timedelta(days=1)
        weeks.append({"days": col})
    return weeks


def _merge_events(events, loose=False):
    """Runs of the same kind of event in the same repository (an automated mirror pushing every few minutes) become one row: 'pushed to main x7'.
    loose=True merges any consecutive events of one repository ('12 events')."""
    out = []
    for e in events:
        prev = out[-1] if out else None
        if prev and prev["repo"] == e["repo"] and prev["private"] == e["private"] and (loose or prev["kind"] == e["kind"]):
            prev["count"] = prev.get("count", 1) + 1
            prev["text"] = ("%d events" % prev["count"]) if loose else "%s ×%d" % (prev["base"], prev["count"])
            continue
        base = e["text"]
        if e["kind"] == "Push" and " to " in base:
            base = "pushed to " + base.split(" to ", 1)[1].split(" · ")[0]
        e["base"] = base
        out.append(e)
    return out


# ============================================================================= GitHub
class GitHub:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "").strip()
        self.user = os.environ.get("GITHUB_USER", "").strip()
        self.rate = {"remaining": None, "limit": None}

    def api(self, path, params=None):
        h = dict(UA)
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        url = GH + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        data, hd = _http(url, h)
        lower = {k.lower(): v for k, v in hd.items()}
        if "x-ratelimit-remaining" in lower and lower.get("x-ratelimit-resource", "core") == "core":
            self.rate = {"remaining": int(lower["x-ratelimit-remaining"]), "limit": int(lower.get("x-ratelimit-limit", 0))}
        return data

    def graphql(self, query):
        data, _ = _http(GH + "/graphql", {"Authorization": "Bearer " + self.token, "User-Agent": UA["User-Agent"], "Content-Type": "application/json"},
                        json.dumps({"query": query}).encode())
        return data

    # ---- pieces
    def repos(self):
        out, page = [], 1
        while page <= 4:
            if self.token:
                rows = self.api("/user/repos", {"per_page": 100, "sort": "pushed", "affiliation": "owner", "page": page})
            else:
                rows = self.api("/users/%s/repos" % self.user, {"per_page": 100, "sort": "pushed", "type": "owner", "page": page})
            out += rows
            if len(rows) < 100:
                break
            page += 1
        shaped = []
        for r in out:
            lang = r.get("language") or ""
            shaped.append({"name": r["name"], "full": r["full_name"], "private": bool(r.get("private")), "fork": bool(r.get("fork")),
                           "archived": bool(r.get("archived")), "lang": lang, "color": LANG_COLORS.get(lang, "#8b949e"),
                           "stars": r.get("stargazers_count", 0), "forks": r.get("forks_count", 0), "issues": r.get("open_issues_count", 0),
                           "size_kb": r.get("size", 0), "desc": (r.get("description") or "")[:90], "url": r["html_url"],
                           "pushed_min": _age_min(r.get("pushed_at")), "branch": r.get("default_branch", "main")})
        return shaped

    def extras(self, repo):
        """Latest workflow run and latest commit of one repository (needs the token budget)."""
        res = {}
        try:
            runs = self.api("/repos/%s/actions/runs" % repo["full"], {"per_page": 3}).get("workflow_runs", [])
            res["runs"] = [{"repo": repo["name"], "private": repo["private"], "name": (w.get("name") or "")[:40], "branch": w.get("head_branch") or "",
                            "status": w.get("status") or "", "conclusion": w.get("conclusion") or "", "age_min": _age_min(w.get("updated_at")),
                            "url": w.get("html_url") or repo["url"], "title": _first_line(w.get("display_title"), 60)} for w in runs]
        except Exception:
            res["runs"] = []
        try:
            c = self.api("/repos/%s/commits" % repo["full"], {"per_page": 1})[0]
            res["commit"] = {"msg": _first_line(c["commit"]["message"]), "age_min": _age_min(c["commit"]["author"]["date"]),
                             "sha": c["sha"][:7], "url": c["html_url"]}
        except Exception:
            res["commit"] = None
        return res

    def events(self, private_names):
        rows = self.api("/users/%s/events" % self.user, {"per_page": 70})
        out = []
        for e in rows:
            p = e.get("payload") or {}
            repo = (e.get("repo") or {}).get("name", "")
            short = repo.split("/", 1)[-1]
            t = e.get("type", "")
            glyph, text, url = "•", t.replace("Event", ""), "https://github.com/" + repo
            if t == "PushEvent":
                n = p.get("size") or len(p.get("commits") or []) or 1
                glyph, text = "↑", "pushed %d commit%s to %s" % (n, "" if n == 1 else "s", (p.get("ref") or "").replace("refs/heads/", ""))
                msg = _first_line(((p.get("commits") or [{}])[-1]).get("message"), 70)
                if msg:
                    text += " · " + msg
            elif t == "PullRequestEvent":
                pr = p.get("pull_request") or {}
                glyph, text, url = "⇄", "%s PR #%s %s" % ("merged" if pr.get("merged") else p.get("action", ""), p.get("number", ""), _first_line(pr.get("title"), 60)), pr.get("html_url", url)
            elif t == "IssuesEvent":
                i = p.get("issue") or {}
                glyph, text, url = "!", "%s issue #%s %s" % (p.get("action", ""), i.get("number", ""), _first_line(i.get("title"), 60)), i.get("html_url", url)
            elif t == "IssueCommentEvent":
                i = p.get("issue") or {}
                glyph, text, url = "…", "commented on #%s %s" % (i.get("number", ""), _first_line(i.get("title"), 50)), (p.get("comment") or {}).get("html_url", url)
            elif t == "CreateEvent":
                glyph, text = "+", "created %s %s" % (p.get("ref_type", ""), p.get("ref") or "")
            elif t == "DeleteEvent":
                glyph, text = "×", "deleted %s %s" % (p.get("ref_type", ""), p.get("ref") or "")
            elif t == "WatchEvent":
                glyph, text = "★", "starred"
            elif t == "ForkEvent":
                glyph, text = "⑂", "forked"
            elif t == "ReleaseEvent":
                r = p.get("release") or {}
                glyph, text, url = "⚑", "released %s" % (r.get("tag_name") or ""), r.get("html_url", url)
            elif t == "PublicEvent":
                glyph, text = "○", "made public"
            out.append({"glyph": glyph, "kind": t.replace("Event", ""), "repo": short, "text": text.strip(), "url": url, "age_min": _age_min(e.get("created_at")),
                        "private": (not e.get("public", True)) or short in private_names})
        return _merge_events(out)

    def work(self):
        """Open PRs and issues that need attention (search API)."""
        u = self.user
        qs = [("prs", "is:pr is:open author:%s archived:false" % u), ("review", "is:pr is:open review-requested:%s archived:false" % u),
              ("issues", "is:issue is:open author:%s archived:false" % u), ("assigned", "is:issue is:open assigned:%s archived:false" % u)]
        out = {}
        for key, q in qs:
            try:
                res = self.api("/search/issues", {"q": q, "per_page": 12, "sort": "updated"})
            except Exception:
                out[key] = {"total": 0, "items": []}
                continue
            items = []
            for i in res.get("items", []):
                repo = i["repository_url"].rsplit("/", 2)
                full = "%s/%s" % (repo[-2], repo[-1])
                items.append({"title": _first_line(i["title"], 80), "repo": repo[-1], "number": i["number"], "url": i["html_url"], "age_min": _age_min(i.get("updated_at")),
                              "comments": i.get("comments", 0), "draft": bool(i.get("draft")), "labels": [l["name"] for l in i.get("labels", [])][:3], "full": full})
            out[key] = {"total": res.get("total_count", 0), "items": items}
        return out

    def heatmap(self):
        if not self.token:
            return None
        q = ('{ user(login: "%s") { contributionsCollection { contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } } } }'
             % re.sub(r"[^A-Za-z0-9-]", "", self.user))
        cal = self.graphql(q)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        counts = {d["date"]: d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]}
        return {"total": cal["totalContributions"], "weeks": _weeks(counts), "active_days": sum(1 for v in counts.values() if v)}

    def build(self):
        if not self.user:
            raise RuntimeError("GITHUB_USER is not set")
        prof = self.api("/users/" + self.user)
        repos = self.repos()
        private_names = {r["name"] for r in repos if r["private"]}
        owned = [r for r in repos if not r["fork"] and not r["archived"]]
        extras = {}
        if self.token:
            with ThreadPoolExecutor(max_workers=4) as ex:
                top = owned[:12]
                for r, ext in zip(top, ex.map(self.extras, top)):
                    extras[r["full"]] = ext
        for r in repos:
            ext = extras.get(r["full"], {})
            r["commit"] = ext.get("commit")
            runs = ext.get("runs") or []
            r["ci"] = ({"status": runs[0]["status"], "conclusion": runs[0]["conclusion"], "url": runs[0]["url"]} if runs else None)
        runs = sorted([x for e in extras.values() for x in e.get("runs", [])], key=lambda x: x["age_min"] if x["age_min"] is not None else 1e9)[:12]
        events = self.events(private_names)
        try:
            work = self.work()
        except Exception:
            work = {}
        try:
            heat = self.heatmap()
        except Exception:
            heat = None
        langs = {}
        for r in repos:
            if r["fork"] or not r["lang"]:
                continue
            l = langs.setdefault(r["lang"], {"lang": r["lang"], "color": r["color"], "size": 0, "repos": 0})
            l["size"] += max(r["size_kb"], 1)
            l["repos"] += 1
        tot = sum(l["size"] for l in langs.values()) or 1
        lang_list = sorted(langs.values(), key=lambda x: -x["size"])[:8]
        for l in lang_list:
            l["pct"] = round(l["size"] * 100 / tot, 1)
            l["w"] = max(int(round(l["size"] * 100 / tot)), 1)
        pub = [r for r in repos if not r["private"]]
        priv = [r for r in repos if r["private"]]
        pub_ev = [e for e in events if not e["private"]]

        def split_runs(want_private):
            return [x for x in runs if x["private"] == want_private][:8]

        def split_work(want_private, private_full):
            res = {}
            for k, v in work.items():
                items = [i for i in v["items"] if (i["full"] in private_full) == want_private]
                res[k] = {"total": len(items) if want_private else max(v["total"] - sum(1 for i in v["items"] if i["full"] in private_full), 0), "items": items[:8]}
            return res

        private_full = {r["full"] for r in priv}
        out = {"ok": True, "user": self.user, "has_token": bool(self.token), "rate": self.rate,
               "profile": {"name": prof.get("name") or self.user, "avatar": prof.get("avatar_url", ""), "url": prof.get("html_url", ""), "followers": prof.get("followers", 0),
                           "following": prof.get("following", 0), "bio": (prof.get("bio") or "")[:120], "since": (prof.get("created_at") or "")[:4]},
               "totals": {"repos": len(repos), "public": len(pub), "private": len(priv), "stars": sum(r["stars"] for r in repos), "forks": sum(r["forks"] for r in repos),
                          "issues": sum(r["issues"] for r in pub)},
               "heatmap": heat, "languages": lang_list, "repos": pub[:60], "events": pub_ev[:25], "runs": split_runs(False), "work": split_work(False, private_full),
               "private": {"repos": priv[:60], "events": [e for e in events if e["private"]][:20], "runs": split_runs(True), "work": split_work(True, private_full)}}
        return out


# ============================================================================= Forgejo
def forgejo():
    host = os.environ.get("TOOLS_HOST", "host.docker.internal")
    tok = os.environ.get("FORGEJO_TOKEN", "")
    link = os.environ.get("FORGEJO_URL", "http://forgejo.wbhomelab").rstrip("/")
    b = "http://%s:3001/api/v1" % host
    h = {"Authorization": "token " + tok, "User-Agent": "glance-admin/1"}

    def get(path, **params):
        return _http(b + path + (("?" + urllib.parse.urlencode(params)) if params else ""), h)

    try:
        ver, _ = get("/version")
        me, _ = get("/user")
        repos_raw, _ = get("/repos/search", sort="updated", order="desc", limit=50)
        repos = repos_raw["data"]
    except Exception as exc:
        return {"ok": False, "err": str(exc)[:100]}
    shaped = []
    for r in repos:
        shaped.append({"name": r["name"], "full": r["full_name"], "private": bool(r.get("private")), "fork": bool(r.get("fork")), "archived": bool(r.get("archived")),
                       "lang": r.get("language") or "", "color": LANG_COLORS.get(r.get("language") or "", "#8b949e"), "stars": r.get("stars_count", 0),
                       "forks": r.get("forks_count", 0), "issues": r.get("open_issues_count", 0), "size_kb": r.get("size", 0), "desc": (r.get("description") or "")[:90],
                       "url": r.get("html_url") or "%s/%s" % (link, r["full_name"]), "pushed_min": _age_min(r.get("updated_at")), "branch": r.get("default_branch", "main")})

    def commit(r):
        try:
            c, _ = get("/repos/%s/commits" % r["full"], limit=1, stat="false", verification="false", files="false")
            c = c[0]
            return {"msg": _first_line(c["commit"]["message"]), "age_min": _age_min(c["commit"]["author"]["date"]), "sha": c["sha"][:7], "url": c.get("html_url", r["url"])}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        top = [r for r in shaped if not r["archived"]][:12]
        for r, c in zip(top, ex.map(commit, top)):
            r["commit"] = c
    heat = None
    try:
        hm, _ = get("/users/%s/heatmap" % me["login"])
        counts = {}
        for x in hm:
            d = datetime.date.fromtimestamp(x["timestamp"]).isoformat()
            counts[d] = counts.get(d, 0) + x["contributions"]
        heat = {"total": sum(counts.values()), "weeks": _weeks(counts), "active_days": sum(1 for v in counts.values() if v)}
    except Exception:
        pass

    def search(kind):
        try:
            rows, hd = get("/repos/issues/search", state="open", type=kind, limit=12, owner=me["login"])
        except Exception:
            return {"total": 0, "items": []}
        items = [{"title": _first_line(i["title"], 80), "repo": i["repository"]["name"], "number": i["number"], "url": i["html_url"], "age_min": _age_min(i.get("updated_at")),
                  "comments": i.get("comments", 0), "private": bool(i["repository"].get("private")), "draft": False, "labels": [l["name"] for l in i.get("labels", [])][:3]}
                 for i in rows]
        return {"total": len(items), "items": items}

    issues, prs = search("issues"), search("pulls")
    feed = []
    try:
        acts, _ = get("/users/%s/activities/feeds" % me["login"], limit=25, **{"only-performed-by": "true"})
        for a in acts:
            repo = (a.get("repo") or {}).get("name", "")
            op = a.get("op_type", "")
            msg = ""
            try:
                content = json.loads(a.get("content") or "{}")
                msg = _first_line(((content.get("Commits") or [{}])[0]).get("Message"), 70) if isinstance(content, dict) else ""
            except Exception:
                pass
            feed.append({"glyph": {"commit_repo": "↑", "create_repo": "+", "create_issue": "!", "comment_issue": "…", "merge_pull_request": "⇄",
                                   "create_pull_request": "⇄", "push_tag": "⚑"}.get(op, "•"), "kind": op, "repo": repo,
                         "text": (op.replace("_", " ") + (" · " + msg if msg else "")), "url": "%s/%s" % (link, (a.get("repo") or {}).get("full_name", "")),
                         "age_min": _age_min(a.get("created")), "private": bool((a.get("repo") or {}).get("private"))})
        feed = _merge_events(feed, loose=True)
    except Exception:
        pass
    pub = [r for r in shaped if not r["private"]]
    priv = [r for r in shaped if r["private"]]
    return {"ok": True, "version": str(ver.get("version", "")).split("+")[0], "user": me["login"], "url": link,
            "totals": {"repos": len(shaped), "public": len(pub), "private": len(priv), "issues": sum(r["issues"] for r in pub), "size_mb": round(sum(r["size_kb"] for r in shaped) / 1024)},
            "heatmap": heat, "repos": pub[:40], "events": [e for e in feed if not e["private"]][:15],
            "work": {"issues": {"total": sum(1 for i in issues["items"] if not i["private"]), "items": [i for i in issues["items"] if not i["private"]][:8]},
                     "prs": {"total": sum(1 for i in prs["items"] if not i["private"]), "items": [i for i in prs["items"] if not i["private"]][:8]}},
            "private": {"repos": priv[:40], "events": [e for e in feed if e["private"]][:12],
                        "work": {"issues": {"total": sum(1 for i in issues["items"] if i["private"]), "items": [i for i in issues["items"] if i["private"]][:8]},
                                 "prs": {"total": sum(1 for i in prs["items"] if i["private"]), "items": [i for i in prs["items"] if i["private"]][:8]}}}}


def build():
    with ThreadPoolExecutor(max_workers=2) as ex:
        g = ex.submit(lambda: GitHub().build())
        f = ex.submit(forgejo)
        out = {"at": int(_now())}
        for k, fut in (("github", g), ("forgejo", f)):
            try:
                out[k] = fut.result()
            except Exception as exc:
                out[k] = {"ok": False, "err": str(exc)[:120]}
    return out


def public_part(doc):
    """What may be written to disk: the document without its private blocks."""
    d = json.loads(json.dumps(doc))
    for k in ("github", "forgejo"):
        if isinstance(d.get(k), dict):
            d[k].pop("private", None)
    return d
