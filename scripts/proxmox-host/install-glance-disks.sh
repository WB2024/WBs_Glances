#!/usr/bin/env bash
# Optional: a read-only disk-usage reporter for a Proxmox host, so the Infra page can show per-mount usage.
# Run as root ON the Proxmox host:   TOKEN=<AGENT_TOKEN_PVE4 from your .env> scripts/proxmox-host/install-glance-disks.sh
# It serves GET /disks on port 27975 (bearer token), returning only device, mount point, filesystem type and sizes.
set -euo pipefail
: "${TOKEN:?set TOKEN to the value of AGENT_TOKEN_PVE4}"
here="$(cd "$(dirname "$0")" && pwd)"
install -d -m 755 /opt/glance-disks
install -m 755 "$here/glance-disks.py" /opt/glance-disks/glance-disks.py
printf 'GLANCE_DISKS_TOKEN=%s\nGLANCE_DISKS_PORT=27975\n' "$TOKEN" > /etc/glance-disks.env
chmod 600 /etc/glance-disks.env
cat > /etc/systemd/system/glance-disks.service <<'UNIT'
[Unit]
Description=Glance disks reporter (read-only mount usage)
After=network-online.target local-fs.target
[Service]
EnvironmentFile=/etc/glance-disks.env
ExecStart=/usr/bin/python3 /opt/glance-disks/glance-disks.py
Restart=on-failure
DynamicUser=yes
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now glance-disks.service
systemctl is-active glance-disks.service
