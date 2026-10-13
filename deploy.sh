#!/bin/bash
# Copy this repo's scripts and config to their places on the Pi.
# Safe to re-run. Does not touch anything that needs sudo (see README for those steps).
#
# Usage: ./deploy.sh [user@host]      default admin@192.168.4.28
set -euo pipefail
PI="${1:-admin@192.168.4.28}"
HERE="$(cd "$(dirname "$0")" && pwd)"

ssh "$PI" 'mkdir -p ~/voice ~/hailo-live ~/hailo_test ~/yolo_test/scenes'
scp "$HERE"/voice/assistant.py "$HERE"/voice/listen.py        "$PI":~/voice/
scp "$HERE"/hailo-live/*                                       "$PI":~/hailo-live/
scp "$HERE"/hailo-test/classify.sh                             "$PI":~/hailo_test/
scp "$HERE"/hailo-test/compare.sh                              "$PI":~/yolo_test/
scp "$HERE"/pi-config/asoundrc                                 "$PI":~/.asoundrc
scp "$HERE"/pi-config/hailo-ollama.service                     "$PI":~/hailo-ollama.service
scp "$HERE"/README.md                                          "$PI":~/README.md
ssh "$PI" 'chmod +x ~/voice/*.py ~/hailo-live/run_live.sh ~/hailo_test/classify.sh ~/yolo_test/compare.sh'
echo "deployed to $PI"
