# Glance Dashboard — Current Configuration Reference

> Rewritten **2026-10-01** after the redesign (Phases 1–12 of `Glance-Redesign-Plan.md`). This describes the dashboard **as it is now**.
> The pre-redesign description is archived in `Archive/Glance-Config-Report-pre-redesign.md`; the retired Homepage is described in `Homepage-Config-Report.md`.
> **No secret values appear here.** Variables are listed by name only.

---

## 1. At a glance

| | |
|---|---|
| Dashboard | [Glance](https://github.com/glanceapp/glance) **v0.8.6**, branded "Homelab" / "WB", at **http://192.168.1.110:3002** |
| Runs on | `services` LXC (CT103, 192.168.1.110) on Proxmox node pve4, in Docker |
| Companion service | **glance-admin** (port 3005), a small Python service that supplies data and the editing features Glance lacks |
| Host agents | `glance-agent` + `glance-lister` stacks on devuan and the jellyfin LXC; `glance-lister` on the services LXC |
| Tabs (11) | Home · Downloads · Audio · Video · Infra · Networking · Tools · Cameras · News Feeds · Video News Feed · Bookmarks |
| Retired | Homepage (deleted 2026-10-01; verified backup kept), the old Media and Feeds tabs |
| Health | all 11 pages 0 widget errors; desktop (1912 px) and phone (390 px) tested for overflow, broken images, theme-picker access and locked rows |

---

## 2. Architecture

```
 Browser ──http──▶ Glance :3002 ──server-side──▶ service APIs (Radarr, Sonarr, Lidarr, Jellyfin, Navidrome, SABnzbd, Seerr, Pi-hole, ...)
    │                   │
    │                   └──server-side──▶ glance-admin :3005  (cached, shaped JSON; holds the extra secrets)
    │                                          │
    │                                          ├─▶ Proxmox / PBS APIs, Tailscale (OAuth), NPM (view-only user)
    │                                          ├─▶ Audiobookshelf, Navidrome covers, Private B, Immich, Paperless, Forgejo, BookStack
    │                                          ├─▶ Frigate (internal API), YouTube RSS, GitHub release feeds
    │                                          └─▶ per-host  glance-agent :27973 + glance-lister :27974 (devuan, jellyfin LXC, services LXC)
    │
    └──http──▶ glance-admin :3005   (notes, to-do, Find, bookmark/channel editors, image proxies)  and  Frigate :5000 (live stream, thumbnails)
```

Design rules that explain most choices:
1. **Secrets never reach the page.** Anything needing a key is fetched server-side (by Glance or glance-admin); images that need credentials go through glance-admin proxies.
2. **Slow or rate-limited upstreams are cached in glance-admin** (Lidarr's calendar, GitHub releases, Proxmox, ...), so Glance always gets an instant answer. Summaries are persisted to disk and survive restarts.
3. **Private rows are locked** (PIN) and load nothing until unlocked.
4. **glance-admin may write only three folders**, so it can edit your bookmarks/channels but not your hand-written config.

---

## 3. Hosts and containers

| Where | Container / stack | Purpose | Port |
|---|---|---|---|
| services LXC | `glance` (`/opt/stacks/glance`) | the dashboard; 1 CPU / 512 MB | 3002 |
| services LXC | `glance-admin` (`/opt/stacks/glance-admin`) | data, caches, editors; 0.5 CPU / 128 MB | 3005 |
| services LXC | `glance-lister` (`/opt/stacks/glance-agent`) | read-only container list for the Infra page | 27974 |
| devuan (.106) | `glance-agent` + `glance-lister` (`/opt/stacks/glance-agent`) | CPU/RAM/disks; containers + CPU temperature | 27973 / 27974 |
| jellyfin LXC (.111) | same stack | same | 27973 / 27974 |

Agents/listers are LAN-only and **token-protected** (no token or a wrong token → 401; writes → 405). The lister returns only name, image, state, status, health, compose stack and published ports, **never** environment variables. Remove any of these stacks with `docker compose down` in its folder. A reference copy of the host stack is at `/opt/glance/tools/host-stack/`.

Not touched by this project: the Proxmox hosts, PBS and the automation LXC.

---

## 4. Directory layout (`/opt/glance`)

```
/opt/glance/
├── .env                    MASTER secrets + host addresses (mode 600)
├── glance.env              generated: only the variables Glance's config uses (mode 600)
├── check_pages.py          health check over all pages
├── config/
│   ├── glance.yml          server, theme (+ presets), document.head scripts, page list
│   ├── pages/              HAND/GENERATOR-WRITTEN pages: home downloads audio video infra networking tools cameras news
│   └── data/               WRITTEN BY glance-admin: bookmarks.yml, video-news.yml
├── assets/
│   ├── glance/             custom.css · wb-home.js · wb-restricted.js · wb-restricted-config.js · rustydisc.png · retired/
│   ├── images/             icon/wallpaper library (42 files, copied from Homepage)
│   └── favicons/           site icons cached for bookmarks (written by glance-admin)
├── data/                   glance-admin state: bookmarks.json, channels.json, notes.json, todos.json, covers/, cache/
├── tools/                  generators (gen_*.py), sync_env.py, host-stack/
└── legacy/                 retired material (old pages, generator, Homepage bookmarks seed, 119 old edit copies in old-edits/, mode 700)

/opt/glance-admin/          glance-admin source: app.py (routes, caches) + infra.py net.py tools.py releases.py cameras.py channels.py bookmarks.py + Dockerfile
/opt/stacks/{glance,glance-admin,glance-agent}/    compose files (Dockge-visible)
/mnt/Main20TB/Backups/dashboards/                  backups (section 11)
```

---

## 5. Configuration model

### 5.1 `glance.yml`
Server port 8080, branding ("Homelab", logo "WB", footer hidden), a near-black zinc theme with warm accent and **~40 theme presets** (4 light), `custom-css-file: /assets/glance/custom.css`, and `document.head` loading three scripts (`wb-restricted-config.js`, `wb-restricted.js`, `wb-home.js`). The page list is `$include`s of the nine files in `pages/` plus `data/video-news.yml` and `data/bookmarks.yml`.

### 5.2 Which pages are edited how
| Page | Source | How to change it |
|---|---|---|
| Home | `pages/home.yml` (hand-written) | edit the YAML; the search-engine list is a JSON attribute inside the Search widget |
| Downloads, Audio, Video, Infra, Networking, Tools, Cameras, News Feeds | `pages/*.yml` **generated** | edit the matching `tools/gen_<page>.py`, run it (it writes a temp file, validate, then move into place) |
| Video News Feed | `data/video-news.yml` | **use the Channels box on the page** (glance-admin regenerates it) |
| Bookmarks | `data/bookmarks.yml` | **use "Edit bookmarks" on the page** (glance-admin regenerates it) |

Generators: `gen_downloads.py`, `gen_audio.py`, `gen_video.py`, `gen_infra.py`, `gen_networking.py`, `gen_tools.py`, `gen_cameras.py`, `gen_news.py`. Each is re-runnable and accepts an optional output path; the safe routine is *generate to a temp file → check the YAML parses and no `${VAR}` is undefined → move into place*. Glance reloads automatically when a config or included file changes.

### 5.3 Variables and secrets
- `/opt/glance/.env` is the **master**: `HOST_*` addresses (SVC, JELLY, AUTO, DEVUAN, PVE4, PVE2, PBS, PIHOLE1, PIHOLE2, ROUTER, CORE, OFFICE_SW, AP) and all secrets: `JELLYFIN_KEY`, `JELLYFIN_USER_ID`, `NAVIDROME_USER/TOKEN/SALT`, `SABNZBD_KEY`, `DEVUAN_SAB_KEY`, `RADARR_KEY`, `SONARR_KEY`, `LIDARR_KEY`, `PROWLARR_KEY`, `PRIVA_KEY`, `SEERR_KEY`, `SLSKD_KEY`, `AUDIOBOOKSHELF_KEY`, `PRIVB_KEY`, `IMMICH_URL/KEY`, `PIHOLE_KEY`, `PROXMOX_USER/PASSWORD`, `PBS_PASSWORD`, `TAILSCALE_OAUTH_ID/SECRET`, `NPM_USER/PASS`, `BOOKSTACK_TOKEN`, `PAPERLESS_TOKEN`, `FORGEJO_TOKEN`, `GLANCE_PIN`, `AGENT_TOKEN_DEVUAN/JELLY/SVC`.
- **`glance.env` is generated** by `python3 /opt/glance/tools/sync_env.py` and holds only the 28 variables referenced by `${VAR}` in the config. The Glance container reads this file, so it never receives Proxmox/PBS/NPM/Tailscale/token secrets.
- glance-admin gets its own subset from `/opt/stacks/glance-admin/.env` (mode 600).
- **Rules:** Glance **refuses to start if a `${VAR}` is undefined**, and env is only read when the container is created. So after adding a variable: add it to `.env` → `sync_env.py` → `cd /opt/stacks/glance && docker compose up -d`. Always scan for undefined variables first (sync_env does it).

---

## 6. The pages

### Home
Left: clock (London/New York/Tokyo), weather (London), calendar. Centre: **Find**, **per-engine search bars** (14: SearXNG, Startpage, YouTube, Reddit, MusicBrainz, Discogs, GitHub, Wikipedia, Hacker News, Amazon UK, Jellyfin, Lidarr, Seerr, BookStack), **Now playing** (Jellyfin + Navidrome). Right: server-side **Notes** and **To-do**.
- **Find** searches every tab (index of ~570 items built by glance-admin from Glance's own page output, refreshed every 5 min). ‹ › / Enter / Shift+Enter step through matches; stepping jumps to the right tab and rings the match; a small bottom-centre strip carries ‹ › ✕ on other tabs. Locked rows are never indexed.

### Downloads
SABnzbd + Seerr requests; **Radarr / Sonarr / Lidarr** rows (queue, missing, 30-day upcoming posters/covers; Lidarr adds upgradable and the **WBs_Lidarrdons** automation stats); right strip: Soulseek (slskd) and Prowlarr. **Locked section:** Private A and the second SABnzbd on devuan. Lidarr's calendar is served from glance-admin's cache because Lidarr takes ~7 s cold and Glance times out at 5 s.

### Audio
Netflix-style shelves from Navidrome (**recently added, recently played, most played, Discover from library** = random 20), **Audiobookshelf** (continue listening + recently added), **Songs that feel like**; side stats (Navidrome library, Audiobookshelf counts, MediaThatFeelsLike). **Locked row:** an Audiobookshelf library you mark private (set by `ABS_RESTRICTED`). Covers come through glance-admin (no token in the page).

### Video
Jellyfin **continue watching**, **recently added**, **Movies that feel like**, library counts. **Locked section:** Private B (stats + recent scenes) and Immich (photos/videos, disk, job queues, latest thumbnails).

### Infra
pve4 · pve2 · Proxmox Backup Server cards (CPU/RAM/load/rootfs/uptime, every LXC with RAM and disk bars, real failed tasks, backup coverage); **Dockge rows for services, jellyfin, devuan** (CPU/load, RAM, temperature, disks, Docker counts, every compose stack as a card of containers); a static **infrastructure map**; **Storage and backups** (Main20TB, devuan drives, PBS datastore, backup coverage per guest incl. stale groups); Hosts status strip. Data: `/api/infra/summary`.

### Networking
The hand-drawn **network topology** SVG (from BookStack › Networking), **Pi-hole 1 and 2**, routers and switches (HTTP up/down + latency), **Tailscale mesh** (all devices, online/offline, last seen, key expiry, updates; read-only OAuth client), **Nginx Proxy Manager** (all proxy hosts with a TCP check of each backend, certificates; view-only user).

### Tools
**RustyDisc**, rich cards for **Paperless-ngx** (counts only, no titles), **Forgejo**, **BookStack** (books you list in BOOKSTACK_HIDE_BOOKS are excluded), a grouped tile for every other tool (Flatnotes, Stirling PDF, CyberChef, IT Tools, Excalidraw, Picard, SearXNG, Firefox, Kiwix, Kolibri, Dozzle, NOMAD, Termix, Homebox, Vaultwarden), and **Latest releases** for 29 projects (built from GitHub's public release redirects/feeds: no API, no token, no rate limit).

### Cameras
Live Frigate tile(s), **auto-discovered from Frigate's config**; the stream attaches only while the tile is on screen and the tab visible (~120 KB/s), otherwise a still. Recent detections (thumbnails), Frigate status (detections 24 h, inference, CPU, storage, version), per-camera status, quick links. Needs no credentials (Frigate's internal port 5000).

### News Feeds
Left: Hacker News/Lobsters tabs, Tech news, UK & local. Centre: Music cards, tabbed Reddit groups (music, bands & taste, self-hosting, data hoarding & Linux), homelab articles. Right: Markets, Excel & work, media & obscure. All 31 subreddits kept.

### Video News Feed
One `videos` row per YouTube channel; add/remove through the **Channels box** (accepts @handle, link or UC id; the real id is found from the page's canonical link and verified against the channel's own feed title). Current channels live in `data/channels.json`.

### Bookmarks
20 groups / 201 links in three columns, edited through **Edit bookmarks** (add link with auto title + cached favicon, add group, move, remove, filter). Source of truth: `data/bookmarks.json`.

---

## 7. glance-admin

Python (stdlib only), `python:3.12-alpine`, non-root, 128 MB, healthcheck, `restart: unless-stopped`. **Mounts (read-write):** `/opt/glance/data` (state), `/opt/glance/config/data` (generated pages), `/opt/glance/assets/favicons` (icons). Nothing else.

| Endpoint | Purpose | Refresh / notes |
|---|---|---|
| `/health` | liveness + index/cache status | |
| `/api/notes`, `/api/todos[/id]` | server-side notes and to-do | files in `data/` |
| `/api/find`, `/api/find/reindex`, `/api/find/status` | cross-tab Find index | every 5 min; skips locked widgets |
| `/api/channels[/UC…]` | YouTube channel list (+ regenerates `video-news.yml`) | verified against feed title |
| `/api/bookmarks[/link|/group][/id]` | bookmark editor (+ regenerates `bookmarks.yml`) | only http(s); favicon + title fetched |
| `/api/infra/summary` | Proxmox, PBS, host agents/listers | 60 s |
| `/api/tailscale/summary`, `/api/npm/summary` | mesh and proxy hosts | 120 s / 60 s |
| `/api/tools/summary` | tool tiles + Paperless/Forgejo/BookStack | 90 s |
| `/api/releases/summary` | 29 projects' latest releases | 3 h |
| `/api/cameras/summary` | Frigate | 20 s |
| `/api/abs/continue|recent|stats` | Audiobookshelf (open vs restricted libraries) | 90 s |
| `/api/privb/summary`, `/api/immich/summary` | private rows | 120 s, **never written to disk** |
| `/api/lidarr/calendar` | Lidarr's 30-day calendar | 5 min (60 s retry) |
| `/api/(nd|abs|privb|immich)/cover/<id>` | image proxies (ids validated, size clamped, image types only) | Navidrome/ABS cached on disk; Private B/Immich never |

Summaries (infra, tailscale, npm, tools, releases, cameras, lidarr, abs-open) are saved to `data/cache/` and reloaded at startup, so a restart answers instantly. **Input limits:** bodies ≤ 256 KB, notes ≤ 100 KB, to-dos ≤ 500 chars, ≤ 40 channels, ≤ 1500 bookmarks.

---

## 8. Front-end scripts

- **`wb-home.js`** (version in the `?v=` of `glance.yml`; bump when changed): widgets for Find, search bars, notes, to-do, channels box, bookmarks editor, live camera streams. Glance injects page content after load, so everything is initialised by a MutationObserver on `[data-wb="…"]` placeholders (timer-based, **not** `requestAnimationFrame`, which pauses in background tabs).
- **`wb-restricted.js`** + `wb-restricted-config.js`: PIN gate for any widget with `css-class: wb-restricted`. Stores only a **salted SHA-256** of the PIN (own implementation: `crypto.subtle` is unavailable over plain http). One correct PIN unlocks all locked rows for the browser session; LOCK re-locks. Locked rows carry images as `data-src` so **nothing private is fetched until unlocked**. **This is casual privacy, not security:** the data is still in the page source.
- **`custom.css`**: wallpaper (`--bgh/--bgs/--bgl`, overlay 91–97 %), shelves/cards (`wb-strip`, `wb-card`), stats (`wb-stats`), tiles, topology, camera, bookmarks editor, mobile fixes (≤ 640 px).
- **Gotcha:** Glance versions the stylesheet URL only when the container starts. After a CSS-only edit, hard-refresh (Ctrl+Shift+R) **or** `docker restart glance`.

---

## 9. Locked ("restricted") content
Private A, SABnzbd (devuan), an Audiobookshelf library you mark private, Private B, Immich. Defaults: collapsed with a lock icon in the header; click → PIN; the Find index and highlighter skip them; their images load only after unlock. Container *names* (e.g. `privb`, `priva`, `immich_*`) are still visible on the Infra page's devuan row.

---

## 10. Operations runbook

| Task | How |
|---|---|
| Health check | `python3 /opt/glance/check_pages.py` (per page: size, widget errors) · `docker logs --tail 50 glance` · `curl http://192.168.1.110:3005/health` |
| Add a bookmark / group | Bookmarks tab → Edit bookmarks |
| Add a YouTube channel | Video News Feed → Channels box |
| Add a camera | Add it in Frigate; it appears on Cameras within ~20 s |
| Change a page's layout | edit `tools/gen_<page>.py`, generate to a temp file, validate, move into `config/pages/` |
| Add/rename a host address | edit `.env` → `python3 tools/sync_env.py` → `cd /opt/stacks/glance && docker compose up -d` |
| Add a secret for Glance | `.env` → `sync_env.py` → recreate Glance. For glance-admin: also `/opt/stacks/glance-admin/.env` + the compose `environment:` line → `docker compose up -d --build` |
| Change the PIN | set `GLANCE_PIN` in `.env`, regenerate `assets/glance/wb-restricted-config.js` (salt + SHA-256, see the Phase 3 log) |
| Upgrade Glance | change the image tag in `/opt/stacks/glance/compose.yaml`, `docker compose pull && up -d` |
| Rebuild glance-admin | `cd /opt/stacks/glance-admin && docker compose build && docker compose up -d` |
| Refresh the stylesheet | Ctrl+Shift+R, or `docker restart glance` |
| RustyDisc image builds leave 800 MB each | `docker image prune -f` after building |

**Do not hand-edit** `config/data/*.yml` (regenerated) or `glance.env` (generated).

---

## 11. Backups and rollback

`/mnt/Main20TB/Backups/dashboards/` (mode 700, contains secrets):
`pre-redesign-…` (original Glance **and** Homepage), `phase1-pre-…`, `phase2-done-…` … `phase11-done-…` (each: Glance, glance-admin, their stacks, and from Phase 6 the host-agent stack), plus `README-RESTORE.txt` in the first. Each `phaseN-done` is a restore point for that phase.

Restore pattern (example):
```
cd /opt/stacks/glance && docker compose down
mv /opt/glance /opt/glance.failed-$(date +%Y%m%d-%H%M%S)
tar -xzf /mnt/Main20TB/Backups/dashboards/<backup>/glance-and-admin-<ts>.tar.gz -C / opt/glance
cd /opt/stacks/glance && docker compose up -d
```
Backups live on the same host as the data (Main20TB) — they protect against bad edits, **not** loss of that disk. Old per-edit copies are in `/opt/glance/legacy/old-edits/` (moved, not deleted).

---

## 12. Security notes
- Glance and glance-admin have **no login**; LAN only. Anyone on the LAN can read the dashboard and call glance-admin's API (including editing bookmarks/channels/notes). Locked rows are a PIN gate, not authentication.
- glance-admin holds the Proxmox, PBS, Tailscale (read-only OAuth), NPM (view-only user), Paperless/Forgejo/BookStack, Private B, Immich, Audiobookshelf, Navidrome and Lidarr credentials; the Glance container itself holds only the 28 it uses.
- The Docker socket is mounted read-only into Glance (container list for local widgets) and into each lister (GET-only code).
- Tokens that were once hard-coded in Homepage (BookStack, Paperless, Forgejo) were exposed during the project; **rotation is pending** (deferred by the owner).

---

## 13. Known issues and things to watch
- **services LXC disk 86 %** (16 GB free of 115 GB); Docker images ~34 GB. Prune dangling images after RustyDisc builds.
- **Homebox** (NOMAD) crash-loops: needs `HBOX_AUTH_API_KEY_PEPPER`.
- **CT200 (automation) has no PBS backup group**; PBS holds a stale `host/pve1` group.
- **Updates available:** Paperless-ngx 2.20.15 → v3.2.x, Immich 3.2.2 → 3.2.4, Prowlarr.
- Several services were stopped for long periods before this project (Vaultwarden still stopped by choice).
- Live camera view works on the LAN (it loads directly from Frigate); over Tailscale it needs that subnet.
- A failed `custom-api` call shows as a widget error (Glance has no soft-fail for it).
- SNMP detail for the switches/routers was left as an optional later phase.

---

## Addendum: changes made after the reference above was written

These came out of the first round of real-world testing. Where this addendum and the text above disagree, this addendum wins.

- **Locked widgets hide their name.** While locked, a `wb-restricted` widget shows the title "Private" with no link (`maskTitle()` in `wb-restricted.js`); the real title and link come back after the PIN. Container, app and repository names that belong to private apps are flagged `private` by glance-admin (`PRIVATE_STACKS` regex) and are only listed inside locked widgets.
- **Infra** lists *every* physical disk on the Proxmox hosts (model, size, SMART health, SSD life left, what it is used for) from the Proxmox API, the real per-mount usage where a host agent reports it, and a diagram that shows every drive and mount. The role text for each disk is the `ROLES` table in `glance-admin/infra.py`: edit it when drives change. Per-mount usage for pve4 comes from an optional read-only service, `glance-disks` (`scripts/proxmox-host/`, systemd, port 27975, bearer token `AGENT_TOKEN_PVE4`); without it the list still shows model, size, health and role.
- **Audio**: Audiobookshelf shows *Continue listening* plus one random row per open library (the sample changes each time Glance refreshes the widget). The locked library row is titled "Audiobookshelf - More".
- **Networking**: the Nginx Proxy Manager widget lists problems (backend down / disabled) always, and every proxy host inside a collapsed "All proxy hosts" list.
- **Cameras**: *Recent detections* (30), *Detections by type* (one row per object type, e.g. person, car, cat), a 24-hour activity chart, and **Search detections by date and time**: pick a type, a camera and a range (last hour / 6 h / 24 h / 7 days / custom from-to) and scroll the results sideways. Search runs through `GET /api/cameras/events`, which validates every parameter before passing it to Frigate.
- **Carousels** (Glance's video rows and the cover strips) have left/right buttons on desktop; touch screens swipe. Added by `addArrows()` in `wb-home.js`.
- **Video News Feed**: each channel in the *Channels* box has a **Remove** button (click twice to confirm); adding is unchanged. Both go through glance-admin and regenerate the page file.
- **News Feeds** is now generated by glance-admin (`news.py`, state in `data/news.json`, page file `config/data/news.yml`). The **Feeds** box at the top of the middle column adds RSS feeds (it verifies that the address really is a feed, and will follow a page's "alternate feed" link) and subreddits (r/name; Reddit often refuses checks from servers, so an unconfirmed name is added with a warning), into any existing group or a new one, and removes them again. `tools/gen_news.py` is retired.
- **Bookmarks**: a group can be marked *private*; it is then rendered in its own locked widget ("Private bookmarks"). The Edit bookmarks panel only lists private groups, and only lets you add to them, while the page is unlocked in this tab. This is as strong as the other locks: casual privacy, not security.
- **Dev** tab (`gen_dev.py`, `glance-admin/dev.py`, `GET /api/dev/summary`): GitHub (profile, repos, events, PRs/issues, Actions runs, GraphQL contribution graph, language mix, API budget) and Forgejo (repos with last commit, heatmap, activity, issues), CI status, dev-tool tiles and recipe links, dev search. Private repositories/events are returned in a separate `private` block that only a locked widget renders and that is stripped before anything is cached to disk. The Forgejo card moved here from Tools, together with the CyberChef / IT Tools / Excalidraw / Dozzle / Termix tiles.
- **Page warmer**: glance-admin requests every page every 15 s (`WARM_SECONDS`, 0 = off) so Glance's widget caches are always fresh and tabs open instantly.
- Disk space on the Glance host: see the runbook in the README for the Docker and data clean-up checklist.
