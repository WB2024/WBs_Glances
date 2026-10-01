#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/audio.yml (Navidrome shelves, Audiobookshelf rows, Songs that feel like, side stats).
Re-runnable: python3 /opt/glance/tools/gen_audio.py [output-path]   -- Glance reloads when the file changes.
Covers come through glance-admin (:3005) so no Navidrome token / Audiobookshelf key is ever put in the page."""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/audio.yml"
ND = "http://${HOST_SVC}:4534"
GA = "http://${HOST_SVC}:3005"
CRED = "u=${NAVIDROME_USER}&t=${NAVIDROME_TOKEN}&s=${NAVIDROME_SALT}&v=1.16.1&c=glance&f=json"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def nd_shelf(title, kind, url_hash, cache, sub):
    return """        - type: custom-api
          title: %s
          title-url: %s/app/#/album/%s
          cache: %s
          url: %s/rest/getAlbumList2.view?type=%s&size=20&%s
          template: |
            <div class="wb-strip">
            {{ range .JSON.Array "subsonic-response.albumList2.album" }}
              <div class="wb-card square">
                <a href="%s/app/#/album/{{ .String "id" }}/show" target="_blank">
                  <img src="%s/api/nd/cover/{{ .String "coverArt" }}?s=300" alt="" loading="lazy">
                  <div class="wb-title">{{ .String "name" }}</div>
                  <div class="wb-sub">%s</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing here yet</p>{{ end }}
            </div>
""" % (title, ND, url_hash, cache, ND, kind, CRED, ND, GA, sub)


ARTIST_YEAR = '{{ .String "artist" }}{{ if .Exists "year" }} &middot; {{ .Int "year" }}{{ end }}'
ARTIST_PLAYED = '{{ .String "artist" }} &middot; <span {{ .String "played" | parseTime "rfc3339" | toRelativeTime }}></span>'
ARTIST_PLAYS = '{{ .String "artist" }} &middot; {{ .Int "playCount" }} plays'

newest = nd_shelf("Recently added", "newest", "newest", "5m", ARTIST_YEAR)
recent = nd_shelf("Recently played", "recent", "recent", "2m", ARTIST_PLAYED)
frequent = nd_shelf("Most played", "frequent", "frequent", "10m", ARTIST_PLAYS)
discover = nd_shelf("Discover from library", "random", "", "1m", ARTIST_YEAR).replace(
    "title-url: %s/app/#/album/\n" % ND, "title-url: %s/app/#/albums\n" % ND)


def abs_row(title, group, css_class=None):
    css = "          css-class: %s\n" % css_class if css_class else ""
    return """        - type: custom-api
          title: %s
          title-url: http://${HOST_SVC}:13378
%s          cache: 2m
          url: %s/api/abs/continue?group=%s&limit=12
          subrequests:
            recent:
              url: %s/api/abs/recent?group=%s&limit=16
          template: |
            <div class="size-h6 color-subdue margin-bottom-5">CONTINUE LISTENING</div>
            <div class="wb-strip margin-bottom-15">
            {{ range .JSON.Array "" }}
              <div class="wb-card square">
                <a href="http://${HOST_SVC}:13378/item/{{ .String "id" }}" target="_blank">
                  <img src="%s/api/abs/cover/{{ .String "id" }}?s=300" alt="" loading="lazy">
                  <div class="wb-progress"><div style="width:{{ .Int "progress" }}%%"></div></div>
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ if ne (.String "sub") "" }}{{ .String "sub" }}{{ else }}{{ .String "author" }}{{ end }} &middot; {{ .Int "progress" }}%%</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing in progress</p>{{ end }}
            </div>
            <div class="size-h6 color-subdue margin-bottom-5">RECENTLY ADDED</div>
            <div class="wb-strip">
            {{ range (.Subrequest "recent").JSON.Array "" }}
              <div class="wb-card square">
                <a href="http://${HOST_SVC}:13378/item/{{ .String "id" }}" target="_blank">
                  <img src="%s/api/abs/cover/{{ .String "id" }}?s=300" alt="" loading="lazy">
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ if ne (.String "author") "" }}{{ .String "author" }}{{ else }}{{ .String "library" }}{{ end }}</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing added yet</p>{{ end }}
            </div>
""" % (title, css, GA, group, GA, group, GA, GA)


def abs_open(title):
    """Open libraries: continue listening + one random row per library (labelled with the library name)."""
    return """        - type: custom-api
          title: %s
          title-url: http://${HOST_SVC}:13378
          cache: 2m
          url: %s/api/abs/continue?group=open&limit=12
          subrequests:
            shelves:
              url: %s/api/abs/shelves?group=open&n=14
          template: |
            <div class="size-h6 color-subdue margin-bottom-5">CONTINUE LISTENING</div>
            <div class="wb-strip margin-bottom-15">
            {{ range .JSON.Array "" }}
              <div class="wb-card square">
                <a href="http://${HOST_SVC}:13378/item/{{ .String "id" }}" target="_blank">
                  <img src="%s/api/abs/cover/{{ .String "id" }}?s=300" alt="" loading="lazy">
                  <div class="wb-progress"><div style="width:{{ .Int "progress" }}%%"></div></div>
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ if ne (.String "sub") "" }}{{ .String "sub" }}{{ else }}{{ .String "author" }}{{ end }} &middot; {{ .Int "progress" }}%%</div>
                </a>
              </div>
            {{ else }}<p class="color-subdue size-h6">Nothing in progress</p>{{ end }}
            </div>
            {{ range (.Subrequest "shelves").JSON.Array "" }}
            <div class="size-h6 color-subdue margin-bottom-5"><a href="http://${HOST_SVC}:13378/library/{{ .String "id" }}" target="_blank">{{ .String "name" }}</a> &middot; random from {{ .Int "total" }}</div>
            <div class="wb-strip margin-bottom-15">
            {{ range .Array "items" }}
              <div class="wb-card square">
                <a href="http://${HOST_SVC}:13378/item/{{ .String "id" }}" target="_blank">
                  <img src="%s/api/abs/cover/{{ .String "id" }}?s=300" alt="" loading="lazy">
                  <div class="wb-title">{{ .String "title" }}</div>
                  <div class="wb-sub">{{ .String "author" }}</div>
                </a>
              </div>
            {{ end }}
            </div>
            {{ end }}
""" % (title, GA, GA, GA, GA)


audiobookshelf = abs_open("Audiobookshelf")
audiobookshelf_r = abs_row("Audiobookshelf - More", "restricted", css_class="wb-restricted")
# locked rows must not fetch their images until unlocked (wb-restricted.js moves data-src to src)
audiobookshelf_r = audiobookshelf_r.replace("<img src=", "<img data-src=")
assert "<img src=" not in audiobookshelf_r

feel = """        - type: custom-api
          title: Songs that feel like
          title-url: http://${HOST_SVC}:8095/music/
          cache: 20m
          url: http://${HOST_SVC}:8095/api/hot/music/?limit=14
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

nd_stats = """        - type: custom-api
          title: Navidrome
          title-url: %s
          cache: 10m
          url: %s/rest/getScanStatus.view?%s
          template: |
            {{ $s := .JSON }}
            <div class="wb-stats">
              <div><div class="size-h3 color-highlight">{{ $s.Int "subsonic-response.scanStatus.count" | formatNumber }}</div><div class="size-h6">TRACKS</div></div>
              <div><div class="size-h3 color-highlight">{{ $s.Int "subsonic-response.scanStatus.folderCount" | formatNumber }}</div><div class="size-h6">FOLDERS</div></div>
              <div><div class="size-h3 {{ if $s.Bool "subsonic-response.scanStatus.scanning" }}color-primary{{ else }}color-positive{{ end }}">{{ if $s.Bool "subsonic-response.scanStatus.scanning" }}scanning{{ else }}idle{{ end }}</div><div class="size-h6">SCANNER</div></div>
            </div>
            <p class="size-h6 color-subdue margin-top-10">last scan <span {{ $s.String "subsonic-response.scanStatus.lastScan" | parseTime "rfc3339" | toRelativeTime }}></span></p>
""" % (ND, ND, CRED)

abs_stats = """        - type: custom-api
          title: Audiobookshelf library
          title-url: http://${HOST_SVC}:13378
          cache: 10m
          url: %s/api/abs/stats
          template: |
            <div class="wb-stats">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "books" | formatNumber }}</div><div class="size-h6">AUDIOBOOKS</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "podcasts" | formatNumber }}</div><div class="size-h6">PODCAST SHOWS</div></div>
            </div>
""" % GA

mtfl_stats = """        - type: custom-api
          title: MediaThatFeelsLike
          title-url: http://${HOST_SVC}:8095
          cache: 15m
          url: http://${HOST_SVC}:8095/api/stats/
          template: |
            <div class="wb-stats">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "movies" | formatNumber }}</div><div class="size-h6">MOVIES</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "music" | formatNumber }}</div><div class="size-h6">MUSIC</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "recommendations" | formatNumber }}</div><div class="size-h6">RECS</div></div>
            </div>
            {{ with .JSON.String "last_synced" }}<p class="size-h6 color-subdue margin-top-10">synced <span {{ . | parseTime "rfc3339" | toRelativeTime }}></span></p>{{ end }}
"""

page = "- name: Audio\n  slug: audio\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
for w in (newest, recent, frequent, discover, audiobookshelf, feel, audiobookshelf_r):
    page += block(w, 8) + "\n"
page += "    - size: small\n      widgets:\n"
for w in (nd_stats, abs_stats, mtfl_stats):
    page += block(w, 8) + "\n"

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
