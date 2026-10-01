#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/video.yml
  open rows : Jellyfin continue watching, Jellyfin recently added, Movies that feel like
  restricted: Private B, Immich (PIN-locked with css-class wb-restricted)
Re-runnable: python3 /opt/glance/tools/gen_video.py [output-path]
Private B/Immich data and thumbnails come through glance-admin (:3005): their keys never reach the page."""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/video.yml"
JF = "http://${HOST_JELLY}:8096"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


continue_watching = """        - type: custom-api
          title: Continue watching
          title-url: @JF@
          cache: 2m
          url: @JF@/Users/${JELLYFIN_USER_ID}/Items/Resume?Limit=14&MediaTypes=Video&Fields=ProductionYear
          headers:
            X-Emby-Token: ${JELLYFIN_KEY}
            Accept: application/json
          template: |
            <div class="wb-strip">
            {{ range .JSON.Array "Items" }}
              {{ $img := .String "Id" }}{{ if .Exists "SeriesId" }}{{ $img = .String "SeriesId" }}{{ end }}
              <div class="wb-card">
                <a href="@JF@/web/#/details?id={{ .String "Id" }}" target="_blank">
                  <img src="@JF@/Items/{{ $img }}/Images/Primary?maxHeight=330&quality=85" alt="" loading="lazy">
                  <div class="wb-progress"><div style="width:{{ printf "%.0f" (.Float "UserData.PlayedPercentage") }}%"></div></div>
                  <div class="wb-title">{{ if .Exists "SeriesName" }}{{ .String "SeriesName" }}{{ else }}{{ .String "Name" }}{{ end }}</div>
                  <div class="wb-sub">{{ if .Exists "SeriesName" }}S{{ .Int "ParentIndexNumber" }}E{{ .Int "IndexNumber" }} &middot; {{ .String "Name" }}{{ else }}{{ .Int "ProductionYear" }} &middot; {{ printf "%.0f" (.Float "UserData.PlayedPercentage") }}% watched{{ end }}</div>
                </a>
              </div>
            {{ else }}
              <p class="color-subdue size-h6">Nothing in progress</p>
            {{ end }}
            </div>
""".replace("@JF@", JF)

recently_added = """        - type: custom-api
          title: Recently added
          title-url: @JF@
          cache: 5m
          url: @JF@/Users/${JELLYFIN_USER_ID}/Items/Latest?Limit=20&IncludeItemTypes=Movie,Series&Fields=ProductionYear,DateCreated
          headers:
            X-Emby-Token: ${JELLYFIN_KEY}
            Accept: application/json
          template: |
            <div class="wb-strip">
            {{ range .JSON.Array "" }}
              <div class="wb-card">
                <a href="@JF@/web/#/details?id={{ .String "Id" }}" target="_blank">
                  <img src="@JF@/Items/{{ .String "Id" }}/Images/Primary?maxHeight=330&quality=85" alt="" loading="lazy">
                  <div class="wb-title">{{ .String "Name" }}</div>
                  <div class="wb-sub">{{ if .Exists "ProductionYear" }}{{ .Int "ProductionYear" }} &middot; {{ end }}{{ .String "Type" }}</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing added yet</p>{{ end }}
            </div>
""".replace("@JF@", JF)

movies_feel = """        - type: custom-api
          title: Movies that feel like
          title-url: http://${HOST_SVC}:8095/movies/
          cache: 20m
          url: http://${HOST_SVC}:8095/api/hot/movies/?limit=14
          template: |
            <div class="wb-strip">
            {{ range .JSON.Array "" }}
              <div class="wb-card square">
                <a href="{{ .String "url" }}" target="_blank">
                  <img src="{{ .String "image" }}" alt="" loading="lazy">
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ .Int "rec_count" }} rec{{ if ne (.Int "rec_count") 1 }}s{{ end }} &middot; &#9650; {{ .Int "score" }}</div>
                </a>
              </div>
            {{ else }}
              <p class="color-subdue size-h6">No posts with a cached image yet. Give the sync a few minutes.</p>
            {{ end }}
            </div>
"""

privb = """        - type: custom-api
          title: Private B
          title-url: http://${HOST_DEVUAN}:9999
          css-class: wb-restricted
          cache: 2m
          url: @GA@/api/privb/summary
          template: |
            <div class="wb-stats margin-bottom-15">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.scenes" | formatNumber }}</div><div class="size-h6">SCENES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.images" | formatNumber }}</div><div class="size-h6">IMAGES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.performers" | formatNumber }}</div><div class="size-h6">PERFORMERS</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.studios" | formatNumber }}</div><div class="size-h6">STUDIOS</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.tags" | formatNumber }}</div><div class="size-h6">TAGS</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Float "stats.size_tb" }}<span class="size-h6"> TB</span></div><div class="size-h6">SCENES SIZE</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "stats.hours" | formatNumber }}<span class="size-h6"> h</span></div><div class="size-h6">PLAY TIME</div></div>
            </div>
            <div class="size-h6 color-subdue margin-bottom-5">RECENTLY ADDED &middot; Private B {{ .JSON.String "version" }}</div>
            <div class="wb-strip">
            {{ range .JSON.Array "recent" }}
              <div class="wb-card">
                <a href="http://${HOST_DEVUAN}:9999/scenes/{{ .String "id" }}" target="_blank">
                  <img data-src="@GA@/api/privb/cover/{{ .String "id" }}" alt="" loading="lazy" style="aspect-ratio:16/9">
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ if ne (.String "studio") "" }}{{ .String "studio" }} &middot; {{ end }}{{ .Int "minutes" }} min</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing yet</p>{{ end }}
            </div>
""".replace("@GA@", GA)

immich = """        - type: custom-api
          title: Immich
          title-url: ${IMMICH_URL}
          css-class: wb-restricted
          cache: 2m
          url: @GA@/api/immich/summary
          template: |
            <div class="wb-stats margin-bottom-15">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "photos" | formatNumber }}</div><div class="size-h6">PHOTOS</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "videos" | formatNumber }}</div><div class="size-h6">VIDEOS</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "disk.percent") 85 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "disk.percent" }}%</div><div class="size-h6">DISK &middot; {{ .JSON.String "disk.used" }} / {{ .JSON.String "disk.size" }}</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "jobs.active" }}<span class="color-subdue">/</span>{{ .JSON.Int "jobs.waiting" }}</div><div class="size-h6">JOBS ACTIVE / WAITING</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "jobs.failed") 0 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "jobs.failed" }}</div><div class="size-h6">JOBS FAILED</div></div>
            </div>
            <div class="size-h6 color-subdue margin-bottom-5">LATEST &middot; Immich {{ .JSON.String "version" }}</div>
            <div class="wb-strip">
            {{ range .JSON.Array "recent" }}
              <div class="wb-card square">
                <a href="${IMMICH_URL}/photos/{{ .String "id" }}" target="_blank">
                  <img data-src="@GA@/api/immich/cover/{{ .String "id" }}" alt="" loading="lazy">
                  <div class="wb-sub">{{ if .Bool "video" }}video &middot; {{ end }}{{ .String "taken" | parseTime "rfc3339" | formatTime "2 Jan 2006" }}</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing yet</p>{{ end }}
            </div>
""".replace("@GA@", GA)

jellyfin_stats = """        - type: custom-api
          title: Jellyfin library
          title-url: @JF@
          cache: 10m
          url: @JF@/Items/Counts
          headers:
            X-Emby-Token: ${JELLYFIN_KEY}
            Accept: application/json
          template: |
            <div class="wb-stats">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "MovieCount" | formatNumber }}</div><div class="size-h6">MOVIES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "SeriesCount" | formatNumber }}</div><div class="size-h6">SERIES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "EpisodeCount" | formatNumber }}</div><div class="size-h6">EPISODES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "BoxSetCount" }}</div><div class="size-h6">SETS</div></div>
            </div>
""".replace("@JF@", JF)

page = "- name: Video\n  slug: video\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
for w in (continue_watching, recently_added, movies_feel, privb, immich):
    page += block(w, 8) + "\n"
page += "    - size: small\n      widgets:\n" + block(jellyfin_stats, 8)

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
