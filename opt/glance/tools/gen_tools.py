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



page = "- name: Tools\n  slug: tools\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += rustydisc + "\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(card("Paperless-ngx", "http://paperless.wbhomelab", paperless), 12) + "\n"
page += block(card("BookStack", "http://bookstack.wbhomelab", bookstack), 12) + "\n"
page += card("Other tools", "http://${HOST_SVC}:5001", tiles) + "\n"
page += "    - size: small\n      widgets:\n" + rel_card

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
