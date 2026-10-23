#!/bin/bash
# Fresh-card install of the Pi 5 + AI HAT+ 2 assistant, run ON THE PI as user admin.
#
#   Project files: git clone https://github.com/MarioCruz/ML-AI ~/ML-AI && ~/ML-AI/deploy.sh --local   (on the Pi)
#                  or, from the Mac:  ssh-copy-id admin@ml-ai.local && ./deploy.sh
#   On the Pi:    ~/setup-pi.sh                                       # asks for the sudo password once
#
# It is staged and re-runnable: each finished stage is recorded in ~/.setup-pi.done and
# skipped next time. Two stages need a reboot; the script says so and exits, then you run
# it again. Matches README.md "Fresh install, in order" with the HailoRT 5.3.0 fixes of
# Oct 19, 2026 (driver source patch for kernel >= 6.15, generic hailort packages, shared
# HAT between hailo-ollama and the camera pipeline, models in ~/.local/share/hailo-ollama).
set -euo pipefail

HAILO_VER=5.3.0
HAILO_URL=https://dev-public.hailo.ai/2026_04/Hailo10       # where Hailo published the 5.3.0 arm64 debs
HEF_URL=https://dev-public.hailo.ai/v5.3.0/blob             # compiled models, must match HAILO_VER
WHEEL=hailort-${HAILO_VER}-cp313-cp313-linux_aarch64.whl    # Python 3.13 (trixie)
LLM_MODELS="qwen2.5:1.5b llama3.2:1b"   # add qwen2.5-coder:1.5b or qwen3:1.7b if wanted (1.7 / ~2 GB each)
VOSK_ZIP=vosk-model-small-en-us-0.15.zip
PIPER_VOICE=en_US-lessac-medium
DONE=~/.setup-pi.done
HAILO_DIR=~/hailo530

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
done_() { grep -qx "$1" "$DONE" 2>/dev/null; }
mark() { echo "$1" >> "$DONE"; }
need_reboot() { say "$1"; echo "Reboot now, then run ~/setup-pi.sh again:  sudo reboot"; exit 0; }

[ "$(id -un)" = admin ] || { echo "run as user admin"; exit 1; }
[ -f ~/voice/assistant.py ] || { [ -x ~/ML-AI/deploy.sh ] && ~/ML-AI/deploy.sh --local; }
[ -f ~/voice/assistant.py ] && [ -f ~/hailo-ollama.service ] || { echo "project files missing: run ~/ML-AI/deploy.sh --local on the Pi (or ./deploy.sh from the Mac) first"; exit 1; }
touch "$DONE"

say "sudo password (kept alive while the script runs)"
sudo -v
( while true; do sudo -n true; sleep 50; done ) 2>/dev/null &
KEEPALIVE=$!
trap 'kill $KEEPALIVE 2>/dev/null || true' EXIT

# ---------------------------------------------------------------- 1. OS packages
if ! done_ apt; then
  say "1. apt update, full-upgrade, packages"
  sudo apt update
  sudo apt full-upgrade -y
  sudo apt install -y dkms build-essential linux-headers-rpi-2712 git curl unzip ffmpeg \
      poppler-utils tesseract-ocr python3-venv python3-dev python3-picamera2 hailo-models
  # hailo-models = the vision HEFs in /usr/share/hailo-models (yolov8m_h10, yolov11m_h10, resnet ...).
  # NOT hailo-h10-all / hailo-tappas-core from apt: they bring HailoRT 5.1.1 and TAPPAS 5.1.0;
  # the 5.3.0 versions come from Hailo's bucket in stage 3.
  mark apt
  # only the Pi 5 flavour (-2712): the image also ships -v8 for the Pi 4, which sorts after it
  newest=$(ls -1 /lib/modules | grep -- "-2712$" | sort -V | tail -1)
  [ "$newest" = "$(uname -r)" ] || need_reboot "Kernel updated ($(uname -r) -> $newest)"
fi

# ---------------------------------------------------------------- 2. kernel cmdline sanity
if ! done_ cmdline; then
  say "2. kernel command line: no cma= (breaks the camera, README 6b), no leftover fsck.mode=force"
  if grep -q "cma=\|fsck.mode=force" /boot/firmware/cmdline.txt; then
    sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
    # fsck.mode=force is the way to get a full root fsck on this image (the /forcefsck file is
    # ignored for root); it is added by hand after a corruption, and removed here so the 57 GB
    # root is not checked on every boot.
    sudo sed -i -e 's/ *cma=[0-9]*[MmKk]//' -e 's/ *fsck.mode=force//' /boot/firmware/cmdline.txt
    mark cmdline
    need_reboot "Cleaned cmdline.txt"
  fi
  mark cmdline
fi

# ---------------------------------------------------------------- 3. HailoRT 5.3.0
if ! done_ hailo; then
  say "3. HailoRT $HAILO_VER: runtime, PCIe driver, GenAI model zoo"
  mkdir -p "$HAILO_DIR" && cd "$HAILO_DIR"
  for f in hailort_${HAILO_VER}_arm64.deb hailort-pcie-driver_${HAILO_VER}_all.deb hailo_gen_ai_model_zoo_${HAILO_VER}_arm64.deb hailo-tappas-core_${HAILO_VER}_arm64.deb $WHEEL; do
    [ -s "$f" ] || curl -fL --progress-bar -o "$f" "$HAILO_URL/$f"
  done
  dpkg -l | grep -q "^ii *hailo-h10-all" && sudo apt remove -y hailo-h10-all h10-hailort h10-hailort-pcie-driver python3-h10-hailort || true
  # Unpack first, patch the driver source for kernels >= 6.15 (del_timer_sync was removed), then configure.
  sudo dpkg --unpack hailort_${HAILO_VER}_arm64.deb hailort-pcie-driver_${HAILO_VER}_all.deb hailo_gen_ai_model_zoo_${HAILO_VER}_arm64.deb
  sudo sed -i 's/\bdel_timer_sync(/timer_delete_sync(/' /usr/src/hailort-pcie-driver/linux/vdma/monitor.c
  sudo dpkg --configure -a
  # TAPPAS (GStreamer hailonet/hailofilter/hailooverlay) through apt so its -dev dependencies resolve
  sudo apt install -y "$HAILO_DIR/hailo-tappas-core_${HAILO_VER}_arm64.deb"
  sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable hailo-ollama
  mark hailo
  need_reboot "HailoRT $HAILO_VER installed"
fi
say "Hailo check"
hailortcli fw-control identify | grep -i "firmware version" || { echo "Hailo device not responding; check lspci and dmesg"; exit 1; }
ls -l /dev/h1x-0

# ---------------------------------------------------------------- 4. voice environment
if ! done_ venv; then
  say "4. Python venv: Vosk, Piper, Flask, embeddings, OpenCV, HailoRT Python API"
  [ -d ~/voice/.venv ] || python3 -m venv ~/voice/.venv
  ~/voice/.venv/bin/pip install --upgrade pip wheel >/dev/null
  ~/voice/.venv/bin/pip install vosk==0.3.45 requests sounddevice piper-tts==1.8.0 flask fastembed opencv-python-headless numpy
  ~/voice/.venv/bin/pip install "$HAILO_DIR/$WHEEL"
  if [ ! -d ~/voice/model ]; then
    cd ~/voice && curl -fL --progress-bar -O "https://alphacephei.com/vosk/models/$VOSK_ZIP" && unzip -q "$VOSK_ZIP" && mv "${VOSK_ZIP%.zip}" model && rm "$VOSK_ZIP"
  fi
  if [ ! -f ~/voice/piper/$PIPER_VOICE.onnx ]; then
    mkdir -p ~/voice/piper && cd ~/voice/piper && ~/voice/.venv/bin/python -m piper.download_voices $PIPER_VOICE
  fi
  mark venv
fi

# ---------------------------------------------------------------- 5. services
if ! done_ services; then
  say "5. systemd services: hailo-ollama (8000), pi-web (80), hailo-live (camera), voice (mic)"
  sudo cp ~/hailo-ollama.service ~/pi-web.service ~/hailo-live.service ~/voice.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo loginctl enable-linger admin
  sudo systemctl enable --now hailo-ollama pi-web voice hailo-live
  mark services
fi

# ---------------------------------------------------------------- 6. LLM models and the VLM
if ! done_ models; then
  say "6. pull LLMs into hailo-ollama: $LLM_MODELS"
  for i in $(seq 1 30); do curl -s -m 3 http://127.0.0.1:8000/api/tags >/dev/null && break; sleep 2; done
  for m in $LLM_MODELS; do
    echo "-- $m"
    curl -s -N -X POST http://127.0.0.1:8000/api/pull -H "Content-Type: application/json" -d "{\"model\":\"$m\"}" | tr '}' '\n' | tail -1; echo
  done
  curl -s http://127.0.0.1:8000/api/tags | python3 -c 'import json,sys; print("pulled:", [m["name"] for m in json.load(sys.stdin)["models"]])'
  say "   Qwen2-VL-2B for vlm_test.py (3.2 GB)"
  [ -s "$HAILO_DIR/Qwen2-VL-2B-Instruct.hef" ] || curl -fL --progress-bar -C - -o "$HAILO_DIR/Qwen2-VL-2B-Instruct.hef" "$HEF_URL/Qwen2-VL-2B-Instruct.hef"
  mark models
fi

# ---------------------------------------------------------------- 7. documents for RAG
if ! done_ rag; then
  say "7. RAG index over ~/rag/docs (PDF, .txt, .md)"
  mkdir -p ~/rag/docs
  if ls ~/rag/docs/* >/dev/null 2>&1; then
    ~/voice/.venv/bin/python ~/rag/rag.py build
  else
    echo "   no documents yet: copy some into ~/rag/docs/ and run  ~/voice/.venv/bin/python ~/rag/rag.py build"
  fi
  mark rag
fi

# ---------------------------------------------------------------- done
say "Checks"
grep CmaTotal /proc/meminfo
rpicam-hello --list-cameras 2>/dev/null | grep -m1 imx708 || echo "camera not listed (is it connected?)"
arecord -D plughw:CARD=Device,DEV=0 -f S16_LE -r 16000 -c 1 -d 1 /tmp/mic.wav 2>/dev/null && echo "USB mic ok" || echo "USB mic not found (is the USB PnP Sound Device plugged in?)"
systemctl is-active hailo-ollama pi-web voice hailo-live | paste -sd' ' | sed 's/^/services: /'
curl -s -m 5 http://127.0.0.1/api/status | head -c 200; echo
say "Done. Page: http://ml-ai.local/   Checklist: README.md 'Test checklist'"
