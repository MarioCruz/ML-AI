#!/bin/bash
# Copy this repo's scripts and config to their places on the Pi.
# Safe to re-run. Does not touch anything that needs sudo (see README for those steps).
#
# Usage: ./deploy.sh [user@host]      from the Mac; default admin@ml-ai.local
#        ./deploy.sh --local          on the Pi itself, from the git clone (~/ML-AI)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--local" ]; then
  # put SRC... DEST  (DEST starts with ~/)   run 'COMMANDS'
  put() { local dest="${!#}"; cp "${@:1:$#-1}" "${dest/#\~/$HOME}"; }
  run() { bash -c "$1"; }
  PI="this Pi"
else
  PI="${1:-admin@ml-ai.local}"
  put() { local dest="${!#}"; scp "${@:1:$#-1}" "$PI:$dest"; }
  run() { ssh "$PI" "$1"; }
fi

run 'mkdir -p ~/voice ~/web ~/hailo-live ~/hailo_test ~/yolo_test/scenes ~/rag/docs'
put "$HERE"/voice/*.py                                         ~/voice/
put "$HERE"/web/app.py "$HERE"/web/index.html                  ~/web/
put "$HERE"/hailo-live/*.py "$HERE"/hailo-live/*.sh "$HERE"/hailo-live/*.html ~/hailo-live/
put "$HERE"/hailo-test/classify.sh "$HERE"/hailo-test/vlm_test.py ~/hailo_test/
put "$HERE"/rag/rag.py                                         ~/rag/
put "$HERE"/hailo-test/compare.sh                              ~/yolo_test/
put "$HERE"/pi-config/asoundrc                                 ~/.asoundrc
put "$HERE"/pi-config/hailo-ollama.service                     ~/hailo-ollama.service
put "$HERE"/pi-config/pi-web.service                           ~/pi-web.service
put "$HERE"/pi-config/hailo-live.service                       ~/hailo-live.service
put "$HERE"/pi-config/voice.service                            ~/voice.service
put "$HERE"/README.md                                          ~/README.md
put "$HERE"/setup-pi.sh                                        ~/setup-pi.sh
run 'chmod +x ~/voice/*.py ~/hailo-live/*.sh ~/hailo_test/classify.sh ~/hailo_test/vlm_test.py ~/yolo_test/compare.sh ~/setup-pi.sh'
# Restart pi-web, voice and hailo-live by killing their main process: their units have
# Restart=always, so systemd starts them again with the new code. No-op for a service
# that is not installed.
run 'for u in pi-web voice hailo-live; do if systemctl is-active --quiet $u; then systemctl show -p MainPID --value $u | xargs -r kill; fi; done; sleep 6; for u in pi-web voice hailo-live; do systemctl is-active --quiet $u && echo "$u restarted" || echo "$u not running (sudo systemctl start $u)"; done'
echo "deployed to $PI"
