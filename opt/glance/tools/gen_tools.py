#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/tools.yml
  RustyDisc (rich, lifted from the old Media page) | Paperless, Forgejo, BookStack (rich cards) | a tile for every other tool | releases
Re-runnable: python3 /opt/glance/tools/gen_tools.py [output-path]"""
import re
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/tools.yml"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


AGE = '{{ if gt (@X@) 48 }}{{ div (@X@) 24 }}d{{ else }}{{ @X@ }}h{{ end }} ago'


def age(expr):
    return AGE.replace("@X@", expr)


# ----------------------------------------------------------------------------- RustyDisc: the existing widget, moved here
media = open("/opt/glance/legacy/media.yml.pre-phase8", encoding="utf-8").read()   # copy of the old Media page (kept for this widget)
m = re.search(r"(        - type: custom-api\n          title: RustyDisc\n.*?)(?=\n        - type: custom-api\n          title: MediaThatFeelsLike)", media, re.S)
assert m, "RustyDisc widget not found in media.yml"
rustydisc = m.group(1).rstrip("\n").replace("192.168.1.110", "${HOST_SVC}") + "\n"
assert "8087" in rustydisc and "${HOST_SVC}" in rustydisc


def card(title, url, template):
    return ("        - type: custom-api\n          title: %s\n          title-url: %s\n          cache: 2m\n          url: %s/api/tools/summary\n"
            "          template: |\n%s\n") % (title, url, GA, block(template, 12))


paperless = """
{{ if .JSON.Bool "paperless.up" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "paperless.docs" | formatNumber }}</div><div class="size-h6">DOCUMENTS</div></div>
  <div><div class="size-h3 {{ if gt (.JSON.Int "paperless.inbox") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "paperless.inbox" }}</div><div class="size-h6">IN INBOX</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "paperless.tags" }}</div><div class="size-h6">TAGS</div></div>
</div>
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">version</span><span>{{ .JSON.String "paperless.version" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">database</span><span class="{{ if .JSON.Bool "paperless.db_ok" }}color-positive{{ else }}color-negative{{ end }}">{{ if .JSON.Bool "paperless.db_ok" }}OK{{ else }}problem{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">storage free</span><span>{{ .JSON.Float "paperless.free_tb" }} of {{ .JSON.Float "paperless.total_tb" }} TB</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">last document added</span><span>AGE_LAST</span></li>
</ul>
{{ else }}<p class="color-subdue">Paperless is not responding.</p>{{ end }}
""".replace("AGE_LAST", age('.JSON.Int "paperless.last_added_h"'))

forgejo = """
{{ if .JSON.Bool "forgejo.up" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "forgejo.repos" }}</div><div class="size-h6">REPOSITORIES</div></div>
  <div><div class="size-h3 {{ if gt (.JSON.Int "forgejo.open_issues") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "forgejo.open_issues" }}</div><div class="size-h6">OPEN ISSUES</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.String "forgejo.version" }}</div><div class="size-h6">VERSION</div></div>
</div>
<div class="size-h6 color-subdue margin-bottom-5">RECENTLY UPDATED</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "forgejo.recent" }}
  <li class="flex justify-between gap-10"><span class="text-truncate">{{ .String "name" }}{{ if .Bool "private" }} <span class="color-subdue">private</span>{{ end }}</span><span class="color-subdue shrink-0">AGE_R</span></li>
{{ end }}
</ul>
{{ else }}<p class="color-subdue">Forgejo is not responding.</p>{{ end }}
""".replace("AGE_R", age('.Int "age_h"'))

bookstack = """
{{ if .JSON.Bool "bookstack.up" }}
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "bookstack.books" }}</div><div class="size-h6">BOOKS</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "bookstack.pages" | formatNumber }}</div><div class="size-h6">PAGES</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "bookstack.chapters" }}</div><div class="size-h6">CHAPTERS</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "bookstack.shelves" }}</div><div class="size-h6">SHELVES</div></div>
</div>
<div class="size-h6 color-subdue margin-bottom-5">RECENTLY UPDATED</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "bookstack.recent" }}
  <li class="flex justify-between gap-10"><span class="text-truncate">{{ .String "name" }} <span class="color-subdue">&middot; {{ .String "book" }}</span></span><span class="color-subdue shrink-0">AGE_R</span></li>
{{ end }}
</ul>
{{ else }}<p class="color-subdue">BookStack is not responding.</p>{{ end }}
""".replace("AGE_R", age('.Int "age_h"'))

tiles = """
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-positive">{{ .JSON.Int "up" }}</div><div class="size-h6">RESPONDING</div></div>
  <div><div class="size-h3 {{ if gt (.JSON.Int "down") 0 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "down" }}</div><div class="size-h6">DOWN</div></div>
</div>
{{ $g := "" }}
{{ range .JSON.Array "tiles" }}
  {{ if ne (.String "group") $g }}{{ if ne $g "" }}</div>{{ end }}<div class="size-h6 color-subdue margin-top-10 margin-bottom-5">{{ .String "group" }}</div><div class="wb-tiles">{{ $g = .String "group" }}{{ end }}
  <div class="wb-tile{{ if not (.Bool "up") }} wb-tile-bad{{ end }}">
    <span class="{{ if not (.Bool "up") }}color-negative{{ else if .Bool "warn" }}color-primary{{ else }}color-positive{{ end }}">&#9679;</span>
    <div class="wb-tile-main">
      <div class="text-truncate"><a class="color-highlight" href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a></div>
      <div class="size-h6 color-subdue text-truncate">{{ .String "detail" }}</div>
    </div>
  </div>
{{ end }}
</div>
"""


releases_t = """
{{ range .JSON.Array "groups" }}
  <div class="size-h6 color-subdue margin-top-10 margin-bottom-5">{{ .String "title" }}</div>
  <ul class="list list-gap-4 size-h6">
  {{ range .Array "items" }}
    <li class="flex justify-between gap-10"><a class="color-highlight text-truncate" href="{{ .String "url" }}" target="_blank">{{ .String "name" }}</a><span class="shrink-0 {{ if .Bool "ok" }}{{ if and (gt (.Int "age_h") 0) (lt (.Int "age_h") 336) }}color-primary{{ else }}color-subdue{{ end }}{{ else }}color-negative{{ end }}">{{ if .Bool "ok" }}{{ .String "tag" }}{{ if gt (.Int "age_h") 0 }} &middot; {{ if gt (.Int "age_h") 48 }}{{ div (.Int "age_h") 24 }}d{{ else }}{{ .Int "age_h" }}h{{ end }}{{ end }}{{ else }}unavailable{{ end }}</span></li>
  {{ end }}
  </ul>
{{ end }}
"""
rel_card = ("        - type: custom-api\n          title: Latest releases\n          title-url: https://github.com\n          cache: 1h\n"
            "          url: %s/api/releases/summary\n          template: |\n%s\n") % (GA, block(releases_t, 12))



# ----------------------------------------------------------------------------- rich cards for the small tools (data: glance-admin /api/tools/summary "cards")
def ctr_line(path):
    return """
<div class="size-h6 color-subdue margin-top-15 wb-ctr">{{ if .JSON.Bool "@P@.running" }}<span class="color-positive">&#9679;</span> container {{ .JSON.String "@P@.status" }}{{ if ge (.JSON.Float "@P@.cpu_pct") 0.0 }} &middot; {{ .JSON.Float "@P@.cpu_pct" }}% CPU &middot; {{ .JSON.Int "@P@.mem_mb" }} MB{{ end }}{{ if ne (.JSON.String "@P@.tag") "latest" }} &middot; {{ .JSON.String "@P@.tag" }}{{ end }}{{ else }}<span class="color-negative">&#9679;</span> container {{ .JSON.String "@P@.state" }}{{ if ne (.JSON.String "@P@.status") "" }} &middot; {{ .JSON.String "@P@.status" }}{{ end }}{{ end }}</div>
""".replace("@P@", path)


def down(name, path):
    return '{{ else }}<p class="color-negative">%s is not responding{{ if ne (.JSON.String "%s.err") "" }}: {{ .JSON.String "%s.err" }}{{ end }}</p>{{ end }}' % (name, path, path)


def stat(value, label, cls="color-highlight"):
    return '<div><div class="size-h3 %s">%s</div><div class="size-h6">%s</div></div>' % (cls, value, label)


kiwix_t = ("""
{{ if .JSON.Bool "cards.kiwix.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.kiwix.libraries" }}', "LIBRARIES") + stat('{{ .JSON.Int "cards.kiwix.articles" | formatNumber }}', "ARTICLES")
           + stat('{{ .JSON.Int "cards.kiwix.media" | formatNumber }}', "MEDIA FILES") + stat('{{ .JSON.String "cards.kiwix.newest" }}', "NEWEST") + """</div>
<div class="size-h6 color-subdue margin-bottom-5">BY SUBJECT</div>
<ul class="list list-gap-4 size-h6 margin-bottom-10">
{{ range .JSON.Array "cards.kiwix.categories" }}
  <li class="flex justify-between gap-10"><span>{{ .String "name" }}</span><span class="color-subdue">{{ .Int "count" }} libraries &middot; {{ .Int "articles" | formatNumber }} articles</span></li>
{{ end }}
</ul>
<div class="size-h6 color-subdue margin-bottom-5">BIGGEST</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "cards.kiwix.top" }}
  <li class="flex justify-between gap-10"><a class="color-highlight text-truncate" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a><span class="color-subdue shrink-0">{{ .Int "articles" | formatNumber }}</span></li>
{{ end }}
</ul>
<details class="wb-fold margin-top-10">
  <summary>All {{ .JSON.Int "cards.kiwix.libraries" }} libraries</summary>
  <ul class="list list-gap-4 size-h6 margin-top-10">
  {{ range .JSON.Array "cards.kiwix.all" }}
    <li class="flex justify-between gap-10"><a class="color-highlight text-truncate" href="{{ .String "url" }}" target="_blank">{{ .String "title" }}</a><span class="color-subdue shrink-0">{{ .Int "articles" | formatNumber }}</span></li>
  {{ end }}
  </ul>
</details>
""" + ctr_line("cards.kiwix.ctr") + down("Kiwix", "cards.kiwix"))

searxng_t = ("""
{{ if .JSON.Bool "cards.searxng.up" }}
<form action="http://searxng.wbhomelab/search" method="get" target="_blank" class="wb-miniform margin-bottom-15">
  <input type="search" name="q" placeholder="Search privately with SearXNG..." autocomplete="off"><button type="submit">Search</button>
</form>
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.searxng.enabled" }}<span class="size-h6"> / {{ .JSON.Int "cards.searxng.engines" }}</span>', "ENGINES ON")
             + stat('{{ len (.JSON.Array "cards.searxng.categories") }}', "CATEGORIES") + stat('{{ len (.JSON.Array "cards.searxng.plugins") }}', "PLUGINS")
             + stat('{{ .JSON.String "cards.searxng.version" }}', "VERSION") + """</div>
<div class="size-h6 color-subdue margin-bottom-5">ENGINES ENABLED PER CATEGORY</div>
<div class="wb-pillrow margin-bottom-10">{{ range .JSON.Array "cards.searxng.categories" }}<span class="wb-pill">{{ .String "name" }} {{ .Int "count" }}</span>{{ end }}</div>
<div class="size-h6 color-subdue margin-bottom-5">GENERAL SEARCH ENGINES</div>
<div class="wb-pillrow margin-bottom-10">{{ range .JSON.Array "cards.searxng.top_engines" }}<span class="wb-pill" title="shortcut !{{ .String "shortcut" }}">{{ .String "name" }}</span>{{ end }}</div>
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">plugins</span><span class="text-truncate">{{ range .JSON.Array "cards.searxng.plugins" }}{{ .String "" }} {{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">safe search</span><span>{{ .JSON.String "cards.searxng.safe" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">autocomplete</span><span>{{ .JSON.String "cards.searxng.autocomplete" }}</span></li>
</ul>
""" + ctr_line("cards.searxng.ctr") + down("SearXNG", "cards.searxng"))

nomad_t = ("""
{{ if .JSON.Bool "cards.nomad.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.nomad.running" }}<span class="size-h6"> / {{ len (.JSON.Array "cards.nomad.services") }}</span>', "SERVICES UP", "color-positive")
           + stat('{{ .JSON.Int "cards.nomad.updates" }}', "UPDATES", '{{ if gt (.JSON.Int "cards.nomad.updates") 0 }}color-primary{{ else }}color-highlight{{ end }}')
           + stat('{{ .JSON.Int "cards.nomad.load_pct" }}%', "HOST CPU") + stat('{{ .JSON.Int "cards.nomad.mem_pct" }}%', "HOST RAM") + """</div>
<ul class="list list-gap-4 size-h6 margin-bottom-10">
{{ range .JSON.Array "cards.nomad.services" }}
  <li class="flex justify-between gap-10"><span class="text-truncate"><span class="{{ if .Bool "running" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span> {{ .String "name" }} <span class="color-subdue">&middot; {{ .String "by" }}</span></span><span class="shrink-0">{{ if ne (.String "update") "" }}<span class="color-primary">update {{ .String "update" }}</span>{{ else }}<span class="color-subdue">{{ .String "status" }}</span>{{ end }}</span></li>
{{ end }}
</ul>
<div class="flex justify-between size-h6"><span class="color-subdue">STORAGE &middot; {{ .JSON.Float "cards.nomad.storage_used_tb" }} / {{ .JSON.Float "cards.nomad.storage_tb" }} TB</span><span>{{ .JSON.Int "cards.nomad.storage_pct" }}%</span></div>
<div class="progress-bar margin-bottom-8"><div class="progress-value{{ if gt (.JSON.Int "cards.nomad.storage_pct") 85 }} progress-value-notice{{ end }}" style="--percent: {{ .JSON.Int "cards.nomad.storage_pct" }}"></div></div>
<div class="flex justify-between size-h6"><span class="color-subdue">ROOT DISK</span><span>{{ .JSON.Int "cards.nomad.root_pct" }}%</span></div>
<div class="progress-bar margin-bottom-8"><div class="progress-value{{ if gt (.JSON.Int "cards.nomad.root_pct") 85 }} progress-value-notice{{ end }}" style="--percent: {{ .JSON.Int "cards.nomad.root_pct" }}"></div></div>
<div class="flex justify-between size-h6"><span class="color-subdue">SWAP</span><span>{{ .JSON.Int "cards.nomad.swap_pct" }}%</span></div>
<div class="progress-bar margin-bottom-8"><div class="progress-value" style="--percent: {{ .JSON.Int "cards.nomad.swap_pct" }}"></div></div>
<p class="size-h6 color-subdue">{{ .JSON.String "cards.nomad.cpu_brand" }} &middot; {{ .JSON.Int "cards.nomad.cores" }} cores &middot; {{ .JSON.Int "cards.nomad.mem_gb" }} GB &middot; up {{ .JSON.Float "cards.nomad.uptime_d" }} d &middot; kernel {{ .JSON.String "cards.nomad.kernel" }}{{ if .JSON.Bool "cards.nomad.gpu_ok" }} &middot; GPU reachable for AI{{ end }}</p>
""" + ctr_line("cards.nomad.ctr") + down("NOMAD", "cards.nomad"))

kolibri_t = ("""
{{ if .JSON.Bool "cards.kolibri.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.kolibri.users" }}', "USERS") + stat('{{ .JSON.Int "cards.kolibri.learners" }}', "LEARNERS")
             + stat('{{ .JSON.Int "cards.kolibri.classrooms" }}', "CLASSROOMS")
             + stat('{{ .JSON.Int "cards.kolibri.channels" }}', "CHANNELS", '{{ if eq (.JSON.Int "cards.kolibri.channels") 0 }}color-primary{{ else }}color-highlight{{ end }}') + """</div>
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">facility</span><span class="text-truncate">{{ .JSON.String "cards.kolibri.facility" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">device</span><span class="text-truncate">{{ .JSON.String "cards.kolibri.device" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">version</span><span>{{ .JSON.String "cards.kolibri.version" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">learner sign-up</span><span>{{ if .JSON.Bool "cards.kolibri.signup" }}open{{ else }}closed{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">sync with other devices</span><span>{{ if .JSON.Bool "cards.kolibri.synced" }}synced{{ else }}never{{ end }}</span></li>
</ul>
{{ if eq (.JSON.Int "cards.kolibri.channels") 0 }}<p class="size-h6 color-primary margin-top-10">No content channels installed yet. Open Kolibri, Device, Channels to import courses and videos.</p>{{ end }}
""" + ctr_line("cards.kolibri.ctr") + down("Kolibri", "cards.kolibri"))

stirling_t = ("""
{{ if .JSON.Bool "cards.stirling.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.stirling.enabled" }}<span class="size-h6"> / {{ .JSON.Int "cards.stirling.tools" }}</span>', "TOOLS ENABLED")
              + stat('{{ .JSON.String "cards.stirling.version" }}', "VERSION") + stat('{{ .JSON.String "cards.stirling.uptime" }}', "UPTIME") + """</div>
<p class="size-h6 color-subdue">Merge, split, compress, convert, OCR, sign, redact and more. Files are processed on this server and never leave it.</p>
{{ if ne (.JSON.String "cards.stirling.update") "" }}<p class="size-h6 color-primary margin-top-5">Update available: {{ .JSON.String "cards.stirling.update" }}</p>{{ end }}
""" + ctr_line("cards.stirling.ctr") + down("Stirling PDF", "cards.stirling"))

flatnotes_t = ("""
{{ if .JSON.Bool "cards.flatnotes.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.Int "cards.flatnotes.notes" }}', "NOTES") + stat('{{ .JSON.Int "cards.flatnotes.tags" }}', "TAGS")
               + stat('{{ .JSON.Int "cards.flatnotes.week" }}', "EDITED THIS WEEK") + """</div>
<p class="size-h6 color-subdue">{{ if lt (.JSON.Int "cards.flatnotes.last_h") 0 }}No notes yet.{{ else if lt (.JSON.Int "cards.flatnotes.last_h") 48 }}Last edit {{ .JSON.Int "cards.flatnotes.last_h" }}h ago.{{ else }}Last edit {{ div (.JSON.Int "cards.flatnotes.last_h") 24 }}d ago.{{ end }} Plain markdown files; titles are not shown here.</p>
{{ if ne (.JSON.String "cards.flatnotes.update") "" }}<p class="size-h6 color-primary margin-top-5">Update available: {{ .JSON.String "cards.flatnotes.update" }}</p>{{ end }}
<div class="wb-pillrow margin-top-10"><a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8200/new">New note</a><a class="wb-pill" target="_blank" href="http://${HOST_SVC}:8200">Open Flatnotes</a></div>
""" + ctr_line("cards.flatnotes.ctr") + down("Flatnotes", "cards.flatnotes"))

homebox_t = ("""
{{ if .JSON.Bool "cards.homebox.up" }}
<div class="wb-stats margin-bottom-10">""" + stat('{{ .JSON.String "cards.homebox.version" }}', "INSTALLED")
             + stat('{{ .JSON.String "cards.homebox.latest" }}', "LATEST", '{{ if .JSON.Bool "cards.homebox.update" }}color-primary{{ else }}color-positive{{ end }}') + stat('{{ .JSON.String "cards.homebox.released" }}', "RELEASED") + """</div>
<p class="size-h6 {{ if .JSON.Bool "cards.homebox.update" }}color-primary{{ else }}color-positive{{ end }}">{{ if .JSON.Bool "cards.homebox.update" }}A newer version is available.{{ else }}Up to date.{{ end }}</p>
<p class="size-h6 color-subdue margin-top-5">{{ .JSON.String "cards.homebox.message" }}. Item counts need a login, so they are not shown here.</p>
""" + ctr_line("cards.homebox.ctr") + down("Homebox", "cards.homebox"))


def remote_row(label, purpose, url, path):
    return """
<li>
  <div class="flex justify-between gap-10"><span class="text-truncate">{{ if .JSON.Bool "@P@.running" }}<span class="color-positive">&#9679;</span>{{ else }}<span class="color-negative">&#9679;</span>{{ end }} <a class="color-highlight" href="@U@" target="_blank">@L@</a></span><span class="shrink-0 color-subdue">{{ if .JSON.Bool "@P@.running" }}{{ .JSON.String "@P@.status" }}{{ else }}{{ .JSON.String "@P@.state" }}{{ end }}</span></div>
  <div class="color-subdue">@D@{{ if .JSON.Bool "@P@.running" }}{{ if ge (.JSON.Float "@P@.cpu_pct") 0.0 }} &middot; {{ .JSON.Float "@P@.cpu_pct" }}% CPU &middot; {{ .JSON.Int "@P@.mem_mb" }} MB{{ end }}{{ end }}</div>
</li>
""".replace("@P@", path).replace("@U@", url).replace("@L@", label).replace("@D@", purpose)


remote_t = ('<ul class="list list-gap-10 size-h6">' + remote_row("Picard (MusicBrainz tagger)", "Music tagging in the browser", "http://${HOST_SVC}:8086", "cards.remote.ctr_picard")
            + remote_row("Firefox (remote browser)", "A browser running on the server, for reaching internal pages", "http://${HOST_SVC}:5800", "cards.remote.ctr_firefox")
            + remote_row("Vaultwarden", "Password vault (reached over Tailscale only); stopped on purpose", "https://services.example.ts.net:8443", "cards.remote.ctr_vault") + "</ul>")



rustybox = """        - type: custom-api
          title: RustyBox
          title-url: https://${HOST_SVC}:8443
          cache: 30s
          url: http://${HOST_SVC}:8088/api/summary
          template: |
            <div class="flex justify-between items-center margin-bottom-10">
              <div>Xbox 360 <span class="color-subdue">library &amp; console manager</span></div>
              <div class="size-h6 color-subdue">v{{ .JSON.String "version" }}</div>
            </div>
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "games" | formatNumber }}</div><div class="size-h6">GAMES</div></div>
              <div><div class="size-h3 color-highlight">{{ printf "%.2f" (div (.JSON.Float "games_bytes") 1099511627776.0) }}<span class="size-h6"> TB</span></div><div class="size-h6">LIBRARY</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "libraries" }}</div><div class="size-h6">LIBRARIES</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "duplicates") 0 }}color-primary{{ else }}color-positive{{ end }}">{{ .JSON.Int "duplicates" }}</div><div class="size-h6">DUPLICATES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "wanted.waiting" }}</div><div class="size-h6">WANTED</div></div>
            </div>
            <ul class="list list-gap-8 size-h6 margin-bottom-10">
            {{ $running := 0 }}
            {{ range .JSON.Array "jobs.running" }}
              {{ $running = add $running 1 }}
              <li>
                <div class="flex justify-between gap-10"><span class="text-truncate">{{ .String "title" }}</span><span class="color-primary shrink-0">{{ printf "%.0f" (.Float "pct") }}%</span></div>
                <div class="color-subdue text-truncate">{{ .String "step" }}</div>
                <div class="wb-progress"><div style="width:{{ printf "%.0f" (.Float "pct") }}%"></div></div>
              </li>
            {{ end }}
            {{ if eq $running 0 }}<li class="color-subdue">Idle &middot; {{ .JSON.Int "downloads.active" }} downloading &middot; {{ .JSON.Int "downloads.importing" }} importing{{ if gt (.JSON.Int "downloads.failed") 0 }} &middot; <span class="color-negative">{{ .JSON.Int "downloads.failed" }} failed</span>{{ end }}{{ if gt (.JSON.Int "jobs.failed_24h") 0 }} &middot; <span class="color-negative">{{ .JSON.Int "jobs.failed_24h" }} job(s) failed today</span>{{ end }}</li>{{ end }}
            </ul>
            {{ if .JSON.Array "latest" }}
            <div class="size-h6 color-subdue margin-bottom-5">RECENTLY ADDED</div>
            <div class="wb-strip">
            {{ range .JSON.Array "latest" }}
              <div class="wb-card">
                <a href="https://${HOST_SVC}:8443/#games?q={{ .String "title_id" }}" target="_blank">
                  {{ if .String "cover" }}<img src="http://${HOST_SVC}:8088/api/covers/{{ .String "cover" }}" alt="" loading="lazy">{{ else }}<div style="aspect-ratio:3/4;display:grid;place-items:center;background:var(--color-widget-background-highlight);border-radius:var(--border-radius)">&#127918;</div>{{ end }}
                  <div class="wb-title">{{ .String "name" }}</div>
                </a>
              </div>
            {{ end }}
            </div>
            {{ end }}
"""

page = "- name: Tools\n  slug: tools\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(rustydisc, 12) + "\n" + block(rustybox, 12) + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Paperless-ngx", "http://paperless.wbhomelab", paperless), 12) + "\n"
page += block(card("BookStack", "http://bookstack.wbhomelab", bookstack), 12) + "\n"
page += "        - type: split-column\n          max-columns: 3\n          widgets:\n"
for title, url, tpl in (("Information library (Kiwix)", "http://${HOST_SVC}:8090", kiwix_t), ("SearXNG", "http://searxng.wbhomelab", searxng_t),
                        ("NOMAD", "http://${HOST_SVC}:8500", nomad_t), ("Education (Kolibri)", "http://${HOST_SVC}:8310", kolibri_t),
                        ("Stirling PDF", "http://${HOST_SVC}:8400", stirling_t), ("Flatnotes", "http://${HOST_SVC}:8200", flatnotes_t),
                        ("Homebox", "http://${HOST_SVC}:8470", homebox_t), ("Remote apps and vault", "http://${HOST_SVC}:5001", remote_t)):
    page += block(card(title, url, tpl), 12) + "\n"
page += "    - size: small\n      widgets:\n" + rel_card

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
