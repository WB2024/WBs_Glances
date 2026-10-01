#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/dev.yml: the Dev tab (GitHub, the local Forgejo, dev tools, dev search).
Data comes from glance-admin (/api/dev/summary, /api/tools/summary); private repositories are only rendered inside a PIN-locked widget.
Re-runnable: python3 /opt/glance/tools/gen_dev.py [output-path]"""
import json
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/dev.yml"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def card(title, url, template, cache="2m", extra="", api="dev"):
    return ("        - type: custom-api\n          title: %s\n          title-url: %s\n%s          cache: %s\n          url: %s/api/%s/summary\n"
            "          template: |\n%s\n") % (title, url, extra, cache, GA, api, block(template, 12))


AGEX = '{{ if lt (X) 1 }}just now{{ else if lt (X) 90 }}{{ X }}m{{ else if lt (X) 2880 }}{{ div (X) 60 }}h{{ else }}{{ div (X) 1440 }}d{{ end }}'


def age(expr):
    return AGEX.replace("X", expr)


def sub(t, **kw):
    for k, v in kw.items():
        t = t.replace("@" + k + "@", v)
    return t


# -------------------------------------------------------------------------------- reusable fragments (P = path prefix, e.g. github or github.private)
HEATMAP = """
<div class="wb-hm-wrap"><div class="wb-hm">{{ range .JSON.Array "@P@.heatmap.weeks" }}<div class="wb-hm-col">{{ range .Array "days" }}{{ if lt (.Int "n") 0 }}<i class="wb-hm-d wb-hm-x"></i>{{ else }}<i class="wb-hm-d l{{ .Int "l" }}" title="{{ .String "d" }} &middot; {{ .Int "n" }}"></i>{{ end }}{{ end }}</div>{{ end }}</div></div>
"""

EVENTS = """
<ul class="list list-gap-8 size-h6">
{{ range .JSON.Array "@P@" }}
  <li class="flex gap-10 items-center">
    <span class="wb-ev wb-ev-{{ .String "kind" }}">{{ .String "glyph" }}</span>
    <div class="grow min-width-0"><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "repo" }}</a> <span class="color-subdue">{{ .String "text" }}</span></div>
    <span class="color-subdue shrink-0">AGE</span>
  </li>
{{ else }}<li class="color-subdue">No recent activity.</li>{{ end }}
</ul>
""".replace("AGE", age('.Int "age_min"'))

REPO_CARD = """
      <div class="wb-repo">
        <div class="flex justify-between gap-10 items-center">
          <a class="color-highlight text-truncate wb-repo-name" href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a>
          {{ if .Exists "ci.status" }}{{ if eq (.String "ci.status") "completed" }}{{ if eq (.String "ci.conclusion") "success" }}<span class="color-positive" title="last CI run passed">&#10003;</span>{{ else if eq (.String "ci.conclusion") "failure" }}<span class="color-negative" title="last CI run failed">&#10007;</span>{{ else }}<span class="color-subdue" title="{{ .String "ci.conclusion" }}">&#8226;</span>{{ end }}{{ else }}<span class="color-primary" title="CI running">&#9679;</span>{{ end }}{{ end }}
        </div>
        <div class="size-h6 color-subdue wb-repo-desc">{{ if ne (.String "desc") "" }}{{ .String "desc" }}{{ else }}&nbsp;{{ end }}</div>
        <div class="flex gap-10 size-h6 wb-repo-meta">
          {{ if ne (.String "lang") "" }}<span><i class="wb-dot" style="background:{{ .String "color" }}"></i>{{ .String "lang" }}</span>{{ end }}
          {{ if gt (.Int "stars") 0 }}<span>&#9733; {{ .Int "stars" }}</span>{{ end }}
          {{ if gt (.Int "forks") 0 }}<span>&#8450; {{ .Int "forks" }}</span>{{ end }}
          {{ if gt (.Int "issues") 0 }}<span class="color-primary">! {{ .Int "issues" }}</span>{{ end }}
          <span class="color-subdue" style="margin-left:auto">AGEP</span>
        </div>
        {{ if .Exists "commit.msg" }}<div class="size-h6 text-truncate wb-repo-commit" title="{{ .String "commit.msg" }}"><a href="{{ .String "commit.url" }}" target="_blank" class="color-subdue">{{ .String "commit.sha" }}</a> {{ .String "commit.msg" }}</div>{{ end }}
      </div>
""".replace("AGEP", age('.Int "pushed_min"'))

REPO_LIST_ROW = """
  <li class="flex justify-between gap-10"><span class="text-truncate"><i class="wb-dot" style="background:{{ if ne (.String "lang") "" }}{{ .String "color" }}{{ else }}#444{{ end }}"></i><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a>{{ if .Bool "fork" }} <span class="color-subdue">fork</span>{{ end }}{{ if .Bool "archived" }} <span class="color-subdue">archived</span>{{ end }}</span><span class="color-subdue shrink-0">{{ if gt (.Int "stars") 0 }}&#9733; {{ .Int "stars" }} &middot; {{ end }}AGEP</span></li>
""".replace("AGEP", age('.Int "pushed_min"'))


def repos_block(path, shown=12, label="repositories"):
    return """
{{ $i := 0 }}
<div class="wb-repos">
{{ range .JSON.Array "@P@" }}{{ $i = add $i 1 }}{{ if le $i @N@ }}CARD{{ end }}{{ else }}<p class="color-subdue">No repositories.</p>{{ end }}
</div>
<details class="wb-fold margin-top-10">
  <summary>All @L@ ({{ len (.JSON.Array "@P@") }})</summary>
  <ul class="list list-gap-4 size-h6 margin-top-10">
  {{ range .JSON.Array "@P@" }}ROW{{ end }}
  </ul>
</details>
""".replace("CARD", REPO_CARD).replace("ROW", REPO_LIST_ROW).replace("@P@", path).replace("@N@", str(shown)).replace("@L@", label)


def work_block(prefix):
    sections = [("prs", "YOUR OPEN PULL REQUESTS"), ("review", "REVIEW REQUESTED"), ("issues", "YOUR OPEN ISSUES"), ("assigned", "ASSIGNED TO YOU")]
    out = ""
    for key, title in sections:
        out += """
{{ if gt (len (.JSON.Array "@P@.@K@.items")) 0 }}
<div class="size-h6 color-subdue margin-top-10 margin-bottom-5">@T@ &middot; {{ .JSON.Int "@P@.@K@.total" }}</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "@P@.@K@.items" }}
  <li class="flex justify-between gap-10"><span class="text-truncate"><span class="color-subdue">{{ .String "repo" }}#{{ .Int "number" }}</span> <a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a>{{ if .Bool "draft" }} <span class="color-subdue">draft</span>{{ end }}{{ range .Array "labels" }} <span class="wb-pill">{{ .String "" }}</span>{{ end }}</span><span class="color-subdue shrink-0">{{ if gt (.Int "comments") 0 }}{{ .Int "comments" }} &#9993; &middot; {{ end }}AGE</span></li>
{{ end }}
</ul>
{{ end }}
""".replace("@P@", prefix).replace("@K@", key).replace("@T@", title).replace("AGE", age('.Int "age_min"'))
    return out


def forge_work_block(prefix):
    out = ""
    for key, title in (("prs", "OPEN PULL REQUESTS"), ("issues", "OPEN ISSUES")):
        out += """
{{ if gt (len (.JSON.Array "@P@.work.@K@.items")) 0 }}
<div class="size-h6 color-subdue margin-top-10 margin-bottom-5">@T@ &middot; {{ .JSON.Int "@P@.work.@K@.total" }}</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "@P@.work.@K@.items" }}
  <li class="flex justify-between gap-10"><span class="text-truncate"><span class="color-subdue">{{ .String "repo" }}#{{ .Int "number" }}</span> <a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a></span><span class="color-subdue shrink-0">AGE</span></li>
{{ end }}
</ul>
{{ end }}
""".replace("@P@", prefix).replace("@K@", key).replace("@T@", title).replace("AGE", age('.Int "age_min"'))
    return out


# -------------------------------------------------------------------------------- GitHub overview (profile, stats, heatmap, languages)
github_overview = """
{{ if .JSON.Bool "github.ok" }}
<div class="flex gap-15 items-center margin-bottom-15" style="flex-wrap:wrap">
  <img src="{{ .JSON.String "github.profile.avatar" }}&s=96" alt="" style="width:3.4rem;height:3.4rem;border-radius:50%">
  <div class="grow min-width-0">
    <div class="size-h3"><a class="color-highlight" href="{{ .JSON.String "github.profile.url" }}" target="_blank">{{ .JSON.String "github.profile.name" }}</a> <span class="color-subdue size-h5">@{{ .JSON.String "github.user" }} &middot; since {{ .JSON.String "github.profile.since" }}</span></div>
    {{ if ne (.JSON.String "github.profile.bio") "" }}<div class="size-h6 color-subdue">{{ .JSON.String "github.profile.bio" }}</div>{{ end }}
  </div>
  <div class="wb-stats">
    <div><div class="size-h3 color-highlight">{{ .JSON.Int "github.totals.repos" }}</div><div class="size-h6">REPOS</div></div>
    <div><div class="size-h3 color-highlight">{{ .JSON.Int "github.totals.stars" }}</div><div class="size-h6">STARS</div></div>
    <div><div class="size-h3 color-highlight">{{ .JSON.Int "github.profile.followers" }}</div><div class="size-h6">FOLLOWERS</div></div>
    <div><div class="size-h3 {{ if gt (.JSON.Int "github.totals.issues") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "github.totals.issues" }}</div><div class="size-h6">OPEN ISSUES</div></div>
    {{ if .JSON.Bool "github.has_token" }}<div><div class="size-h3 color-highlight">{{ .JSON.Int "github.heatmap.total" | formatNumber }}</div><div class="size-h6">CONTRIBUTIONS 1Y</div></div>{{ end }}
  </div>
</div>
{{ if .JSON.Bool "github.has_token" }}@@HEAT@@{{ else }}<p class="size-h6 color-subdue">Add a read-only <code>GITHUB_TOKEN</code> to glance-admin for the contribution graph, CI status, last commits and private repositories (locked).</p>{{ end }}
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">LANGUAGES</div>
<div class="wb-langbar">{{ range .JSON.Array "github.languages" }}<div style="flex:{{ .Int "w" }};background:{{ .String "color" }}" title="{{ .String "lang" }} {{ .Float "pct" }}%"></div>{{ end }}</div>
<div class="flex gap-15 size-h6 margin-top-5" style="flex-wrap:wrap">{{ range .JSON.Array "github.languages" }}<span><i class="wb-dot" style="background:{{ .String "color" }}"></i>{{ .String "lang" }} <span class="color-subdue">{{ .Float "pct" }}%</span></span>{{ end }}</div>
{{ else }}<p class="color-negative">GitHub: {{ .JSON.String "github.err" }}</p>{{ end }}
""".replace("@@HEAT@@", sub(HEATMAP, P="github"))

github_activity = ("{{ if .JSON.Bool \"github.ok\" }}" + sub(EVENTS, P="github.events") + "{{ else }}<p class=\"color-negative\">GitHub: {{ .JSON.String \"github.err\" }}</p>{{ end }}")

github_repos = "{{ if .JSON.Bool \"github.ok\" }}" + repos_block("github.repos", 12) + "{{ else }}<p class=\"color-negative\">GitHub: {{ .JSON.String \"github.err\" }}</p>{{ end }}"

github_work = ("{{ if .JSON.Bool \"github.ok\" }}" + work_block("github.work") +
               "{{ if and (eq (len (.JSON.Array \"github.work.prs.items\")) 0) (eq (len (.JSON.Array \"github.work.review.items\")) 0) (eq (len (.JSON.Array \"github.work.issues.items\")) 0) (eq (len (.JSON.Array \"github.work.assigned.items\")) 0) }}<p class=\"color-positive\">Nothing open: no pull requests or issues waiting.</p>{{ end }}"
               "{{ else }}<p class=\"color-negative\">GitHub: {{ .JSON.String \"github.err\" }}</p>{{ end }}")

ci_runs = """
{{ if .JSON.Bool "github.has_token" }}
<ul class="list list-gap-8 size-h6">
{{ range .JSON.Array "github.runs" }}
  <li class="flex gap-10 items-center">
    {{ if eq (.String "status") "completed" }}{{ if eq (.String "conclusion") "success" }}<span class="color-positive">&#10003;</span>{{ else if eq (.String "conclusion") "failure" }}<span class="color-negative">&#10007;</span>{{ else }}<span class="color-subdue">&#8226;</span>{{ end }}{{ else }}<span class="color-primary">&#9679;</span>{{ end }}
    <div class="grow min-width-0"><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "repo" }}</a> <span class="color-subdue">{{ .String "name" }} &middot; {{ .String "branch" }} &middot; {{ .String "title" }}</span></div>
    <span class="color-subdue shrink-0">AGE</span>
  </li>
{{ else }}<li class="color-subdue">No workflow runs yet.</li>{{ end }}
</ul>
{{ else }}<p class="size-h6 color-subdue">Needs <code>GITHUB_TOKEN</code> (Actions: read).</p>{{ end }}
""".replace("AGE", age('.Int "age_min"'))

# -------------------------------------------------------------------------------- Forgejo
forgejo_overview = """
{{ if .JSON.Bool "forgejo.ok" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "forgejo.totals.repos" }}</div><div class="size-h6">REPOSITORIES</div></div>
  <div><div class="size-h3 {{ if gt (.JSON.Int "forgejo.totals.issues") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "forgejo.totals.issues" }}</div><div class="size-h6">OPEN ISSUES</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "forgejo.totals.size_mb" }}<span class="size-h6"> MB</span></div><div class="size-h6">ON DISK</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.String "forgejo.version" }}</div><div class="size-h6">VERSION</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "forgejo.heatmap.total" }}</div><div class="size-h6">CONTRIBUTIONS 1Y</div></div>
</div>
@@HEAT@@
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">RECENTLY UPDATED</div>
@@REPOS@@
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">ACTIVITY</div>
@@EVENTS@@
@@WORK@@
{{ else }}<p class="color-negative">Forgejo is not responding: {{ .JSON.String "forgejo.err" }}</p>{{ end }}
""".replace("@@HEAT@@", sub(HEATMAP, P="forgejo")).replace("@@REPOS@@", repos_block("forgejo.repos", 6)).replace("@@EVENTS@@", sub(EVENTS, P="forgejo.events")).replace("@@WORK@@", forge_work_block("forgejo"))

# -------------------------------------------------------------------------------- private (locked)
private_t = """
{{ if .JSON.Bool "github.ok" }}
<div class="size-h6 color-subdue margin-bottom-5">GITHUB &middot; PRIVATE REPOSITORIES &middot; {{ .JSON.Int "github.totals.private" }}</div>
{{ if .JSON.Bool "github.has_token" }}
GREPOS
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">PRIVATE ACTIVITY</div>
GEVENTS
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">PRIVATE CI RUNS</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "github.private.runs" }}
  <li class="flex justify-between gap-10"><span class="text-truncate">{{ if eq (.String "conclusion") "success" }}<span class="color-positive">&#10003;</span>{{ else if eq (.String "conclusion") "failure" }}<span class="color-negative">&#10007;</span>{{ else }}<span class="color-primary">&#9679;</span>{{ end }} {{ .String "repo" }} <span class="color-subdue">{{ .String "name" }} &middot; {{ .String "branch" }}</span></span><span class="color-subdue shrink-0">AGE</span></li>
{{ else }}<li class="color-subdue">No runs.</li>{{ end }}
</ul>
GWORK
{{ else }}<p class="size-h6 color-subdue">Needs <code>GITHUB_TOKEN</code> to see private repositories.</p>{{ end }}
{{ end }}
{{ if .JSON.Bool "forgejo.ok" }}
<div class="size-h6 color-subdue margin-top-20 margin-bottom-5">FORGEJO &middot; PRIVATE REPOSITORIES &middot; {{ .JSON.Int "forgejo.totals.private" }}</div>
FREPOS
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">PRIVATE ACTIVITY</div>
FEVENTS
FWORK
{{ end }}
""".replace("AGE", age('.Int "age_min"')) \
    .replace("GREPOS", repos_block("github.private.repos", 8, "private repositories")).replace("GEVENTS", sub(EVENTS, P="github.private.events")) \
    .replace("GWORK", work_block("github.private.work")) \
    .replace("FREPOS", repos_block("forgejo.private.repos", 8, "private repositories")).replace("FEVENTS", sub(EVENTS, P="forgejo.private.events")) \
    .replace("FWORK", forge_work_block("forgejo.private"))

# -------------------------------------------------------------------------------- sidebar
engines = json.dumps([
    ["GitHub code", "https://github.com/search?q={QUERY}&type=code", "si:github"],
    ["GitHub repos", "https://github.com/search?q={QUERY}&type=repositories", "si:github"],
    ["MDN", "https://developer.mozilla.org/en-US/search?q={QUERY}", "si:mdnwebdocs"],
    ["Stack Overflow", "https://stackoverflow.com/search?q={QUERY}", "si:stackoverflow"],
    ["Docker Hub", "https://hub.docker.com/search?q={QUERY}", "si:docker"],
    ["PyPI", "https://pypi.org/search/?q={QUERY}", "si:pypi"],
    ["npm", "https://www.npmjs.com/search?q={QUERY}", "si:npm"],
    ["crates.io", "https://crates.io/search?q={QUERY}", "si:rust"],
    ["Hugging Face", "https://huggingface.co/models?search={QUERY}", "si:huggingface"],
    ["DevDocs", "https://devdocs.io/#q={QUERY}", "mdi:book-open-variant"],
], separators=(",", ":"))

search_w = """        - type: html
          title: Dev search
          source: |
            <div class="widget-header"><h2 class="uppercase">Dev search</h2></div>
            <div data-wb="search" data-wb-noindex data-engines='@E@'></div>
""".replace("@E@", engines)

dev_tools = """
{{ range .JSON.Array "dev_tiles" }}
  <div class="wb-tile{{ if not (.Bool "up") }} wb-tile-bad{{ end }} margin-bottom-5">
    <span class="{{ if not (.Bool "up") }}color-negative{{ else }}color-positive{{ end }}">&#9679;</span>
    <div class="wb-tile-main">
      <div class="text-truncate"><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a></div>
      <div class="size-h6 color-subdue text-truncate">{{ .String "detail" }}</div>
    </div>
  </div>
{{ end }}
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">CYBERCHEF RECIPES</div>
<div class="wb-pillrow">
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=From_Base64('A-Za-z0-9%2B/%3D',true,false)">Base64 decode</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=To_Base64('A-Za-z0-9%2B/%3D')">Base64 encode</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=JSON_Beautify('%20%20%20%20',false,true)">JSON beautify</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=JWT_Decode()">JWT decode</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=Magic(3,false,false,'')">Magic</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8100/#recipe=URL_Decode()">URL decode</a>
</div>
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">IT TOOLS</div>
<div class="wb-pillrow">
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/uuid-generator">UUID</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/token-generator">Token</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/hash-text">Hash</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/jwt-parser">JWT</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/crontab-generator">Cron</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/regex-tester">Regex</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/json-prettify">JSON</a>
  <a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8430/url-parser">URL</a>
</div>
"""

api_status = """
{{ if .JSON.Bool "github.ok" }}
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">GitHub token</span><span class="{{ if .JSON.Bool "github.has_token" }}color-positive{{ else }}color-primary{{ end }}">{{ if .JSON.Bool "github.has_token" }}token set{{ else }}none (public data only){{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">API budget</span><span class="{{ if lt (.JSON.Int "github.rate.remaining") 100 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "github.rate.remaining" }} / {{ .JSON.Int "github.rate.limit" }} left</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">repositories</span><span>{{ .JSON.Int "github.totals.public" }} public{{ if .JSON.Bool "github.has_token" }} &middot; {{ .JSON.Int "github.totals.private" }} private{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">forks received</span><span>{{ .JSON.Int "github.totals.forks" }}</span></li>
</ul>
{{ else }}<p class="color-negative size-h6">GitHub: {{ .JSON.String "github.err" }}</p>{{ end }}
"""

links = """        - type: bookmarks
          title: Quick links
          groups:
            - links:
                - { title: "GitHub pull requests",  url: "https://github.com/pulls",          icon: si:github }
                - { title: "GitHub issues",         url: "https://github.com/issues",         icon: si:github }
                - { title: "GitHub notifications",  url: "https://github.com/notifications",  icon: si:github }
                - { title: "GitHub new repository", url: "https://github.com/new",            icon: si:github }
                - { title: "Forgejo",               url: "http://forgejo.wbhomelab",          icon: di:forgejo }
                - { title: "Docker Hub",            url: "https://hub.docker.com",            icon: si:docker }
                - { title: "Dozzle (container logs)", url: "http://${HOST_SVC}:9999",         icon: mdi:text-search }
                - { title: "Dockge · services",     url: "http://${HOST_SVC}:5001",           icon: di:dockge }
"""

LOCKED = "          css-class: wb-restricted\n"

page = "- name: Dev\n  slug: dev\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += card("GitHub", "https://github.com", github_overview) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("GitHub activity", "https://github.com", github_activity), 12) + "\n"
page += block(card("Pull requests and issues", "https://github.com", github_work), 12) + "\n"
page += card("GitHub repositories", "https://github.com?tab=repositories", github_repos) + "\n"
page += card("CI runs (GitHub Actions)", "https://github.com", ci_runs) + "\n"
page += card("Forgejo", "http://forgejo.wbhomelab", forgejo_overview) + "\n"
page += card("Private repositories", "http://forgejo.wbhomelab", private_t, extra=LOCKED) + "\n"
page += "    - size: small\n      widgets:\n" + search_w + "\n"
page += card("Dev tools", "http://${HOST_SVC}:8100", dev_tools, cache="1m", api="tools") + "\n"
page += card("GitHub API", "https://docs.github.com/rest", api_status, cache="2m") + "\n"
page += links

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
