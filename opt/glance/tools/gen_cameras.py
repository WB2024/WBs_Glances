#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/cameras.yml (Frigate live view, recent detections, camera + system status, quick links).
Cameras are discovered by glance-admin from Frigate's config, so adding a camera in Frigate adds a live tile here with no edit.
Re-runnable: python3 /opt/glance/tools/gen_cameras.py [output-path]"""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/cameras.yml"
GA = "http://${HOST_SVC}:3005"
FR = "http://${HOST_AUTO}:5000"            # Frigate internal API: the browser loads streams and thumbnails straight from it (LAN only)


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def card(title, url, template, cache="20s", extra=""):
    return ("        - type: custom-api\n          title: %s\n          title-url: %s\n%s          cache: %s\n          url: %s/api/cameras/summary\n"
            "          template: |\n%s\n") % (title, url, extra, cache, GA, block(template, 12))


AGE = '{{ if lt (@X@) 1 }}just now{{ else if lt (@X@) 90 }}{{ @X@ }} min ago{{ else if lt (@X@) 2880 }}{{ div (@X@) 60 }}h ago{{ else }}{{ div (@X@) 1440 }}d ago{{ end }}'

live = """
<div class="wb-cams">
{{ range .JSON.Array "cameras" }}
  <div class="wb-cam{{ if not (.Bool "online") }} wb-cam-off{{ end }}">
    <a href="https://${HOST_AUTO}:8971" target="_blank" title="Open {{ .String "name" }} in Frigate">
      <img class="wb-cam-img" alt="{{ .String "name" }}"
           src="@FR@/api/{{ .String "name" }}/latest.jpg?h=540"
           data-still="@FR@/api/{{ .String "name" }}/latest.jpg?h=540"
           data-live-src="@FR@/api/{{ .String "name" }}?fps=5&h=540">
    </a>
    <div class="wb-cam-bar">
      <span class="{{ if .Bool "online" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span>
      <span class="color-highlight">{{ .String "name" }}</span>
      <span class="color-subdue size-h6">{{ if .Bool "online" }}{{ .Float "camera_fps" }} fps{{ else }}offline{{ end }}{{ if .Bool "recording" }} &middot; recording{{ end }}</span>
      <span class="wb-cam-live size-h6">LIVE</span>
    </div>
  </div>
{{ else }}<p class="color-subdue">No cameras reported by Frigate.</p>{{ end }}
</div>
""".replace("@FR@", FR)

recent = """
<div class="wb-strip">
{{ range .JSON.Array "recent" }}
  <div class="wb-card" style="flex-basis:12rem">
    <a href="https://${HOST_AUTO}:8971" target="_blank">
      <img src="@FR@/api/events/{{ .String "id" }}/thumbnail.jpg" alt="" loading="lazy" style="aspect-ratio:16/10">
      <div class="wb-title">{{ .String "label" }}{{ if ne (.String "sub") "" }} &middot; {{ .String "sub" }}{{ end }}</div>
      <div class="wb-sub">{{ .String "camera" }} &middot; AGE{{ if .Bool "ongoing" }} &middot; now{{ else if gt (.Int "seconds") 0 }} &middot; {{ .Int "seconds" }}s{{ end }}{{ if gt (.Int "score") 0 }} &middot; {{ .Int "score" }}%{{ end }}</div>
    </a>
  </div>
{{ else }}<p class="color-subdue size-h6">No detections recorded yet.</p>{{ end }}
</div>
""".replace("@FR@", FR).replace("AGE", AGE.replace("@X@", '.Int "age_min"'))


by_label = """
{{ range .JSON.Array "by_label" }}
<div class="flex justify-between size-h6 margin-bottom-5"><span class="color-highlight" style="text-transform:uppercase;letter-spacing:0.05em">{{ .String "label" }}</span><span class="color-subdue">{{ .Int "count_24h" }} in the last 24 h &middot; newest first</span></div>
<div class="wb-strip margin-bottom-15">
{{ range .Array "events" }}
  <div class="wb-card" style="flex-basis:12rem">
    <a href="@FR@/api/events/{{ .String "id" }}/snapshot.jpg" target="_blank">
      <img src="@FR@/api/events/{{ .String "id" }}/thumbnail.jpg" alt="" loading="lazy" style="aspect-ratio:16/10">
      <div class="wb-title">{{ if ne (.String "sub") "" }}{{ .String "sub" }}{{ else }}{{ .String "label" }}{{ end }}</div>
      <div class="wb-sub">{{ .String "camera" }} &middot; AGE{{ if gt (.Int "seconds") 0 }} &middot; {{ .Int "seconds" }}s{{ end }}{{ if gt (.Int "score") 0 }} &middot; {{ .Int "score" }}%{{ end }}</div>
    </a>
  </div>
{{ end }}
</div>
{{ else }}<p class="color-subdue size-h6">Nothing detected yet.</p>{{ end }}
""".replace("@FR@", FR).replace("AGE", AGE.replace("@X@", '.Int "age_min"'))

explorer = """        - type: html
          title: Search detections by date and time
          source: |
            <div data-wb="cam-events" data-wb-noindex data-frigate="@FR@" data-frigate-ui="https://${HOST_AUTO}:8971"></div>
""".replace("@FR@", FR)

status = """
<div class="wb-stats margin-bottom-10">
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "events_24h" }}</div><div class="size-h6">DETECTIONS 24H</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Float "inference_ms" }}<span class="size-h6"> ms</span></div><div class="size-h6">INFERENCE &middot; {{ .JSON.String "detector" }}</div></div>
  <div><div class="size-h3 color-highlight">{{ .JSON.Int "cpu_pct" }}%</div><div class="size-h6">FRIGATE CPU</div></div>
</div>
{{ range .JSON.Array "labels_24h" }}<span class="wb-pill">{{ .String "label" }} {{ .Int "count" }}</span>{{ end }}
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">ACTIVITY &middot; LAST 24 H{{ if gt (.JSON.Int "peak_n") 0 }} &middot; busiest {{ .JSON.String "peak_hour" }}:00 ({{ .JSON.Int "peak_n" }}){{ end }}</div>
<div class="wb-bars">{{ range .JSON.Array "hourly" }}<div class="wb-bar" title="{{ .String "h" }}:00 &middot; {{ .Int "n" }} detections"><div style="height:{{ .Int "pct" }}%"></div></div>{{ end }}</div>
<div class="flex justify-between size-h6 color-subdue"><span>24 h ago</span><span>now</span></div>
<div class="flex justify-between size-h6 margin-top-15"><span class="color-subdue">RECORDINGS &middot; {{ .JSON.Int "retain_days" }} days kept</span><span>{{ .JSON.Float "storage.used_tb" }} / {{ .JSON.Float "storage.total_tb" }} TB &middot; {{ .JSON.Int "storage.pct" }}%</span></div>
<div class="progress-bar margin-bottom-8"><div class="progress-value{{ if gt (.JSON.Int "storage.pct") 85 }} progress-value-notice{{ end }}" style="--percent: {{ .JSON.Int "storage.pct" }}"></div></div>
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">Frigate</span><span>{{ .JSON.String "version" }}{{ if .JSON.Bool "update" }} <span class="color-primary">&middot; update {{ .JSON.String "latest" }}</span>{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">uptime</span><span>{{ .JSON.Float "uptime_d" }} days</span></li>
</ul>
{{ range .JSON.Array "cameras" }}
<div class="size-h6 color-subdue margin-top-15 margin-bottom-5">CAMERA &middot; {{ .String "name" }}</div>
<ul class="list list-gap-4 size-h6">
  <li class="flex justify-between gap-10"><span class="color-subdue">stream</span><span class="{{ if .Bool "online" }}color-positive{{ else }}color-negative{{ end }}">{{ if .Bool "online" }}online &middot; {{ .Float "camera_fps" }} fps{{ else }}offline{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">detection</span><span>{{ .Int "width" }}&times;{{ .Int "height" }} &middot; {{ .Float "detect_fps" }} fps{{ if gt (.Float "skipped_fps") 0.0 }} <span class="color-negative">&middot; {{ .Float "skipped_fps" }} skipped</span>{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">tracks</span><span class="text-truncate">{{ .String "objects" }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">recording</span><span>{{ if .Bool "recording" }}{{ .Float "rec_gb" }} GB{{ else }}off{{ end }}</span></li>
  <li class="flex justify-between gap-10"><span class="color-subdue">seen in 24 h</span><span>{{ .Int "seen_24h" }} detections</span></li>
</ul>
{{ end }}
"""

links = """        - type: bookmarks
          title: Quick links
          groups:
            - links:
                - { title: "Frigate",                url: "https://${HOST_AUTO}:8971", icon: di:frigate }
                - { title: "Frigate (internal, no login)", url: "http://${HOST_AUTO}:5000", icon: di:frigate }
                - { title: "Home Assistant",         url: "http://${HOST_AUTO}:8123", icon: di:home-assistant }
                - { title: "Dockge · automation",    url: "http://${HOST_AUTO}:5001", icon: di:dockge }
"""

page = "- name: Cameras\n  slug: cameras\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += card("Live", "https://${HOST_AUTO}:8971", live, cache="1m") + "\n"
page += card("Recent detections", "https://${HOST_AUTO}:8971", recent, cache="30s") + "\n"
page += card("Detections by type", "https://${HOST_AUTO}:8971", by_label, cache="2m") + "\n"
page += explorer + "\n"
page += "    - size: small\n      widgets:\n" + card("Frigate", "https://${HOST_AUTO}:8971", status, cache="20s") + "\n" + links

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
