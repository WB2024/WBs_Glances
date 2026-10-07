#!/usr/bin/env python3
"""Generates /opt/glance/config/pages/remote.yml: the Remote tab.
  left  : remote desktops (VNC/RDP hosts from Termix; click opens Termix's standalone viewer in a new tab)
  right : SSH terminal (dropdown of Termix SSH hosts; Termix's terminal in an iframe, with Pop out / Files / Full screen)
Both widgets are filled in the browser by wb-home.js (components remote-desktops and remote-terminal) from glance-admin /api/remote/hosts,
so adding a host in Termix adds it here with no edit to this file.
Re-runnable: python3 /opt/glance/tools/gen_remote.py [output-path]"""
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "/opt/glance/config/pages/remote.yml"
TX = "http://${HOST_SVC}:8080"      # Termix (opened by the same hostname as Glance, see wb-home.js)

page = """- name: Remote
  slug: remote
  width: wide
  columns:
    - size: small
      widgets:
        - type: html
          title: Remote desktops
          title-url: @TX@
          source: |
            <div data-wb="remote-desktops" data-wb-noindex></div>
    - size: full
      widgets:
        - type: html
          title: SSH terminal
          title-url: @TX@
          source: |
            <div data-wb="remote-terminal" data-wb-noindex></div>
""".replace("@TX@", TX)

open(OUT, "w", encoding="utf-8").write(page)
print("wrote", OUT, len(page), "bytes")
