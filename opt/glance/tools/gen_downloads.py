#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/downloads.yml (Radarr / Sonarr / Lidarr / Private A rows share one template per media type).
Re-runnable: python3 /opt/glance/tools/gen_downloads.py   -- Glance reloads automatically when the file changes.
All hosts and keys come from /opt/glance/.env via ${VAR}; nothing secret is written into the output."""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/downloads.yml"
UPCOMING_DAYS = 30


def ind(text, n):
    return textwrap.indent(textwrap.dedent(text).strip("\n"), " " * n)


# ----------------------------------------------------------------------------- shared template pieces
QUEUE_LI = """
{{ range .JSON.Array "records" }}
  {{ $left := 0.0 }}{{ if gt (.Float "size") 0.0 }}{{ $left = div (.Float "sizeleft") (.Float "size") }}{{ end }}
  <li>
    <div class="flex justify-between gap-10"><span class="text-truncate">@@TITLE@@</span><span class="shrink-0 {{ if eq (.String "trackedDownloadState") "importFailed" }}color-negative{{ else }}color-subdue{{ end }}">{{ .String "trackedDownloadState" }}</span></div>
    <div class="wb-progress"><div style="width:{{ printf "%.0f" (mul (sub 1.0 $left) 100) }}%"></div></div>
  </li>
{{ else }}<li class="color-subdue">Nothing downloading</li>{{ end }}
"""

SHELL = """
<div class="flex gap-25" style="flex-wrap:wrap">
  <div style="flex:0 0 24rem;max-width:100%;min-width:0">
    <div class="wb-stats margin-bottom-10">
@@STATS@@
    </div>
    <ul class="list list-gap-8 size-h6">
@@QUEUE@@
    </ul>
@@EXTRA@@
  </div>
  <div class="grow" style="flex-basis:20rem;min-width:0">
    <div class="size-h6 color-subdue margin-bottom-5">UPCOMING &middot; next @@DAYS@@ days</div>
@@UPCOMING@@
  </div>
</div>
"""

STAT = '      <div><div class="size-h3 color-highlight">@@VALUE@@</div><div class="size-h6">@@LABEL@@</div></div>'


def stat(value, label, warn=None):
    cls = "color-highlight"
    if warn:
        cls = "{{ if gt (%s) 0 }}color-negative{{ else }}color-highlight{{ end }}" % warn
    return ('      <div><div class="size-h3 %s">%s</div><div class="size-h6">%s</div></div>' % (cls, value, label))


def dates(path, extra_params=""):
    return ('{{ $start := now | formatTime "2006-01-02" }}{{ $end := offsetNow "%dh" | formatTime "2006-01-02" }}\n'
            '{{ $cal := newRequest "@@BASE@@%s" | withParameter "start" $start | withParameter "end" $end%s '
            '| withHeader "X-Api-Key" (.Options.StringOr "key" "") | getResponse }}\n' % (UPCOMING_DAYS * 24, path, extra_params))


# ----------------------------------------------------------------------------- per-type bodies
def movie_body():
    upcoming = """
{{ $items := $cal.JSON.Array "" }}
{{ if $items }}
<div class="wb-strip">
{{ range sortByString "digitalRelease" "asc" $items }}
  {{ $poster := "" }}{{ range .Array "images" }}{{ if eq (.String "coverType") "poster" }}{{ $poster = .String "remoteUrl" }}{{ end }}{{ end }}{{ $poster = replaceAll "/original/" "/w342/" $poster }}
  {{ $when := .String "digitalRelease" }}{{ if eq $when "" }}{{ $when = .String "physicalRelease" }}{{ end }}{{ if eq $when "" }}{{ $when = .String "inCinemas" }}{{ end }}
  <div class="wb-card">
    <a href="@@UI@@/movie/{{ .String "titleSlug" }}" target="_blank">
      <img src="{{ $poster }}" alt="" loading="lazy">
      <div class="wb-title">{{ .String "title" }}</div>
      <div class="wb-sub">{{ if ne $when "" }}{{ $when | parseTime "rfc3339" | formatTime "2 Jan" }}{{ end }}{{ if .Bool "hasFile" }} &middot; <span class="color-positive">have it</span>{{ end }}</div>
    </a>
  </div>
{{ end }}
</div>
{{ else }}<p class="color-subdue size-h6">Nothing scheduled</p>{{ end }}
"""
    stats = "\n".join([stat('{{ .JSON.Int "totalRecords" }}', "QUEUE"),
                       stat('{{ (.Subrequest "missing").JSON.Int "totalRecords" }}', "MISSING")])
    title = '{{ if .Exists "movie.title" }}{{ .String "movie.title" }}{{ else }}{{ .String "title" }}{{ end }}'
    return dates("/api/v3/calendar"), stats, QUEUE_LI.replace("@@TITLE@@", title), upcoming, ""


def series_body():
    upcoming = """
{{ $items := $cal.JSON.Array "" }}
{{ if $items }}
<div class="wb-strip">
{{ range sortByString "airDateUtc" "asc" $items }}
  {{ $poster := "" }}{{ range .Array "series.images" }}{{ if eq (.String "coverType") "poster" }}{{ $poster = .String "remoteUrl" }}{{ end }}{{ end }}{{ $poster = replaceAll "/original/" "/w342/" $poster }}
  <div class="wb-card">
    <a href="@@UI@@/series/{{ .String "series.titleSlug" }}" target="_blank">
      <img src="{{ $poster }}" alt="" loading="lazy">
      <div class="wb-title">{{ .String "series.title" }}</div>
      <div class="wb-sub">S{{ .Int "seasonNumber" }}E{{ .Int "episodeNumber" }} &middot; {{ .String "airDateUtc" | parseTime "rfc3339" | formatTime "Mon 2 Jan" }}</div>
    </a>
  </div>
{{ end }}
</div>
{{ else }}<p class="color-subdue size-h6">Nothing scheduled</p>{{ end }}
"""
    stats = "\n".join([stat('{{ .JSON.Int "totalRecords" }}', "QUEUE"),
                       stat('{{ (.Subrequest "missing").JSON.Int "totalRecords" }}', "MISSING")])
    title = ('{{ if .Exists "series.title" }}{{ .String "series.title" }}{{ if .Exists "episode.seasonNumber" }} '
             'S{{ .Int "episode.seasonNumber" }}E{{ .Int "episode.episodeNumber" }}{{ end }}{{ else }}{{ .String "title" }}{{ end }}')
    return dates("/api/v3/calendar", ' | withParameter "includeSeries" "true"'), stats, QUEUE_LI.replace("@@TITLE@@", title), upcoming, ""


def album_body():
    upcoming = """
{{ $items := $cal.JSON.Array "" }}
{{ if $items }}
<div class="wb-strip">
{{ range sortByString "releaseDate" "asc" $items }}
  {{ $fallback := "" }}{{ range .Array "images" }}{{ if eq (.String "coverType") "cover" }}{{ $fallback = .String "remoteUrl" }}{{ end }}{{ end }}
  <div class="wb-card square">
    <a href="@@UI@@/artist/{{ .String "artist.foreignArtistId" }}" target="_blank">
      <img src="https://coverartarchive.org/release-group/{{ .String "foreignAlbumId" }}/front-250" onerror="this.onerror=null;this.src='{{ $fallback }}'" alt="" loading="lazy">
      <div class="wb-title">{{ .String "title" }}</div>
      <div class="wb-sub">{{ .String "artist.artistName" }} &middot; {{ .String "releaseDate" | parseTime "rfc3339" | formatTime "2 Jan" }}</div>
    </a>
  </div>
{{ end }}
</div>
{{ else }}<p class="color-subdue size-h6">Nothing scheduled</p>{{ end }}
"""
    stats = "\n".join([stat('{{ .JSON.Int "totalRecords" }}', "QUEUE"),
                       stat('{{ (.Subrequest "missing").JSON.Int "totalRecords" }}', "MISSING"),
                       stat('{{ (.Subrequest "cutoff").JSON.Int "totalRecords" }}', "UPGRADABLE")])
    title = '{{ if .Exists "artist.artistName" }}{{ .String "artist.artistName" }} &ndash; {{ .String "album.title" }}{{ else }}{{ .String "title" }}{{ end }}'
    extra = """
    {{ $ld := newRequest "http://${HOST_SVC}:8690/api/status" | getResponse }}
    <div class="size-h6 color-subdue margin-top-15 margin-bottom-5">WBS_LIDARRDONS</div>
    <div class="wb-stats">
      <div><div class="size-h3 color-highlight">{{ $ld.JSON.Int "wanted" | formatNumber }}</div><div class="size-h6">WANTED</div></div>
      <div><div class="size-h3 color-highlight">{{ $ld.JSON.Int "cutoff" }}</div><div class="size-h6">UPGRADES</div></div>
      <div><div class="size-h3 {{ if gt ($ld.JSON.Int "stuck") 0 }}color-negative{{ else }}color-highlight{{ end }}">{{ $ld.JSON.Int "queue" }}<span class="color-subdue">/</span>{{ $ld.JSON.Int "stuck" }}</div><div class="size-h6">QUEUE / STUCK</div></div>
      <div><div class="size-h3 color-highlight">{{ $ld.JSON.Int "grabs24h" }}</div><div class="size-h6">GRABS 24H</div></div>
    </div>
    <ul class="list list-gap-4 margin-top-10 size-h6 color-subdue">
      <li>drip every {{ $ld.JSON.Int "drip_interval_minutes" }} min &middot; last {{ $ld.JSON.String "last_drip" }}</li>
      <li>janitor {{ if $ld.JSON.Bool "janitor_enabled" }}<span class="color-positive">on</span>{{ else }}<span class="color-negative">off</span>{{ end }} &middot; upgrades {{ if $ld.JSON.Bool "upgrade_enabled" }}<span class="color-positive">on</span>{{ else }}<span class="color-negative">off</span>{{ end }} &middot; path fixer {{ $ld.JSON.String "listener" }}</li>
    </ul>
"""
    # cached by glance-admin: Lidarr's calendar takes ~7 s when cold, longer than Glance's 5 s request timeout
    pre = '{{ $cal := newRequest "http://${HOST_SVC}:3005/api/lidarr/calendar" | getResponse }}' + chr(10)
    return pre, stats, QUEUE_LI.replace("@@TITLE@@", title), upcoming, extra


def row(title, kind, base, ui, key, queue_path, missing_path, extra_subs="", css_class=None):
    pre, stats, queue, upcoming, extra = {"movie": movie_body, "series": series_body, "album": album_body}[kind]()
    body = (SHELL.replace("@@STATS@@", stats).replace("@@QUEUE@@", ind(queue, 6))
            .replace("@@EXTRA@@", extra.strip("\n")).replace("@@UPCOMING@@", ind(upcoming, 4)).replace("@@DAYS@@", str(UPCOMING_DAYS)))
    tpl = (pre + body).replace("@@BASE@@", base).replace("@@UI@@", ui)
    if css_class == "wb-restricted":   # locked rows must not fetch their images until unlocked
        tpl = tpl.replace("<img src=", "<img data-src=")
    css = "          css-class: %s\n" % css_class if css_class else ""
    return """        - type: custom-api
          title: %s
          title-url: %s
%s          cache: 2m
          url: %s%s
          headers:
            X-Api-Key: ${%s}
          options:
            key: ${%s}
          subrequests:
            missing:
              url: %s%s
              headers:
                X-Api-Key: ${%s}
%s          template: |
%s
""" % (title, ui, css, base, queue_path, key, key, base, missing_path, key, extra_subs, ind(tpl, 12))


radarr = row("Radarr", "movie", "http://${HOST_SVC}:7878", "http://${HOST_SVC}:7878", "RADARR_KEY",
             "/api/v3/queue?pageSize=8&includeMovie=true&includeUnknownMovieItems=true",
             "/api/v3/wanted/missing?pageSize=1&monitored=true")
sonarr = row("Sonarr", "series", "http://${HOST_SVC}:8989", "http://${HOST_SVC}:8989", "SONARR_KEY",
             "/api/v3/queue?pageSize=8&includeSeries=true&includeEpisode=true&includeUnknownSeriesItems=true",
             "/api/v3/wanted/missing?pageSize=1&monitored=true")
lidarr_sub = """            cutoff:
              url: http://${HOST_SVC}:8686/api/v1/wanted/cutoff?pageSize=1&monitored=true
              headers:
                X-Api-Key: ${LIDARR_KEY}
"""
lidarr = row("Lidarr", "album", "http://${HOST_SVC}:8686", "http://${HOST_SVC}:8686", "LIDARR_KEY",
             "/api/v1/queue?pageSize=8&includeArtist=true&includeAlbum=true",
             "/api/v1/wanted/missing?pageSize=1&monitored=true", extra_subs=lidarr_sub)
priva = row("Private A", "series", "http://${HOST_DEVUAN}:6969", "http://${HOST_DEVUAN}:6969", "PRIVA_KEY",
               "/api/v3/queue?pageSize=8&includeSeries=true&includeEpisode=true&includeUnknownSeriesItems=true",
               "/api/v3/wanted/missing?pageSize=1&monitored=true", css_class="wb-restricted")

sab = """        - type: custom-api
          title: SABnzbd
          title-url: http://${HOST_SVC}:8085
          cache: 30s
          url: http://${HOST_SVC}:8085/api?mode=queue&output=json&apikey=${SABNZBD_KEY}&limit=8
          subrequests:
            history:
              url: http://${HOST_SVC}:8085/api?mode=history&output=json&apikey=${SABNZBD_KEY}&limit=6
          template: |
            {{ $q := .JSON }}
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 {{ if $q.Bool "queue.paused" }}color-negative{{ else }}color-highlight{{ end }}">{{ if $q.Bool "queue.paused" }}paused{{ else }}{{ $q.String "queue.speed" }}B/s{{ end }}</div><div class="size-h6">SPEED</div></div>
              <div><div class="size-h3 color-highlight">{{ $q.Int "queue.noofslots_total" }}</div><div class="size-h6">IN QUEUE</div></div>
              <div><div class="size-h3 color-highlight">{{ $q.String "queue.sizeleft" }}</div><div class="size-h6">REMAINING</div></div>
              <div><div class="size-h3 color-highlight">{{ $q.String "queue.timeleft" }}</div><div class="size-h6">ETA</div></div>
              <div><div class="size-h3 color-highlight">{{ $q.String "queue.diskspace1_norm" }}</div><div class="size-h6">FREE</div></div>
            </div>
            <ul class="list list-gap-8 size-h6 margin-bottom-10">
            {{ range $q.Array "queue.slots" }}
              <li>
                <div class="flex justify-between gap-10"><span class="text-truncate">{{ .String "filename" }}</span><span class="color-subdue shrink-0">{{ .String "percentage" }}% &middot; {{ .String "sizeleft" }} &middot; {{ .String "status" }}</span></div>
                <div class="wb-progress"><div style="width:{{ .String "percentage" }}%"></div></div>
              </li>
            {{ else }}
              <li class="color-subdue">Queue is empty</li>
            {{ end }}
            </ul>
            <div class="size-h6 color-subdue margin-bottom-5">RECENT HISTORY</div>
            <ul class="list list-gap-4 size-h6">
            {{ range (.Subrequest "history").JSON.Array "history.slots" }}
              <li class="flex justify-between gap-10"><span class="text-truncate"><span class="{{ if eq (.String "status") "Completed" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span> {{ .String "name" }}</span><span class="color-subdue shrink-0">{{ .String "category" }} &middot; {{ .String "size" }}</span></li>
            {{ end }}
            </ul>
"""


qbit = """        - type: custom-api
          title: qBittorrent
          title-url: http://${HOST_SVC}:8082
          cache: 20s
          url: http://${HOST_SVC}:8088/api/torrents/live
          template: |
            {{ if .JSON.Bool "online" }}
            <div class="flex justify-between items-center margin-bottom-10">
              <div>Torrents <span class="color-positive">connected</span></div>
              <div class="size-h6 color-subdue">qBittorrent {{ .JSON.String "version" }}</div>
            </div>
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 {{ if gt (.JSON.Float "down") 0.0 }}color-positive{{ else }}color-highlight{{ end }}">{{ printf "%.1f" (div (.JSON.Float "down") 1048576.0) }}<span class="size-h6"> MB/s</span></div><div class="size-h6">DOWN</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Float "up") 0.0 }}color-primary{{ else }}color-highlight{{ end }}">{{ printf "%.1f" (div (.JSON.Float "up") 1048576.0) }}<span class="size-h6"> MB/s</span></div><div class="size-h6">UP</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "counts.downloading" }}</div><div class="size-h6">DOWNLOADING</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "counts.seeding" }}</div><div class="size-h6">SEEDING</div></div>
              <div><div class="size-h3 color-highlight">{{ printf "%.1f" (div (.JSON.Float "free") 1099511627776.0) }}<span class="size-h6"> TB</span></div><div class="size-h6">FREE</div></div>
            </div>
            <ul class="list list-gap-8 size-h6 margin-bottom-10">
            {{ range .JSON.Array "torrents" }}
              {{ $s := .String "state" }}
              <li>
                <div class="flex justify-between gap-10"><span class="text-truncate">{{ .String "name" }}</span><span class="shrink-0 {{ if or (eq $s "error") (eq $s "missingFiles") }}color-negative{{ else }}color-subdue{{ end }}">{{ if or (eq $s "error") (eq $s "missingFiles") }}error{{ else if or (eq $s "uploading") (eq $s "stalledUP") (eq $s "forcedUP") (eq $s "queuedUP") (eq $s "checkingUP") }}seeding{{ else if or (eq $s "pausedDL") (eq $s "pausedUP") (eq $s "stoppedDL") (eq $s "stoppedUP") }}paused{{ else if or (eq $s "metaDL") (eq $s "forcedMetaDL") (eq $s "checkingDL") (eq $s "queuedDL") }}waiting{{ else }}{{ printf "%.0f" (.Float "percent") }}%{{ if gt (.Float "down") 0.0 }} &middot; {{ printf "%.1f" (div (.Float "down") 1048576.0) }} MB/s{{ end }}{{ end }}</span></div>
                {{ if not (or (eq $s "uploading") (eq $s "stalledUP") (eq $s "forcedUP") (eq $s "queuedUP")) }}<div class="wb-progress"><div style="width:{{ printf "%.0f" (.Float "percent") }}%"></div></div>{{ end }}
              </li>
            {{ else }}
              <li class="color-subdue">No torrents</li>
            {{ end }}
            </ul>
            {{ if gt (.JSON.Int "counts.errored") 0 }}<p class="size-h6 color-negative">{{ .JSON.Int "counts.errored" }} torrent(s) in error</p>{{ end }}
            <p class="size-h6 color-subdue">{{ .JSON.Int "counts.total" }} torrent(s) &middot; added by RustyBox, imported into the Xbox library when they finish</p>
            {{ else }}
            <p class="color-negative">qBittorrent isn't responding.</p>
            <p class="size-h6 color-subdue">{{ .JSON.String "message" }}</p>
            {{ end }}
"""

# second SABnzbd (devuan): same template as the main one, inside the PIN-locked section with Private A
sab_devuan = (sab.replace("${HOST_SVC}", "${HOST_DEVUAN}")
              .replace("${SABNZBD_KEY}", "${DEVUAN_SAB_KEY}")
              .replace("title: SABnzbd" + chr(10), "title: SABnzbd (devuan)" + chr(10))
              .replace("          cache: 30s" + chr(10), "          css-class: wb-restricted" + chr(10) + "          cache: 30s" + chr(10), 1))
assert "wb-restricted" in sab_devuan and "DEVUAN_SAB_KEY" in sab_devuan and "SABnzbd (devuan)" in sab_devuan

seerr = """        - type: custom-api
          title: Seerr requests
          title-url: http://${HOST_SVC}:5055/requests
          cache: 2m
          url: http://${HOST_SVC}:5055/api/v1/request/count
          headers:
            X-Api-Key: ${SEERR_KEY}
          subrequests:
            recent:
              url: http://${HOST_SVC}:5055/api/v1/request?take=8&sort=added&filter=all
              headers:
                X-Api-Key: ${SEERR_KEY}
          template: |
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 {{ if gt (.JSON.Int "pending") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "pending" }}</div><div class="size-h6">PENDING</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "processing" }}</div><div class="size-h6">PROCESSING</div></div>
              <div><div class="size-h3 color-positive">{{ .JSON.Int "available" }}</div><div class="size-h6">AVAILABLE</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "total" }}</div><div class="size-h6">TOTAL</div></div>
            </div>
            <ul class="list list-gap-4 size-h6">
            {{ range (.Subrequest "recent").JSON.Array "results" }}
              {{ $st := .Int "status" }}
              <li class="flex justify-between gap-10"><span class="text-truncate">{{ .String "type" }} &middot; {{ .String "requestedBy.displayName" }} &middot; {{ if eq $st 1 }}<span class="color-primary">pending</span>{{ else if eq $st 2 }}approved{{ else if eq $st 3 }}declined{{ else if eq $st 4 }}<span class="color-negative">failed</span>{{ else }}<span class="color-positive">completed</span>{{ end }}</span><span class="color-subdue shrink-0" {{ .String "createdAt" | parseTime "rfc3339" | toRelativeTime }}></span></li>
            {{ else }}<li class="color-subdue">No requests yet</li>{{ end }}
            </ul>
"""

slskd = """        - type: custom-api
          title: Soulseek (slskd)
          title-url: http://${HOST_SVC}:5030/
          cache: 30s
          url: http://${HOST_SVC}:8095/integrations/api/slskd/
          template: |
            <div class="flex justify-between items-center margin-bottom-10">
              <div>Soulseek <span class="{{ if .JSON.Bool "connected" }}color-positive{{ else }}color-negative{{ end }}">{{ if .JSON.Bool "connected" }}connected{{ else }}offline{{ end }}</span></div>
              <div class="size-h6 color-subdue">v{{ .JSON.String "version" }}</div>
            </div>
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 color-positive">{{ .JSON.Int "counts.downloading" }}</div><div class="size-h6">DOWNLOADING</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "counts.queued" }}</div><div class="size-h6">QUEUED</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "counts.completed" }}</div><div class="size-h6">DONE</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "counts.failed") 0 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "counts.failed" }}</div><div class="size-h6">FAILED</div></div>
            </div>
            <ul class="list list-gap-8 size-h6">
            {{ range .JSON.Array "active" }}
              <li>
                <div class="flex justify-between gap-10"><span class="text-truncate">{{ .String "label" }}</span><span class="color-subdue shrink-0">{{ .Int "percent" }}%{{ with .String "speed" }} &middot; {{ . }}{{ end }}</span></div>
                <div class="wb-progress"><div style="width:{{ .Int "percent" }}%"></div></div>
              </li>
            {{ else }}
              <li class="color-subdue">Nothing in flight</li>
            {{ end }}
            </ul>
"""

prowlarr = """        - type: custom-api
          title: Prowlarr
          title-url: http://${HOST_SVC}:9696/
          cache: 5m
          url: http://${HOST_SVC}:9696/api/v1/indexer
          headers:
            X-Api-Key: ${PROWLARR_KEY}
          subrequests:
            health:
              url: http://${HOST_SVC}:9696/api/v1/health
              headers:
                X-Api-Key: ${PROWLARR_KEY}
            failing:
              url: http://${HOST_SVC}:9696/api/v1/indexerstatus
              headers:
                X-Api-Key: ${PROWLARR_KEY}
          template: |
            {{ $all := .JSON.Array "" }}{{ $on := 0 }}
            {{ range $all }}{{ if .Bool "enable" }}{{ $on = add $on 1 }}{{ end }}{{ end }}
            {{ $fail := len ((.Subrequest "failing").JSON.Array "") }}
            <div class="wb-stats margin-bottom-10">
              <div><div class="size-h3 color-highlight">{{ len $all }}</div><div class="size-h6">INDEXERS</div></div>
              <div><div class="size-h3 color-highlight">{{ $on }}</div><div class="size-h6">ENABLED</div></div>
              <div><div class="size-h3 {{ if gt $fail 0 }}color-negative{{ else }}color-positive{{ end }}">{{ $fail }}</div><div class="size-h6">FAILING</div></div>
            </div>
            <ul class="list list-gap-4 size-h6">
            {{ range (.Subrequest "health").JSON.Array "" }}
              <li class="{{ if eq (.String "type") "error" }}color-negative{{ else }}color-subdue{{ end }}">{{ .String "type" }} &middot; {{ .String "message" }}</li>
            {{ else }}<li class="color-positive">No health issues</li>{{ end }}
            </ul>
"""

# build the page by plain concatenation (indent handled per block)
def block(b, n):
    return textwrap.indent(textwrap.dedent(b), " " * n)

page = "- name: Downloads\n  slug: downloads\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += "        - type: split-column\n          max-columns: 2\n          widgets:\n"
page += block(sab, 12) + "\n" + block(qbit, 12) + "\n" + block(seerr, 12) + "\n"
page += block(radarr, 8) + "\n" + block(sonarr, 8) + "\n" + block(lidarr, 8) + "\n" + block(priva, 8) + "\n" + block(sab_devuan, 8) + "\n"
page += "    - size: small\n      widgets:\n" + block(slskd, 8) + "\n" + block(prowlarr, 8)

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
