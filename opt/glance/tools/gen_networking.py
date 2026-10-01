#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/networking.yml
  rows: network topology (moved from the old Infra page) | Pi-hole 1 + 2 | Tailscale mesh | Nginx Proxy Manager
  side: routers and switches
Re-runnable: python3 /opt/glance/tools/gen_networking.py [output-path]"""
import glob
import re
import sys
import textwrap

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/networking.yml"
GA = "http://${HOST_SVC}:3005"


def block(text, n):
    return textwrap.indent(textwrap.dedent(text), " " * n)


# ----------------------------------------------------------------------------- topology diagram: lifted unchanged from the old Infra page
legacy = sorted(glob.glob("/opt/glance/legacy/infra.yml.pre-phase6-*"))[-1]
src = open(legacy, encoding="utf-8").read()
m = re.search(r"(        - type: html\n          title: Network topology\n.*?)(?=\n        - type: monitor\n          title: Network\n)", src, re.S)
assert m, "topology block not found in " + legacy
topology = m.group(1).rstrip("\n") + "\n"
assert "bookstack.wbhomelab/books/networking" in topology and "<svg" in topology

pihole = """        - type: dns-stats
          title: Pi-hole @N@ (@IP@)
          title-url: http://${HOST_PIHOLE@N@}/admin
          service: pihole-v6
          url: http://${HOST_PIHOLE@N@}
          password: ${PIHOLE_KEY}
          hour-format: 24h
"""
pihole_split = ("        - type: split-column\n          max-columns: 2\n          widgets:\n"
                + block(pihole.replace("@N@", "1").replace("@IP@", ".53"), 12) + "\n"
                + block(pihole.replace("@N@", "2").replace("@IP@", ".54"), 12))

tailscale = """        - type: custom-api
          title: Tailscale mesh
          title-url: https://login.tailscale.com/admin/machines
          cache: 2m
          url: @GA@/api/tailscale/summary
          template: |
            <div class="wb-stats margin-bottom-15">
              <div><div class="size-h3 color-positive">{{ .JSON.Int "online" }}</div><div class="size-h6">ONLINE</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "offline" }}</div><div class="size-h6">OFFLINE</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "expired") 0 }}color-negative{{ else }}color-highlight{{ end }}">{{ .JSON.Int "expired" }}</div><div class="size-h6">KEYS EXPIRED</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "updates" }}</div><div class="size-h6">UPDATES</div></div>
            </div>
            <div class="wb-tiles">
            {{ range .JSON.Array "devices" }}
              <div class="wb-tile{{ if not (.Bool "online") }} wb-tile-off{{ end }}">
                <span class="{{ if .Bool "online" }}color-positive{{ else }}color-subdue{{ end }}">&#9679;</span>
                <div class="wb-tile-main">
                  <div class="color-highlight text-truncate">{{ .String "name" }} <span class="color-subdue size-h6">{{ .String "os" }}</span></div>
                  <div class="size-h6 color-subdue text-truncate">{{ .String "ip" }} &middot; {{ if .Bool "online" }}online{{ else if gt (.Int "seen_h") 48 }}seen {{ div (.Int "seen_h") 24 }}d ago{{ else }}seen {{ .Int "seen_h" }}h ago{{ end }}{{ if ne (.String "tags") "" }} &middot; {{ .String "tags" }}{{ end }}</div>
                </div>
                <div class="wb-tile-flags size-h6">
                  {{ if .Bool "key_expired" }}<span class="color-negative">key expired</span>{{ else if .Bool "expires_soon" }}<span class="color-primary">key {{ .Int "expires_days" }}d</span>{{ end }}
                  {{ if .Bool "update" }}<span class="color-subdue">update</span>{{ end }}
                </div>
              </div>
            {{ end }}
            </div>
""".replace("@GA@", GA)

npm = """        - type: custom-api
          title: Nginx Proxy Manager
          title-url: http://${HOST_SVC}:81
          cache: 1m
          url: @GA@/api/npm/summary
          template: |
            <div class="wb-stats margin-bottom-15">
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "total" }}</div><div class="size-h6">PROXY HOSTS</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "down") 0 }}color-negative{{ else }}color-positive{{ end }}">{{ .JSON.Int "down" }}</div><div class="size-h6">BACKEND DOWN</div></div>
              <div><div class="size-h3 {{ if gt (.JSON.Int "disabled") 0 }}color-primary{{ else }}color-highlight{{ end }}">{{ .JSON.Int "disabled" }}</div><div class="size-h6">DISABLED</div></div>
              <div><div class="size-h3 color-highlight">{{ .JSON.Int "redirections" }} / {{ .JSON.Int "streams" }}</div><div class="size-h6">REDIRECTS / STREAMS</div></div>
            </div>
            {{ range .JSON.Array "hosts" }}{{ if or (not (.Bool "backend_up")) (not (.Bool "enabled")) }}
            <div class="flex justify-between gap-10 size-h6 margin-bottom-5"><span class="text-truncate"><span class="color-negative">&#9679;</span> {{ .String "domain" }} <span class="color-subdue">&rarr; {{ .String "target" }}</span></span><span class="shrink-0 {{ if .Bool "enabled" }}color-negative{{ else }}color-primary{{ end }}">{{ if not (.Bool "backend_up") }}backend down{{ else }}disabled{{ end }}</span></div>
            {{ end }}{{ end }}
            <details class="wb-fold">
              <summary>All proxy hosts ({{ .JSON.Int "total" }})</summary>
              <ul class="list list-gap-4 size-h6 margin-top-10">
              {{ range .JSON.Array "hosts" }}
                <li class="flex justify-between gap-10">
                  <span class="text-truncate"><span class="{{ if .Bool "backend_up" }}color-positive{{ else }}color-negative{{ end }}">&#9679;</span> <a class="color-highlight" href="http://{{ .String "domain" }}" target="_blank">{{ .String "domain" }}</a>{{ if gt (.Int "extra") 0 }} <span class="color-subdue">+{{ .Int "extra" }}</span>{{ end }} <span class="color-subdue">&rarr; {{ .String "target" }}</span></span>
                  <span class="shrink-0">{{ if not (.Bool "enabled") }}<span class="color-primary">disabled</span> {{ end }}{{ if .Bool "ssl" }}<span class="color-positive">ssl</span>{{ end }}</span>
                </li>
              {{ end }}
              </ul>
            </details>
            {{ if .JSON.Array "certs" }}
            <div class="size-h6 color-subdue margin-top-15 margin-bottom-5">CERTIFICATES</div>
            <ul class="list list-gap-4 size-h6">
            {{ range .JSON.Array "certs" }}
              <li class="flex justify-between gap-10"><span class="text-truncate">{{ .String "name" }} <span class="color-subdue">&middot; {{ .String "provider" }} &middot; {{ if eq (.Int "used_by") 0 }}not used by any host{{ else }}used by {{ .Int "used_by" }}{{ end }}</span></span><span class="shrink-0 {{ if lt (.Int "days") 30 }}color-negative{{ else }}color-positive{{ end }}">{{ .Int "days" }} days left</span></li>
            {{ end }}
            </ul>
            {{ end }}
""".replace("@GA@", GA)

routers = """        - type: monitor
          title: Routers & switches
          cache: 1m
          sites:
            - { title: "EE Smart Hub · .254 (gateway)",   url: "http://${HOST_ROUTER}",    icon: mdi:router-wireless }
            - { title: "D-Link DGS-1520-52 · .3 (core)",   url: "http://${HOST_CORE}",      icon: mdi:lan,          timeout: 8s }
            - { title: "HP 1810-24G · .10 (office)",       url: "http://${HOST_OFFICE_SW}", icon: mdi:switch,       timeout: 8s }
            - { title: "GL.iNet SFT1200 · .52 (AP)",       url: "http://${HOST_AP}",        icon: mdi:access-point }
"""

page = "- name: Networking\n  slug: networking\n  width: wide\n  columns:\n    - size: full\n      widgets:\n"
page += topology + "\n" + pihole_split + "\n" + block(tailscale, 8) + "\n" + block(npm, 8) + "\n"
page += "    - size: small\n      widgets:\n" + routers

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
