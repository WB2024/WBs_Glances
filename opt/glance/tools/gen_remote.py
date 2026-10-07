#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/remote.yml: the Remote tab.
  one workspace widget (wb-home.js component remote-workspace): host list with search / recent / online status on the left; on the right
  open sessions, per-host tabs (Terminal, Files, Docker, Metrics, Tunnels, Tmux, or a VNC/RDP desktop), live CPU/RAM/disk, split view.
  Every pane is one of Termix's own standalone views in an iframe. It is filled in the browser from glance-admin /api/remote/hosts,
so adding a host in Termix adds it here with no edit to this file.
Re-runnable: python3 /opt/glance/tools/gen_remote.py [output-path]"""
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/remote.yml"
TX = "http://${HOST_SVC}:8080"      # Termix (opened by the same hostname as Glance, see wb-home.js)

page = """- name: Remote
  slug: remote
  width: wide
  columns:
    - size: full
      widgets:
        - type: html
          title: Remote
          title-url: @TX@
          source: |
            <div data-wb="remote-workspace" data-wb-noindex></div>
""".replace("@TX@", TX)

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
