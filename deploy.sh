#!/bin/bash
# Copy this repo's scripts and config to their places on the Pi.
# Safe to re-run. Does not touch anything that needs sudo (see README for those steps).
#
# Usage: ./deploy.sh [user@host]      default admin@ml-ai.local
set -euo pipefail
PI="${1:-admin@ml-ai.local}"
HERE="$(cd "$(dirname "$0")" && pwd)"

ssh "$PI" 'mkdir -p ~/voice ~/web ~/hailo-live ~/hailo_test ~/yolo_test/scenes ~/rag/docs'
scp "$HERE"/voice/*.py                                         "$PI":~/voice/
scp "$HERE"/web/app.py "$HERE"/web/index.html                  "$PI":~/web/
scp "$HERE"/hailo-live/*                                       "$PI":~/hailo-live/
scp "$HERE"/hailo-test/classify.sh "$HERE"/hailo-test/vlm_test.py "$PI":~/hailo_test/
scp "$HERE"/rag/rag.py                                          "$PI":~/rag/
scp "$HERE"/hailo-test/compare.sh                              "$PI":~/yolo_test/
scp "$HERE"/pi-config/asoundrc                                 "$PI":~/.asoundrc
scp "$HERE"/pi-config/hailo-ollama.service                     "$PI":~/hailo-ollama.service
scp "$HERE"/pi-config/pi-web.service                           "$PI":~/pi-web.service
scp "$HERE"/pi-config/hailo-live.service                       "$PI":~/hailo-live.service
scp "$HERE"/pi-config/voice.service                            "$PI":~/voice.service
scp "$HERE"/README.md                                          "$PI":~/README.md
ssh "$PI" 'chmod +x ~/voice/*.py ~/hailo-live/run_live.sh ~/hailo_test/classify.sh ~/yolo_test/compare.sh'
# Reload the web app if it runs as the pi-web service (Restart=always brings it
# back with the new files). No-op if the service is not installed.
ssh "$PI" 'if systemctl is-active --quiet pi-web; then pkill -f "^/home/admin/voice/.venv/bin/python /home/admin/web/app.py"; sleep 5; systemctl is-active --quiet pi-web && echo "pi-web restarted" || echo "pi-web did not come back: run sudo systemctl restart pi-web"; fi'
# Same trick for the voice assistant and the live camera (both Restart=always).
ssh "$PI" 'for u in voice hailo-live; do if systemctl is-active --quiet $u; then systemctl show -p MainPID --value $u | xargs -r kill; fi; done; sleep 6; for u in voice hailo-live; do systemctl is-active --quiet $u && echo "$u restarted" || echo "$u not running (sudo systemctl start $u)"; done'
echo "deployed to $PI"
