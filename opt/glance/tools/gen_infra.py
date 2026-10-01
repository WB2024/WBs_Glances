#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/infra.yml from the glance-admin infra summary (/api/infra/summary).
Rows: pve4 | pve2 | PBS  ->  Dockge hosts (services, jellyfin, devuan)  ->  infrastructure diagram  ->  storage + backup coverage.
Re-runnable: python3 /opt/glance/tools/gen_infra.py [output-path]"""
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/infra.yml"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


def bar(label, pct, text, margin="margin-bottom-8"):
    return ('<div class="flex justify-between size-h6"><span class="color-subdue">@L@</span><span>@T@</span></div>'
            '<div class="progress-bar @M@"><div class="progress-value{{ if gt (@P@) 85 }} progress-value-notice{{ end }}" '
            'style="--percent: {{ @P@ }}"></div></div>').replace("@L@", label).replace("@T@", text).replace("@P@", pct).replace("@M@", margin)


def tile(value, label, warn_over=None, warn_expr=None):
    cls = "color-highlight"
    if warn_over is not None:
        cls = "{{ if gt (%s) %s }}color-negative{{ else }}color-highlight{{ end }}" % (warn_expr, warn_over)
    return '<div><div class="size-h3 %s">%s</div><div class="size-h6">%s</div></div>' % (cls, value, label)


def widget(title, title_url, template, cache="1m", extra=""):
    return ("        - type: custom-api\n          title: %s\n          title-url: %s\n%s          cache: %s\n          url: %s/api/infra/summary\n"
            "          template: |\n%s\n") % (title, title_url, extra, cache, GA, block(template, 12))


# ----------------------------------------------------------------------------- Proxmox node card
def node_card(name, ip):
    guests = """
<ul class="list list-gap-10 size-h6">
{{ range .Array "guests" }}
  <li>
    <div class="flex justify-between gap-10">
      <span class="text-truncate"><span class="color-subdue">{{ if eq (.String "kind") "lxc" }}CT{{ else }}VM{{ end }}{{ .Int "vmid" }}</span> {{ .String "name" }}</span>
      <span class="shrink-0">{{ if eq (.String "status") "running" }}<span class="color-positive">&#9679;</span> {{ .Int "cpu_pct" }}% cpu{{ else }}<span class="color-subdue">&#9675; {{ .String "status" }}</span>{{ end }}</span>
    </div>
    BAR_MEM
    BAR_DISK
  </li>
{{ end }}
</ul>
""".replace("BAR_MEM", bar("RAM", '.Int "mem_pct"', '{{ .Int "mem_mb" }} / {{ .Int "maxmem_mb" }} MB', "margin-bottom-4")) \
       .replace("BAR_DISK", bar("Disk", '.Int "disk_pct"', '{{ printf "%.1f" (.Float "disk_gb") }} / {{ printf "%.0f" (.Float "maxdisk_gb") }} GB', "margin-bottom-4"))
    t = """
{{ range .JSON.Array "nodes" }}{{ if eq (.String "name") "@N@" }}
{{ if .Bool "ok" }}
<div class="wb-stats margin-bottom-10">
  T_CPU
  T_RAM
  T_LOAD
  T_ROOT
  T_UP
</div>
<div class="size-h6 color-subdue margin-bottom-10">pve {{ .String "pve" }} &middot; kernel {{ .String "kernel" }}</div>
GUESTS
<div class="size-h6 margin-top-10 {{ if gt (.Int "failed_7d") 0 }}color-negative{{ else }}color-positive{{ end }}">FAILED TASKS &middot; 7 DAYS: {{ .Int "failed_7d" }}</div>
{{ range .Array "failed_latest" }}{{ if lt (.Int "age_h") 168 }}<div class="size-h6 color-subdue text-truncate">{{ .String "type" }} {{ .String "id" }} &middot; {{ .Int "age_h" }}h ago &middot; {{ .String "status" }}</div>{{ end }}{{ end }}
<div class="size-h6 margin-top-5 {{ if .Bool "backed_up" }}color-subdue{{ else }}color-negative{{ end }}">{{ if .Bool "backed_up" }}host backup {{ .Int "backup_h" }}h ago{{ else }}no host backup in PBS{{ end }}</div>
{{ else }}<p class="color-negative">Proxmox API unreachable: {{ .String "err" }}</p>{{ end }}
{{ end }}{{ end }}
""".replace("GUESTS", guests) \
       .replace("T_CPU", tile('{{ .Int "cpu_pct" }}%', 'CPU &middot; {{ .Int "cpus" }} cores', 80, '.Int "cpu_pct"')) \
       .replace("T_RAM", tile('{{ .Int "mem_pct" }}%', 'RAM &middot; {{ printf "%.0f" (.Float "mem_total_gb") }}G', 90, '.Int "mem_pct"')) \
       .replace("T_LOAD", tile('{{ .Float "load" }}', 'LOAD 1M')) \
       .replace("T_ROOT", tile('{{ .Int "rootfs_pct" }}%', 'ROOTFS', 85, '.Int "rootfs_pct"')) \
       .replace("T_UP", tile('{{ printf "%.1f" (.Float "uptime_d") }}d', 'UPTIME')) \
       .replace("@N@", name)
    return widget("%s" % name, "https://%s:8006" % ip, t)


# ----------------------------------------------------------------------------- PBS card
pbs_t = """
{{ if .JSON.Bool "pbs.ok" }}
<div class="wb-stats margin-bottom-10">
  T_RAM
  T_LOAD
  T_UP
</div>
{{ range .JSON.Array "pbs.datastores" }}
BAR_DS
{{ end }}
<div class="size-h6 margin-top-10 {{ if gt (.JSON.Int "pbs.failed_7d") 0 }}color-negative{{ else }}color-positive{{ end }}">FAILED TASKS &middot; 7 DAYS: {{ .JSON.Int "pbs.failed_7d" }}</div>
<div class="size-h6 color-subdue margin-top-10 margin-bottom-5">LAST BACKUP TASKS</div>
<ul class="list list-gap-4 size-h6">
{{ range .JSON.Array "pbs.recent" }}
  <li class="flex justify-between gap-10"><span class="text-truncate">{{ .String "name" }}</span><span class="shrink-0 {{ if eq (.String "status") "OK" }}color-positive{{ else if eq (.String "status") "running" }}color-primary{{ else }}color-negative{{ end }}">{{ .String "status" }} &middot; {{ .Int "age_h" }}h</span></li>
{{ end }}
</ul>
{{ else }}<p class="color-negative">PBS API unreachable: {{ .JSON.String "pbs.err" }}</p>{{ end }}
""".replace("T_RAM", tile('{{ .JSON.Int "pbs.mem_pct" }}%', 'RAM')) \
   .replace("T_LOAD", tile('{{ .JSON.Float "pbs.load" }}', 'LOAD')) \
   .replace("T_UP", tile('{{ printf "%.0f" (.JSON.Float "pbs.uptime_d") }}d', 'UPTIME')) \
   .replace("BAR_DS", bar('{{ .String "store" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))


# ----------------------------------------------------------------------------- Dockge host rows
STACKS_COL = """  <div class="grow" style="flex-basis:24rem;min-width:0">
    <div class="wb-stacks" style="max-height:@H@;overflow-y:auto">
    {{ range .JSON.Array "@K@.stacks" }}@IF@
      <div class="wb-stack">
        <div class="wb-stack-name">{{ .String "name" }}</div>
        <ul class="list list-gap-4 size-h6">
        {{ range .Array "containers" }}
          <li class="text-truncate" title="{{ .String "image" }} &middot; {{ .String "status" }}"><span class="{{ if eq (.String "state") "running" }}{{ if eq (.String "health") "unhealthy" }}color-negative{{ else }}color-positive{{ end }}{{ else }}color-subdue{{ end }}">{{ if eq (.String "state") "running" }}&#9679;{{ else }}&#9675;{{ end }}</span> {{ .String "name" }}</li>
        {{ end }}
        </ul>
      </div>@ENDIF@
    {{ end }}
    </div>
  </div>"""


def stacks_widget(key, title, dockge_url, scroll):
    """Container names only, in a PIN-locked widget (its title and link are masked until unlocked)."""
    t = ("{{ if .JSON.Bool \"@K@.ok\" }}<div>" + STACKS_COL + "</div>{{ else }}<p class=\"color-negative\">Host unreachable</p>{{ end }}"
         ).replace("@IF@", "").replace("@ENDIF@", "").replace("@K@", "hosts." + key).replace("@H@", scroll)
    return widget(title, dockge_url, t, extra="          css-class: wb-restricted\n")


def host_row(key, title, dockge_url, cpu_label, scroll, stacks=True):
    k = "hosts." + key
    t = """
{{ if .JSON.Bool "@K@.ok" }}
<div class="flex gap-25" style="flex-wrap:wrap">
  <div style="flex:0 0 24rem;max-width:100%;min-width:0">
    <div class="wb-stats margin-bottom-10">
      T_CPU
      T_RAM
      {{ if gt (.JSON.Float "@K@.temp_c") 0.0 }}T_TEMP{{ end }}
      T_UP
    </div>
    {{ range .JSON.Array "@K@.disks" }}
    BAR_DISK
    {{ end }}
    <div class="size-h6 color-subdue margin-top-10">Docker {{ .JSON.String "@K@.docker" }} &middot; <span class="color-positive">{{ .JSON.Int "@K@.running" }} running</span> &middot; {{ .JSON.Int "@K@.stopped" }} stopped &middot; {{ len (.JSON.Array "@K@.stacks") }} stacks</div>
  </div>
@STACKS@
</div>
{{ else }}<p class="color-negative">Host unreachable: {{ .JSON.String "@K@.err" }}</p>{{ end }}
""".replace("@STACKS@", (STACKS_COL.replace("@IF@", '{{ if not (.Bool "private") }}').replace("@ENDIF@", "{{ end }}") if stacks else "")).replace("@K@", k).replace("@H@", scroll) \
       .replace("T_CPU", tile('{{ .JSON.Int "%s.cpu_pct" }}%%' % k, cpu_label, 80, '.JSON.Int "%s.cpu_pct"' % k)) \
       .replace("T_RAM", tile('{{ .JSON.Int "%s.mem_pct" }}%%' % k, 'RAM &middot; {{ printf "%%.1f" (div (.JSON.Float "%s.mem_total_mb") 1024.0) }}G' % k, 90, '.JSON.Int "%s.mem_pct"' % k)) \
       .replace("T_TEMP", tile('{{ printf "%%.0f" (.JSON.Float "%s.temp_c") }}&deg;C' % k, 'CPU TEMP', "80.0", '.JSON.Float "%s.temp_c"' % k)) \
       .replace("T_UP", tile('{{ printf "%%.1f" (.JSON.Float "%s.uptime_d") }}d' % k, 'UPTIME')) \
       .replace("BAR_DISK", bar('{{ .String "name" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))
    return widget(title, dockge_url, t)


# ----------------------------------------------------------------------------- storage + backup coverage
storage_t = """
<div class="flex gap-25" style="flex-wrap:wrap">
  <div style="flex:1 1 22rem;min-width:0">
    <div class="size-h6 color-subdue margin-bottom-5">SPACE IN USE</div>
    {{ range .JSON.Array "nodes" }}{{ if eq (.String "name") "pve4" }}{{ range .Array "storage" }}BAR_STORE{{ end }}{{ end }}{{ end }}
    {{ range .JSON.Array "hosts.devuan.disks" }}BAR_DISK{{ end }}
    {{ range .JSON.Array "hosts.services.disks" }}BAR_SVC{{ end }}
    {{ range .JSON.Array "pbs.datastores" }}BAR_DS{{ end }}
  </div>
  <div style="flex:2 1 34rem;min-width:0">
    <div class="size-h6 color-subdue margin-bottom-5">EVERY PHYSICAL DISK</div>
    <ul class="list list-gap-8 size-h6">
    {{ range .JSON.Array "nodes" }}{{ $node := .String "name" }}
      {{ range .Array "disks" }}
      <li>
        <div class="flex justify-between gap-10">
          <span class="text-truncate"><span class="color-subdue">{{ $node }}</span> <span class="color-highlight">{{ .String "dev" }}</span> {{ .String "model" }}</span>
          <span class="shrink-0">{{ if ge (.Int "size_gb") 1000 }}{{ printf "%.1f" (div (.Float "size_gb") 1000.0) }} TB{{ else }}{{ .Int "size_gb" }} GB{{ end }} &middot; <span class="{{ if eq (.String "health") "PASSED" }}color-positive{{ else if eq (.String "health") "UNKNOWN" }}color-subdue{{ else }}color-negative{{ end }}">{{ .String "health" }}</span>{{ if .Exists "wear_left" }}{{ if gt (.Int "wear_left") 0 }} &middot; {{ .Int "wear_left" }}% life{{ end }}{{ end }}</span>
        </div>
        <div class="color-subdue text-truncate">{{ .String "mount" }}{{ if .String "role" }} &middot; {{ .String "role" }}{{ end }}</div>
      </li>
      {{ end }}
    {{ end }}
    {{ range .JSON.Array "hosts.devuan.disks" }}
      <li>
        <div class="flex justify-between gap-10"><span class="text-truncate"><span class="color-subdue">devuan</span> <span class="color-highlight">{{ .String "name" }}</span></span><span class="shrink-0">{{ if ge (.Int "total_gb") 1000 }}{{ printf "%.1f" (div (.Float "total_gb") 1000.0) }} TB{{ else }}{{ .Int "total_gb" }} GB{{ end }} &middot; {{ .Int "pct" }}% used</span></div>
        <div class="color-subdue text-truncate">{{ .String "mount" }} &middot; {{ .String "role" }}</div>
      </li>
    {{ end }}
    </ul>
  </div>
  <div style="flex:1 1 22rem;min-width:0">
    <div class="size-h6 color-subdue margin-bottom-5">BACKUP COVERAGE (PBS)</div>
    <ul class="list list-gap-4 size-h6">
    {{ range .JSON.Array "nodes" }}
      <li class="flex justify-between gap-10"><span>host &middot; {{ .String "name" }}</span><span class="{{ if .Bool "backed_up" }}color-positive{{ else }}color-negative{{ end }}">{{ if .Bool "backed_up" }}{{ .Int "backup_h" }}h ago{{ else }}NO BACKUP{{ end }}</span></li>
      {{ range .Array "guests" }}
      <li class="flex justify-between gap-10"><span>{{ if eq (.String "kind") "lxc" }}CT{{ else }}VM{{ end }}{{ .Int "vmid" }} &middot; {{ .String "name" }}</span><span class="{{ if .Bool "backed_up" }}color-positive{{ else }}color-negative{{ end }}">{{ if .Bool "backed_up" }}{{ .Int "backup_h" }}h ago{{ else }}NO BACKUP{{ end }}</span></li>
      {{ end }}
    {{ end }}
    {{ range .JSON.Array "pbs.groups" }}{{ if .Bool "stale" }}
      <li class="flex justify-between gap-10 color-subdue"><span>PBS group {{ .String "type" }}/{{ .String "id" }}</span><span class="color-negative">last {{ div (.Int "age_h") 24 }}d ago (stale)</span></li>
    {{ end }}{{ end }}
    </ul>
  </div>
</div>
""".replace("BAR_STORE", bar('pve4 &middot; {{ .String "name" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))    .replace("BAR_DISK", bar('devuan &middot; {{ .String "name" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))    .replace("BAR_SVC", bar('services &middot; {{ .String "name" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))    .replace("BAR_DS", bar('PBS &middot; {{ .String "store" }}', '.Int "pct"', '{{ .Int "used_gb" }} / {{ .Int "total_gb" }} GB &middot; {{ .Int "pct" }}%'))


# ----------------------------------------------------------------------------- infrastructure diagram (static)
diagram = """        - type: html
          title: Infrastructure map
          source: |
            <svg class="wb-topo" viewBox="0 0 1100 640" xmlns="http://www.w3.org/2000/svg">
              <text class="t-sub" x="1090" y="14" text-anchor="end">compute &amp; storage as built &middot; Oct 2026 (static: edit by hand when it changes)</text>

              <!-- pve4 -->
              <rect class="box" x="20" y="40" width="470" height="290"/>
              <text class="t-title" x="255" y="62" text-anchor="middle">pve4 &middot; main node &middot; .60</text>
              <text class="t-sub" x="255" y="78" text-anchor="middle">Proxmox VE &middot; 4 cores &middot; 32 GB &middot; 11 drives</text>
              <rect class="box box-core" x="40" y="96" width="210" height="214"/>
              <text class="t-title" x="145" y="118" text-anchor="middle">CT103 &middot; services &middot; .110</text>
              <text class="t-sub" x="145" y="136" text-anchor="middle">Dockge &middot; Nginx Proxy Manager</text>
              <text class="t-sub" x="145" y="152" text-anchor="middle">Glance + glance-admin</text>
              <text class="t-sub" x="145" y="168" text-anchor="middle">Lidarr &middot; Radarr &middot; Sonarr &middot; Prowlarr</text>
              <text class="t-sub" x="145" y="184" text-anchor="middle">SABnzbd &middot; slskd &middot; Seerr</text>
              <text class="t-sub" x="145" y="200" text-anchor="middle">Navidrome &middot; Audiobookshelf</text>
              <text class="t-sub" x="145" y="216" text-anchor="middle">RustyDisc &middot; Picard &middot; NOMAD tools</text>
              <text class="t-sub" x="145" y="232" text-anchor="middle">BookStack &middot; Paperless &middot; Forgejo</text>
              <text class="t-sub" x="145" y="248" text-anchor="middle">Vaultwarden &middot; SearXNG &middot; Termix</text>
              <text class="t-tag" x="145" y="290" text-anchor="middle">4 cores &middot; 24 GB &middot; 115 GB disk</text>
              <rect class="box box-core" x="270" y="96" width="200" height="110"/>
              <text class="t-title" x="370" y="118" text-anchor="middle">CT104 &middot; jellyfin &middot; .111</text>
              <text class="t-sub" x="370" y="138" text-anchor="middle">Jellyfin &middot; Dockge</text>
              <text class="t-tag" x="370" y="186" text-anchor="middle">4 cores &middot; 8 GB &middot; 32 GB disk</text>

              <!-- pve2 -->
              <rect class="box" x="520" y="40" width="270" height="190"/>
              <text class="t-title" x="655" y="62" text-anchor="middle">pve2 &middot; automation node &middot; .59</text>
              <text class="t-sub" x="655" y="78" text-anchor="middle">Proxmox VE &middot; 4 cores &middot; 8 GB</text>
              <rect class="box box-core" x="540" y="96" width="230" height="96"/>
              <text class="t-title" x="655" y="118" text-anchor="middle">CT200 &middot; automation &middot; .112</text>
              <text class="t-sub" x="655" y="138" text-anchor="middle">Home Assistant &middot; Frigate &middot; Dockge</text>
              <text class="t-tag" x="655" y="178" text-anchor="middle">4 cores &middot; 6 GB &middot; 32 GB disk</text>
              <text class="t-sub" x="655" y="214" text-anchor="middle">disk: 120 GB SSD (boot + root)</text>

              <!-- PBS -->
              <rect class="box" x="520" y="250" width="270" height="80"/>
              <text class="t-title" x="655" y="274" text-anchor="middle">Proxmox Backup Server &middot; .250</text>
              <text class="t-sub" x="655" y="294" text-anchor="middle">datastore pbs-store &middot; ~0.9 TB (NFS from pve4)</text>
              <text class="t-sub" x="655" y="312" text-anchor="middle">host + container backups from the nodes</text>

              <!-- devuan -->
              <rect class="box" x="820" y="40" width="260" height="290"/>
              <text class="t-title" x="950" y="62" text-anchor="middle">devuan &middot; physical &middot; .106</text>
              <text class="t-sub" x="950" y="78" text-anchor="middle">Devuan 6 &middot; 2 cores &middot; 4 GB &middot; 4 drives</text>
              <rect class="box box-core" x="840" y="96" width="220" height="130"/>
              <text class="t-title" x="950" y="118" text-anchor="middle">Docker (Dockge)</text>
              <text class="t-sub" x="950" y="138" text-anchor="middle">private containers (locked)</text>
              <text class="t-sub" x="950" y="154" text-anchor="middle">Glance agent + lister</text>
              <text class="t-tag" x="950" y="206" text-anchor="middle">data on the 233 GB root SSD</text>
              <rect class="box" x="840" y="246" width="105" height="64"/>
              <text class="t-title" x="892" y="268" text-anchor="middle">/srv/1tb</text>
              <text class="t-sub" x="892" y="285" text-anchor="middle">btrfs, 2 &times; 1 TB</text>
              <text class="t-tag" x="892" y="301" text-anchor="middle">private data</text>
              <rect class="box" x="955" y="246" width="105" height="64"/>
              <text class="t-title" x="1007" y="268" text-anchor="middle">/srv/4tb</text>
              <text class="t-sub" x="1007" y="285" text-anchor="middle">4 TB ext4</text>
              <text class="t-tag" x="1007" y="301" text-anchor="middle">recordings, NFS</text>

              <!-- pve4 disks -->
              <rect class="box" x="20" y="358" width="770" height="226"/>
              <text class="t-title" x="36" y="378">pve4 disks</text>

              <rect class="box box-core" x="36" y="386" width="118" height="62"/>
              <text class="t-title" x="95" y="406" text-anchor="middle">Main20TB</text>
              <text class="t-sub" x="95" y="422" text-anchor="middle">20 TB &middot; ext4</text>
              <text class="t-tag" x="95" y="438" text-anchor="middle">media pool</text>
              <rect class="box" x="162" y="386" width="118" height="62"/>
              <text class="t-title" x="221" y="406" text-anchor="middle">wd-4tb</text>
              <text class="t-sub" x="221" y="422" text-anchor="middle">4 TB &middot; ext4</text>
              <text class="t-tag" x="221" y="438" text-anchor="middle">PVE dir + dumps</text>
              <rect class="box" x="288" y="386" width="118" height="62"/>
              <text class="t-title" x="347" y="406" text-anchor="middle">pbs-nfs</text>
              <text class="t-sub" x="347" y="422" text-anchor="middle">1 TB &middot; ext4</text>
              <text class="t-tag" x="347" y="438" text-anchor="middle">PBS datastore</text>
              <rect class="box" x="414" y="386" width="118" height="62"/>
              <text class="t-title" x="473" y="406" text-anchor="middle">OCZ SSD</text>
              <text class="t-sub" x="473" y="422" text-anchor="middle">128 GB</text>
              <text class="t-tag" x="473" y="438" text-anchor="middle">boot + root</text>
              <rect class="box" x="540" y="386" width="118" height="62"/>
              <text class="t-title" x="599" y="406" text-anchor="middle">CT240 SSD</text>
              <text class="t-sub" x="599" y="422" text-anchor="middle">240 GB</text>
              <text class="t-tag" x="599" y="438" text-anchor="middle">local-lvm (CTs)</text>
              <rect class="box" x="666" y="386" width="118" height="62"/>
              <text class="t-title" x="725" y="406" text-anchor="middle">USB stick</text>
              <text class="t-sub" x="725" y="422" text-anchor="middle">32 GB &middot; exfat</text>
              <text class="t-tag" x="725" y="438" text-anchor="middle">not in use</text>

              <rect class="box" x="28" y="462" width="392" height="112"/>
              <text class="t-sub" x="36" y="478">backup-20tb &middot; mergerfs &middot; nightly rsync of Main20TB</text>
              <rect class="box" x="36" y="488" width="118" height="62"/>
              <text class="t-title" x="95" y="508" text-anchor="middle">sdb1</text>
              <text class="t-sub" x="95" y="524" text-anchor="middle">8 TB &middot; ext4</text>
              <text class="t-tag" x="95" y="540" text-anchor="middle">pool member</text>
              <rect class="box" x="162" y="488" width="118" height="62"/>
              <text class="t-title" x="221" y="508" text-anchor="middle">sdc1</text>
              <text class="t-sub" x="221" y="524" text-anchor="middle">10 TB &middot; ext4</text>
              <text class="t-tag" x="221" y="540" text-anchor="middle">pool member</text>
              <rect class="box" x="288" y="488" width="118" height="62"/>
              <text class="t-title" x="347" y="508" text-anchor="middle">sdg1</text>
              <text class="t-sub" x="347" y="524" text-anchor="middle">2 TB &middot; ext4</text>
              <text class="t-tag" x="347" y="540" text-anchor="middle">pool member</text>

              <rect class="box" x="432" y="462" width="262" height="112"/>
              <text class="t-sub" x="440" y="478">misc &middot; mergerfs &middot; scratch, NFS export</text>
              <rect class="box" x="440" y="488" width="118" height="62"/>
              <text class="t-title" x="499" y="508" text-anchor="middle">st-500gb</text>
              <text class="t-sub" x="499" y="524" text-anchor="middle">500 GB &middot; ext4</text>
              <text class="t-tag" x="499" y="540" text-anchor="middle">pool member</text>
              <rect class="box" x="566" y="488" width="118" height="62"/>
              <text class="t-title" x="625" y="508" text-anchor="middle">hgst-1tb</text>
              <text class="t-sub" x="625" y="524" text-anchor="middle">1 TB &middot; ext4</text>
              <text class="t-tag" x="625" y="540" text-anchor="middle">pool member</text>

              <!-- links -->
              <path class="link link-fibre" d="M145 310 V386"/>
              <path class="link link-fibre" d="M370 206 V340 H110 V386"/>
              <path class="link link-standby" d="M60 448 V462"/>
              <path class="link link-standby" d="M490 190 H520"/>
              <path class="link link-vlan15" d="M655 230 V250"/>
              <path class="link link-standby" d="M490 150 H505 V280 H520"/>
              <path class="link link-acl" d="M820 150 H790"/>
              <path class="link link-acl" d="M1007 310 V345 H221 V386"/>
              <path class="link link-vlan15" d="M600 330 V372 H347 V386"/>

              <!-- legend -->
              <path class="link link-fibre" d="M20 608 H50"/><text class="t-sub" x="56" y="612">storage mount</text>
              <path class="link link-standby" d="M170 608 H200"/><text class="t-sub" x="206" y="612">backup flow</text>
              <path class="link link-vlan15" d="M310 608 H340"/><text class="t-sub" x="346" y="612">node &rarr; PBS</text>
              <path class="link link-acl" d="M460 608 H490"/><text class="t-sub" x="496" y="612">Glance agent reads / NFS from devuan</text>
            </svg>
"""

hosts_monitor = """        - type: monitor
          title: Hosts
          cache: 1m
          sites:
            - { title: "pve4 (.60)",             url: "https://${HOST_PVE4}:8006", allow-insecure: true, icon: di:proxmox }
            - { title: "pve2 (.59)",             url: "https://${HOST_PVE2}:8006", allow-insecure: true, icon: di:proxmox }
            - { title: "PBS (.250)",             url: "https://${HOST_PBS}:8007",  allow-insecure: true, icon: di:proxmox-backup-server }
            - { title: "services · Dockge",      url: "http://${HOST_SVC}:5001",    icon: di:dockge }
            - { title: "jellyfin · Dockge",      url: "http://${HOST_JELLY}:5001",  icon: di:dockge }
            - { title: "devuan · Dockge",        url: "http://${HOST_DEVUAN}:5001", icon: di:dockge }
            - { title: "automation · Dockge",    url: "http://${HOST_AUTO}:5001",   icon: di:dockge }
            - { title: "Home Assistant",         url: "http://${HOST_AUTO}:8123",   icon: di:home-assistant }
"""

page = "- name: Infra\n  slug: infra\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += "        - type: split-column\n          max-columns: 3\n          widgets:\n"
for w in (node_card("pve4", "${HOST_PVE4}"), node_card("pve2", "${HOST_PVE2}"),
          widget("Proxmox Backup Server", "https://${HOST_PBS}:8007", pbs_t)):
    page += block(w, 12) + "\n"
page += host_row("services", "Dockge · services", "http://${HOST_SVC}:5001", "CPU", "26rem")
page += host_row("jellyfin", "Dockge · jellyfin", "http://${HOST_JELLY}:5001", "CPU", "16rem")
page += host_row("devuan", "Dockge · devuan", "http://${HOST_DEVUAN}:5001", "LOAD", "18rem", stacks=False)
page += stacks_widget("devuan", "Dockge · devuan (containers)", "http://${HOST_DEVUAN}:5001", "18rem")
page += diagram
page += widget("Storage and backups", "https://${HOST_PBS}:8007", storage_t)
page += "    - size: small\n      widgets:\n" + hosts_monitor

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
