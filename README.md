# Raspberry Pi 5 + AI HAT+ 2 voice assistant (ML-AI)

A Raspberry Pi 5 with an AI HAT+ 2 (Hailo-10H) that listens on a USB mic, answers with a local LLM running on the Hailo, speaks the answer with Piper, and can run YOLO object detection on the Pi camera. Everything runs offline on the Pi. This is the base for the Moonlighter FabLab high-school AI program.

- Pi: `admin@ml-ai.local` (mDNS; the DHCP address changed from 192.168.4.28 to 192.168.4.69 on Oct 19, 2026, so use the name), hostname `ML-AI`, Raspberry Pi OS (Debian 13 trixie, 64-bit), kernel 6.18, Python 3.13, 8 GB RAM, 32 GB SD.
- Passwordless sudo is **not** set up. Steps marked **(sudo)** below must be run in an interactive terminal; from the Mac, `ssh -t admin@ml-ai.local 'sudo ...'` prompts for the password.

## What is in this repo

| Path | Goes to (on the Pi) | What it is |
|---|---|---|
| `voice/assistant.py` | `~/voice/` | Voice → LLM → voice assistant (Vosk + hailo-ollama + Piper) |
| `voice/listen.py` | `~/voice/` | The original fixed-command Vosk listener (lights on/off etc., placeholder actions) |
| `voice/stt_fix.py` | `~/voice/` | Vocabulary corrections applied to every transcript ("pie"→"pi", "i had"→"ai hat", …) |
| `voice/stt_bench.py` | `~/voice/` | Measures word error rate and speed of Vosk models on a WAV test set |
| `hailo-live/` | `~/hailo-live/` | Live YOLO11m on the camera with a browser viewer |
| `hailo-test/classify.sh` | `~/hailo_test/` | ResNet-50 classification of one image on the Hailo |
| `hailo-test/compare.sh` | `~/yolo_test/` | YOLOv8m vs YOLO11m side-by-side on a folder of images |
| `pi-config/asoundrc` | `~/.asoundrc` | Defines the `usbmic` ALSA device |
| `pi-config/hailo-ollama.service` | `/etc/systemd/system/` **(sudo)** | Runs the LLM server at boot |
| `pi-config/hailo-live.service` | `/etc/systemd/system/` **(sudo)** | Runs the live YOLO camera viewer at boot |
| `pi-config/voice.service` | `/etc/systemd/system/` **(sudo)** | Runs the voice assistant (mic) at boot |
| `web/app.py`, `web/index.html` | `~/web/` | Web front end on port 80 (http://ml-ai.local/): chat, speak, hold-to-talk, live transcript, camera |
| `rag/rag.py` | `~/rag/` | Retrieval over the documents in `~/rag/docs/` (index, search, prompt assembly); used by the assistant and the web page |
| `pi-config/pi-web.service` | `/etc/systemd/system/` **(sudo)** | Runs the web front end at boot |
| `voice/llm_bench.py` | `~/voice/` | CPU-vs-Hailo LLM benchmark (speed, CPU load, saved answers) |
| `deploy.sh` | — | Copies all of the above to the Pi (everything except the sudo step) |

## Hardware

- Raspberry Pi 5 (8 GB) with active cooler and 27 W PSU
- Raspberry Pi AI HAT+ 2 (Hailo-10H, 8 GB on-board RAM) on the PCIe connector. No `dtparam=pciex1` line and no stacking board were needed; it was detected as soon as it was seated properly. The link already runs at **PCIe Gen 3 (8.0 GT/s) x1** with no `pciex1_gen=3` line (Raspberry Pi OS negotiates Gen 3 for HAT+ boards automatically; check with `cat /sys/bus/pci/devices/0001:01:00.0/current_link_speed`). The Hailo-10H supports x4 but the Pi 5 has one lane, so there is nothing to gain from PCIe settings.
- Raspberry Pi Camera Module 3 (IMX708) on the CSI connector
- USB microphone: TI PCM2902 codec ("USB PnP Sound Device"), capture only
- Audio out: HDMI for now (needs a display with audio plugged into HDMI0). A USB speaker can be added later with no code change.

## Fresh install, in order

**The short way (new SD card):** flash Raspberry Pi OS 64-bit (trixie) with user `admin`, SSH and Wi-Fi enabled, then from the Mac `ssh-copy-id admin@ml-ai.local && ./deploy.sh`, and on the Pi `~/setup-pi.sh`. The script (`setup-pi.sh` in the repo) does steps 1 to 7 below in order, records each finished stage in `~/.setup-pi.done`, stops twice to ask for a reboot (kernel update, Hailo driver) and continues where it left off when run again. It installs HailoRT 5.3.0 straight away (generic `hailort` packages from Hailo's bucket plus the one-line driver patch for kernel 6.15+, see 2c), not the 5.1.1 that `hailo-h10-all` would bring, and it leaves nothing on the Pi CPU except Vosk, Piper and the embedding model. The long way is the rest of this section.

### 1. OS, SSH, updates

Flash Raspberry Pi OS 64-bit (trixie) with the Imager, set user `admin`, enable SSH and Wi-Fi. Then:

```
ssh-copy-id admin@ml-ai.local                      # from the Mac, key login
ssh -t admin@ml-ai.local 'sudo apt update && sudo apt full-upgrade -y && sudo reboot'   # (sudo)
```

### 2. Hailo driver for the AI HAT+ 2 (sudo)

`hailo-h10-all` is for the AI HAT+ 2. Do not install `hailo-all` (that is for the older AI Kit / AI HAT+); they conflict.

```
ssh -t admin@ml-ai.local 'sudo apt install -y dkms hailo-h10-all && sudo reboot'
```

Verify after the reboot:

```
lspci | grep -i hailo                 # Hailo-10H at 0001:01:00.0
ls -l /dev/h1x-0                      # was /dev/hailo0 up to HailoRT 5.2.0; 5.3.0 renamed it
hailortcli fw-control identify        # Firmware 5.3.0, Device Architecture: HAILO10H
```

A fresh install from the Raspberry Pi repo (checked Oct 12, 2026) gives HailoRT 5.1.1. It pulls in `h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`, `hailo-tappas-core` 5.1.0, `hailo-models` 1.0.0 (the `.hef` files in `/usr/share/hailo-models/`), and `rpicam-apps-hailo-postprocess`. Step 2b upgrades it to 5.2.0, which is what this Pi runs now.

### 2b. Upgrade to HailoRT 5.2.0 (sudo, optional)

Download the three packages from Hailo's server (the same server as the 5.1.1 zoo `.deb`, see step 6) into `~/hailo520/` on the Pi: `hailort_5.2.0_arm64.deb`, `hailort-pcie-driver_5.2.0_all.deb`, `hailo_gen_ai_model_zoo_5.2.0_arm64.deb`. Install all three together, or the driver and runtime versions will not match (`HAILO_INVALID_DRIVER_VERSION`):

```
ssh -t admin@ml-ai.local 'sudo dpkg -i ~/hailo520/hailort_5.2.0_arm64.deb ~/hailo520/hailort-pcie-driver_5.2.0_all.deb ~/hailo520/hailo_gen_ai_model_zoo_5.2.0_arm64.deb && sudo reboot'   # (sudo)
```

Before upgrading, save the package list so you can roll back: `dpkg -l 'h10*' 'hailo*' > ~/hailo-rollback-5.1.1.txt`. The zoo install replaces `/usr/share/hailo-ollama`, so the models must be pulled again afterwards (step 6). Verify `hailortcli fw-control identify` shows firmware 5.2.0.

### 2c. Upgrade to HailoRT 5.3.0 (sudo, done Oct 19, 2026)

Why: 5.3.0 lets `hailo-ollama` share the HAT with the camera pipeline (`HAILO_OLLAMA_VDEVICE_GROUP_ID`, set in `pi-config/hailo-ollama.service`; `hailonet vdevice-group-id=HAILO_OLLAMA_SHARED` in `run_live.sh` and `compare.sh`). It also adds Qwen3-1.7B and Qwen3-VL-2B. Same procedure as 2b; the packages come from `https://dev-public.hailo.ai/2026_04/Hailo10/`. This Pi runs the generic `hailort` package, so the `hailo-gen-ai-model-zoo` "Depends: hailort" that breaks `hailo-h10-all` installs ([forum report](https://community.hailo.ai/t/bug-report-hailo-gen-ai-model-zoo-5-3-0-uninstallable-on-raspberry-pi-with-hailo-10h/19226)) is satisfied here.

```
mkdir -p ~/hailo530 && cd ~/hailo530 && for f in hailort_5.3.0_arm64.deb hailort-pcie-driver_5.3.0_all.deb hailo_gen_ai_model_zoo_5.3.0_arm64.deb hailort-5.3.0-cp313-cp313-linux_aarch64.whl; do wget -q https://dev-public.hailo.ai/2026_04/Hailo10/$f; done
dpkg -l | grep -i hailo > ~/hailo-rollback-5.2.0.txt                     # what was installed, for rollback (5.2.0 debs stay in ~/hailo520)
ssh -t admin@ml-ai.local 'sudo dpkg -i ~/hailo530/hailort_5.3.0_arm64.deb ~/hailo530/hailort-pcie-driver_5.3.0_all.deb ~/hailo530/hailo_gen_ai_model_zoo_5.3.0_arm64.deb && sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo reboot'   # (sudo); the driver rebuilds through dkms, a few minutes
```

**The 5.3.0 driver does not build on kernel 6.15+ as shipped:** `linux/vdma/monitor.c` calls `del_timer_sync`, removed from the kernel in 6.15 (renamed `timer_delete_sync` in 6.2). The `dpkg -i` above therefore fails at the driver's post-install (`/var/log/hailort-pcie-driver.deb.log`: "implicit declaration of function 'del_timer_sync'"), leaves the package half-configured, and the `&&` chain stops before the reboot. The 5.2.0 module stays loaded, so nothing breaks yet. Fix the one line and finish the install (tested: the patched driver compiles against 6.18.50; the package's udev rule gives the device node mode 0666, so no group setup is needed):

```
ssh -t admin@ml-ai.local 'sudo sed -i "s/del_timer_sync(/timer_delete_sync(/" /usr/src/hailort-pcie-driver/linux/vdma/monitor.c && sudo systemctl stop hailo-ollama && sudo dpkg --configure hailort-pcie-driver && sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo reboot'   # (sudo)
```

Also from the same bucket: `hailo-tappas-core_5.3.0_arm64.deb` (`sudo apt install -y ~/hailo530/hailo-tappas-core_5.3.0_arm64.deb`; apt resolves its -dev dependencies). It turned out not to matter for sharing, `hailonet` lives in HailoRT's own `libgsthailo.so`, but it keeps TAPPAS and HailoRT at the same version. After that apt lists `hailo-models` as auto-removable because the `hailo-h10-all` meta-package is gone: `sudo apt-mark manual hailo-models hailo-tappas-core` and never `apt autoremove` blindly.

After the reboot: `hailortcli fw-control identify` must say 5.3.0; the zoo package resets the model store, so re-pull the models (step 6; about 2 MB/s); reinstall the Python wheel for the VLM (`~/voice/.venv/bin/pip install ~/hailo530/hailort-5.3.0-cp313-cp313-linux_aarch64.whl`) and fetch the 5.3.0 VLM HEF (`wget -O ~/hailo530/Qwen2-VL-2B-Instruct.hef https://dev-public.hailo.ai/v5.3.0/blob/Qwen2-VL-2B-Instruct.hef`). Then `sudo systemctl enable --now hailo-live` and check that a chat works while the camera panel is live.

### 3. Camera

Nothing to install. Check and take a still:

```
rpicam-hello --list-cameras           # should list imx708
rpicam-still -n -t 2000 --width 640 --height 640 -o test.jpg
```

If `rpicam-hello` says "rpicam-apps currently only supports the Raspberry Pi platforms", the firmware mailbox is broken; check `cmdline.txt` for a `cma=` parameter (see 6b).

### 4. Microphone

The system default ALSA input does not work with this codec, so a named device is defined in `~/.asoundrc` (`pi-config/asoundrc`). It references the card by name and uses `plug`, so 16 kHz mono capture works even though the hardware runs at 48 kHz. Copy it with `deploy.sh`, then test:

```
arecord -D usbmic -f S16_LE -r 16000 -c 1 -d 3 test.wav
```

### 5. Voice environment (no sudo)

```
python3 -m venv ~/voice/.venv
~/voice/.venv/bin/pip install vosk==0.3.45 requests sounddevice piper-tts==1.8.0

# Vosk speech-to-text model (small US English, 68 MB)
cd ~/voice && curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
  && unzip -q vosk-model-small-en-us-0.15.zip && mv vosk-model-small-en-us-0.15 model && rm vosk-model-small-en-us-0.15.zip

# Piper text-to-speech voice (63 MB)
mkdir -p ~/voice/piper && cd ~/voice/piper && ~/voice/.venv/bin/python -m piper.download_voices en_US-lessac-medium
```

`piper-tts` from pip was used instead of apt's `piper` so no sudo is needed; it brings `onnxruntime` with it.

### 6. LLM server on the Hailo (sudo for two steps)

`hailo-ollama` is Hailo's Ollama-compatible server. It runs curated HEF LLMs on the Hailo-10H's own 8 GB. Stock Ollama is CPU-only and is not used. Package version must match HailoRT (5.2.0 on this Pi; the 5.1.1 zoo package goes with 5.1.1). Source: the [official Raspberry Pi AI docs](https://www.raspberrypi.com/documentation/computers/ai.html).

```
cd ~ && wget https://dev-public.hailo.ai/2025_12/Hailo10/hailo_gen_ai_model_zoo_5.2.0_arm64.deb   # check the directory name on Hailo's server if this 404s
ssh -t admin@ml-ai.local 'sudo dpkg -i ~/hailo_gen_ai_model_zoo_5.2.0_arm64.deb'                   # (sudo)
```

If you are on 5.1.1, use `hailo_gen_ai_model_zoo_5.1.1_arm64.deb` (7.9 MB) instead. If you did step 2b, the zoo package is already installed, so skip this step.

Install the service (unit file comes from `pi-config/hailo-ollama.service` via `deploy.sh`; it runs as `admin`, restarts on failure, working directory `/home/admin`):

```
ssh -t admin@ml-ai.local 'sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hailo-ollama'   # (sudo)
```

Pull the models (about 1.5–2 MB/s here, so 15–20 minutes each). Pull them again after any zoo package install, because that replaces the model store:

```
curl -s http://127.0.0.1:8000/hailo/v1/list        # zoo (5.2.0): qwen2.5:1.5b, qwen2.5-coder:1.5b, qwen2:1.5b, llama3.2:1b, deepseek_r1:1.5b
for m in qwen2.5:1.5b qwen2.5-coder:1.5b; do
  curl -s http://127.0.0.1:8000/api/pull -H 'Content-Type: application/json' -d "{\"model\": \"$m\", \"stream\": true}" | tail -c 200; echo
done
curl -s http://127.0.0.1:8000/api/tags             # shows what is pulled
```

Models land in `/usr/share/hailo-ollama/models/blob/` up to 5.2.0 and in `~/.local/share/hailo-ollama/models/blob/` from 5.3.0 (the three models together about 6 GB; the 5.2.0 blobs are left behind in the old place and can be deleted). On Oct 19, 2026 pulls ran at about 29 MB/s, so a model takes 1–3 minutes; the 2 MB/s seen a week earlier was not the norm. Config is `/etc/xdg/hailo-ollama/hailo-ollama.json`; it binds `0.0.0.0:8000`, so the API is reachable from the LAN. Change `host` to `127.0.0.1` to keep it Pi-only.

### 6b. CMA memory pool: leave it at the default

Hailo's driver uses a contiguous memory pool (CMA), 64 MB by default. On Oct 13, 2026 it was raised to 256 MB with `cma=256M` on the kernel command line. **Don't do this.** Two results:

- It did not help the LLM: `qwen2.5:1.5b` on the Hailo ran at 6.8 tok/s at 64 MB and 6.8 tok/s at 256 MB.
- It broke the camera, the 3D core and `vcgencmd`. A `cma=` command-line parameter bypasses the device tree's `alloc-ranges`, so the pool was placed at 0xde000000 (3.5 GB), out of reach of the VideoCore firmware. Every firmware mailbox request then returns status 0, the `raspberrypi-clk` driver fails with -22, and `v3d`, `pispbe` (the ISP) and the HEVC decoder never probe. Symptoms: `rpicam-hello --list-cameras` says "rpicam-apps currently only supports the Raspberry Pi platforms", `picamera2` lists no cameras, `vcgencmd version` says `ioctl_set_msg failed`. See [raspberrypi/linux #7230](https://github.com/raspberrypi/linux/issues/7230).

Revert (the original file was saved as `cmdline.txt.bak`):

```
ssh -t admin@ml-ai.local 'sudo cp /boot/firmware/cmdline.txt.bak /boot/firmware/cmdline.txt && sudo reboot'   # (sudo)
```

After the reboot `grep CmaTotal /proc/meminfo` should show `65536 kB` and `rpicam-hello --list-cameras` should list the imx708. If a bigger pool is ever wanted, use `dtoverlay=vc4-kms-v3d,cma-256` in `config.txt` instead, which keeps the placement limits.

### 7. Copy the scripts

From the Mac, in this repo:

```
./deploy.sh
```

## Running

### Voice assistant

```
~/voice/.venv/bin/python ~/voice/assistant.py
```

Speak a question; it transcribes with Vosk, asks `qwen2.5:1.5b` on the Hailo (short-answer system prompt, last 4 turns kept as context), streams the reply, and speaks each sentence with Piper as it completes (first word about 0.5 s after you stop talking). Mic input is dropped while it speaks. Say "stop listening" to quit.

Options:

- `--confirm` say "I heard: …" before answering, so a mis-heard question is obvious
- `--stt-model small|big|DIR` speech model (default `small`; see "Speech recognition accuracy" below)
- `--no-fix` turn off the vocabulary corrections in `stt_fix.py`
- `--text` type questions instead of speaking (same prompt, history and speech)
- `--no-tts` print only
- `--wav file.wav` feed a 16 kHz mono 16-bit WAV instead of the mic
- `--wake "hey pi"` only answer utterances that start with the phrase
- `--model qwen2.5-coder:1.5b` use another pulled model (switching models costs ~10 s on the Hailo; only one is loaded at a time)
- `--out pw|hdmi|usb|DEVICE` where to play: `pw` (default) uses PipeWire's current default sink; `hdmi` / `usb` force that output through `aplay`; anything else is an ALSA device name

### Web front end

**http://ml-ai.local/** from any device on the network (port 80; it was 80 before Oct 19, 2026). It runs as the systemd service `pi-web` (installed Oct 13, 2026, moved to port 80 on Oct 19; starts at boot after `hailo-ollama`). Manage with `sudo systemctl {status,restart,stop} pi-web`; logs via `journalctl -u pi-web -n 50`. To install it on a fresh Pi (**sudo**):

```
ssh -t admin@ml-ai.local 'sudo cp ~/pi-web.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now pi-web'
```

If you ever start it by hand instead (`~/voice/.venv/bin/python ~/web/app.py`), stop that copy before enabling the service: two instances cannot share port 80, and the service will crash-loop with "Address already in use" until the hand-started one is gone (`pkill -f "^/home/admin/voice/.venv/bin/python app.py"`). After editing `web/app.py` or `index.html`, just run `./deploy.sh`: it copies the files and kills the running app, and the unit's `Restart=always` starts it again with the new code, no sudo needed. (With the earlier `Restart=on-failure` a clean kill left the service stopped; that is why it was changed.)

The model picker lists the models pulled into hailo-ollama (port 8000), tagged "AI HAT+ 2". The code can route to more than one Ollama-style server (`BACKENDS` in `web/app.py`); the CPU server used for the "CPU vs Hailo" comparison was removed on Oct 19, 2026, so only the HAT is listed.

What the page does (all against the same pieces the voice assistant uses):

- **Chat**: type a question, the reply streams in from `hailo-ollama` with the same short-answer prompt and 4-turn history as `assistant.py`. A model picker lists what's pulled. "New conversation" clears the history.
- **Speak replies on the Pi**: when checked, each sentence is spoken through the Pi's audio output (Piper, PipeWire default sink) in order while the text keeps streaming. Set `ASSISTANT_OUT=hdmi|usb|<alsa device>` in the service file to force an output.
- **Hold to talk**: records on the laptop/phone, sends the audio to the Pi, transcribes it with Vosk (small model) plus `stt_fix.py`, and asks the question. **Browsers only allow mic access on HTTPS or `localhost`**, so over plain `http://ml-ai.local` the button will report "mic not available" in Chrome/Safari. Workarounds: open `chrome://flags/#unsafely-treat-insecure-origin-as-secure` and add `http://ml-ai.local`; or run the page over HTTPS with a self-signed certificate (not set up yet). Typing and the Pi's own USB mic are unaffected.
- **Voice assistant transcript**: live `HEARD:` / `ANSWER:` lines from `assistant.py` (it appends each to `~/voice/transcript.jsonl`; the page follows that file). Lets a room see what the mic understood.
- **Camera**: shows the latest YOLO frame while `~/hailo-live/run_live.sh` is running (it checks the frame is under 5 s old).

Endpoints, for students who want to build on it: `POST /api/chat` (NDJSON stream), `POST /api/transcribe` (audio body → `{text, raw}`), `POST /api/speak`, `POST /api/reset`, `GET /api/transcript` (server-sent events), `GET /api/camera`, `GET /api/status`. Needs `flask` in the voice venv (`~/voice/.venv/bin/pip install flask`) and `ffmpeg` (already on the Pi). Ports in use on the Pi: 8000 `hailo-ollama`, 8001 live camera viewer, 80 this page.

### Everything at boot

Four services, all as user `admin`, all from `pi-config/` (copied to `~` by `deploy.sh`). One sudo command installs the two new ones, moves the web page to port 80 and keeps the user session (PipeWire, USB mic) alive without a login. All four run together since HailoRT 5.3.0 (Oct 19, 2026); on 5.2.0 `hailo-live` had to stay disabled, see the HAT-sharing note below the table.

```
ssh -t admin@ml-ai.local 'sudo cp ~/pi-web.service ~/hailo-live.service ~/voice.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo loginctl enable-linger admin && sudo systemctl enable --now hailo-live voice && sudo systemctl restart pi-web && systemctl --no-pager status hailo-ollama pi-web hailo-live voice | grep -E "service|Active"'   # (sudo)
```

| service | what | where |
|---|---|---|
| `hailo-ollama` | LLM server on the HAT | port 8000 |
| `pi-web` | the page: chat, speak, hold-to-talk, transcript, camera, sources | **http://ml-ai.local/** |
| `hailo-live` | YOLO11m on the camera, 15 fps, sharing the HAT with the LLM (HailoRT Python API, `live_yolo.py`); the page's camera panel shows its frames | raw viewer on port 8001 |
| `voice` | microphone assistant, wake phrase "hey pi", answers through the PipeWire default sink; its questions and answers appear in the page's transcript | — |

Idle cost, measured Oct 19, 2026 right after enabling: `voice` keeps Vosk transcribing everything the mic hears, about 30% of one core, and `hailo-live` about 10%; the HAT does the detection. Speech that does not start with the wake phrase shows in `journalctl -u voice` as `HEARD:` lines but is not written to the page's transcript and cannot stop the assistant.

**HAT sharing (solved with 5.3.0, Oct 19, 2026).** `hailo-ollama.service` sets `HAILO_OLLAMA_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED`; `hailo-live/live_yolo.py` opens its VDevice with the same `group_id` through the HailoRT Python API, so the camera runs at 15 fps while the LLM is loaded and about 5.6 fps while it is generating (the chip is time-sliced), with no effect on the LLM. Two things did not work: the GStreamer `hailonet` element (HailoRT's own plugin, not TAPPAS) still fails with error 74 even with `vdevice-group-id=HAILO_OLLAMA_SHARED`, so `run_live.sh` no longer uses GStreamer (`compare.sh` still does and needs the LLM idle); and releasing a shared VDevice while its model is still configured corrupts the device for every process (kernel: "Trying to enable channels ... already enabled", hailo-ollama 500s until restarted), so `live_yolo.py` closes the model first. The 5.2.0 story, for the record: found after enabling `hailo-live` at boot, `hailo-ollama` releases the device after about five idle minutes ("generation_context: timeout expired") and then cannot get it back while `hailonet` holds it, so every chat returned a 500 ("Failed to create vdevice, there are not enough free devices") and `hailo-ollama` eventually segfaulted (systemd restarted it). The reverse is the same: `hailonet` with `vdevice-group-id=SHARED` or `HAILO_OLLAMA_SHARED` fails with error 74 while the LLM holds the device. The earlier "YOLO works while hailo-ollama runs" result only held because the LLM was idle and had released the device. On 5.2.0 the only option was to keep `hailo-live` disabled and start it by hand when the LLM was not needed.

`hailo-live` holds the camera: `sudo systemctl stop hailo-live` before `rpicam-still` or `vlm_test.py --camera`, and the VLM additionally needs `sudo systemctl stop hailo-ollama`. `voice` and the page both talk to the same hailo-ollama, which handles one request at a time, so a spoken question and a typed one queue behind each other. Logs: `journalctl -u voice -f` (same for the others). To change the wake phrase or the output device, edit `pi-config/voice.service`, `./deploy.sh`, then `sudo cp ~/voice.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart voice`.

### Live object detection (YOLO11m on the camera)

Since Oct 19, 2026 the live loop is `hailo-live/live_yolo.py` (HailoRT Python API, shares the HAT with the LLM); `run_live.sh` starts it plus the viewer's http server on 8001, `stop_live.sh` stops both. `live_yolo.py --image in.jpg --out out.jpg` runs one image and prints the detections. The GStreamer description below is how it worked up to 5.2.0 and is still what `compare.sh` uses.

```
cd ~/hailo-live && ./run_live.sh          # Ctrl-C to stop; from another shell: ~/hailo-live/stop_live.sh
```

Open `http://ml-ai.local:8001/viewer.html` from any machine on the network. `capture_letterbox.py` pads each 640×480 camera frame to 640×640 (no stretching) and pipes it into `hailonet`; annotated frames are written to `live/latest.jpg` about 20 times a second. (The viewer is on 8001 because `hailo-ollama` owns 8000.)

### One-off tests

```
~/hailo_test/classify.sh image.jpg out.jpg                              # ResNet-50 label + score drawn on the image
~/yolo_test/compare.sh                                                  # YOLOv8m vs YOLO11m on ~/yolo_test/scenes/*.jpg -> out/<model>/
hailortcli run2 --measure-overall-latency set-net /usr/share/hailo-models/resnet_v1_50_h10.hef   # latency benchmark
```

### Answering from documents (RAG)

The 1.5B models invent facts, so the assistant and the web page answer from the documents in `~/rag/docs/` when an index exists. The LLM stays on the HAT; the only CPU work is a 65 MB sentence-embedding model (`BAAI/bge-small-en-v1.5` through `fastembed`/onnxruntime, in `~/voice/.venv`): about 15 ms per question once loaded, and about 70 s to index the current 253 chunks. No sudo.

```
~/voice/.venv/bin/pip install fastembed                      # once; pulls onnxruntime, ~65 MB model is downloaded on first use into ~/rag/models/
cp your.pdf your-notes.md ~/rag/docs/                        # PDF, .txt, .md
~/voice/.venv/bin/python ~/rag/rag.py build                  # rebuild after adding or removing documents
~/voice/.venv/bin/python ~/rag/rag.py search "how do I load filament"   # retrieval only: scores, document, page
~/voice/.venv/bin/python ~/rag/rag.py ask "how do I load filament"      # retrieval + answer from the HAT, with sources
```

How it works: `pdftotext` splits each PDF into pages; pages are cut into ~180-word chunks (40-word overlap) that remember their file and page; chunks are embedded and stored as a numpy array in `~/rag/index/`. For a question, the top 3 chunks with cosine score ≥ 0.60 go into the user turn ("Document excerpts: ... Question: ...") capped at ~420 words, because hailo-ollama models have a 2048-token context. Below 0.60 nothing is added and the model answers on its own. The conversation history keeps only the plain question, not the excerpts. `assistant.py` prints the sources after each answer (not spoken); the web page shows them under the answer; `--no-rag` or `{"no_rag": true}` turns retrieval off.

Image-only PDFs: pages with no text layer are OCR'd with `tesseract` when it is installed (`sudo apt install tesseract-ocr`, **sudo**); otherwise they are skipped with a warning. Of the first test set (Oct 19, 2026: Bambu Lab H2D manuals and the xTool O1 Omni quick start), the H2D 3D Printing User Manual (163 pages) and the xTool guide have text; the three H2D quick-start guides are pictures and need OCR.

Measured Oct 19, 2026: manual questions score 0.69–0.80 against the right pages, an off-topic question ("president of France") scores 0.41 and gets no excerpts; removing a document and rebuilding removes its pages from every search. Answer quality is limited by the 1.5B model, see the RAG notes in "Gotchas".

### Vision-language model on the HAT (Qwen2-VL-2B)

`hailo-ollama` serves text LLMs only (Hailo's USAGE.rst says so, and the VLM is absent from `/hailo/v1/list`). The VLM runs through the HailoRT Python GenAI API instead, which works on 5.2.0. One-time setup, no sudo:

```
cd ~/hailo520 && wget https://dev-public.hailo.ai/2026_01/Hailo10/hailort-5.2.0-cp313-cp313-linux_aarch64.whl   # Python 3.13 wheel; not linked from Hailo's site
~/voice/.venv/bin/pip install ~/hailo520/hailort-5.2.0-cp313-cp313-linux_aarch64.whl opencv-python-headless
wget https://dev-public.hailo.ai/v5.2.0/blob/Qwen2-VL-2B-Instruct.hef          # 3.1 GB; other 5.2.0 HEFs live at the same path
```

The HAT is exclusive on 5.2.0: `hailo-ollama` holds it while running, and anything else gets `HAILO_OUT_OF_PHYSICAL_DEVICES` (error 74). Stop it, run the test, start it again:

```
ssh -t admin@ml-ai.local 'sudo systemctl stop hailo-ollama'                           # (sudo)
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --image ~/hailo_test/cam640.jpg --prompt "Describe this image in two sentences."
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --camera                            # grabs a frame with rpicam-still first
ssh -t admin@ml-ai.local 'sudo systemctl start hailo-ollama'                          # (sudo)
```

Measured Oct 19, 2026: model load 7.8 s warm, 33 s cold after a reboot; 12.5 s for a 67-word answer (~7 tok/s including the image prefill). The description of `cam640.jpg` (a cardboard box corner with a glare spot over a wooden floor) was accurate, and so was a live `--camera` frame (wooden floor, colorful red/yellow/blue printed object). The model does not respect sentence limits in the prompt; use `--max-tokens` (default 150) to bound the answer. The HEF wants 336×336 RGB; the script resizes. Sharing the device between `hailo-ollama` and other apps (`HAILO_OLLAMA_VDEVICE_GROUP_ID`) only arrives with model zoo 5.3.0, which needs HailoRT 5.3.0 and has a [reported broken Pi dependency](https://community.hailo.ai/t/bug-report-hailo-gen-ai-model-zoo-5-3-0-uninstallable-on-raspberry-pi-with-hailo-10h/19226).

## Test checklist

Run these after any upgrade, kernel change or reboot. All from `admin@ml-ai.local`; the two marked **(sudo)** need a password.

```
grep CmaTotal /proc/meminfo                                   # 65536 kB. If not, check cmdline.txt for cma= (6b)
vcgencmd version                                              # a date, not "ioctl_set_msg failed"
hailortcli fw-control identify | grep -i "firmware version"   # 5.2.0
rpicam-hello --list-cameras                                   # imx708 listed
curl -s localhost:8000/api/tags | python3 -m json.tool | grep '"name"'     # hailo-ollama: the pulled models
~/voice/.venv/bin/python ~/voice/llm_bench.py hailo=http://127.0.0.1:8000,llama3.2:1b   # ~8.4 tok/s; copy results aside first
~/yolo_test/compare.sh                                        # 8 "done" lines, boxes in ~/yolo_test/out/*/
cd ~/hailo-live && ./run_live.sh                              # open http://ml-ai.local:8001/viewer.html, then ~/hailo-live/stop_live.sh
~/voice/.venv/bin/python ~/voice/assistant.py --text          # typed question, spoken/printed answer
curl -s localhost/api/status                                  # web UI: "backends": ["hailo"], "camera": true while run_live.sh runs
```

Vision-language model (the HAT must be free):

```
ssh -t admin@ml-ai.local 'sudo systemctl stop hailo-ollama'                                   # (sudo)
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --image ~/hailo_test/cam640.jpg              # box/floor description, ~7 tok/s
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --camera --prompt "What objects do you see?"  # live frame
ssh -t admin@ml-ai.local 'sudo systemctl start hailo-ollama'                                  # (sudo)
```

Expected numbers are in "Measured so far".

## CPU vs Hailo for the LLM

Prompted by [this article](https://the-diy-life.com/i-ran-ai-on-a-raspberry-pi-the-results-were-unexpected/) (Pi 5 CPU ~11 tok/s, Hailo slower), measured here on Oct 13, 2026 with `voice/llm_bench.py`: the same Qwen2.5 1.5B model as a GGUF on the Pi's CPU (stock Ollama 0.40.3, `qwen2.5:1.5b`, 986 MB) and as Hailo's HEF on the AI HAT+ 2 (`hailo-ollama`, `qwen2.5-instruct:1.5b`, 2.25 GB). Temperature 0, seed 42, "hello" warm-up, the article's three prompts, 3 runs each, CPU sampled during generation. The table below is that run on HailoRT 5.1.1. Reruns on 5.2.0 are in the next section.

| backend | prompt | tok/s | wall | CPU during generation |
|---|---|---|---|---|
| Pi 5 CPU | DNS (≈385 tok) | **11.5** | 34 s | **100% of 4 cores** |
| Pi 5 CPU | physics (853 tok) | 11.1 | 77 s | 100% |
| Pi 5 CPU | intro (38 tok) | 11.8 | 3.5 s | 100% |
| AI HAT+ 2 | DNS (≈255 tok) | 6.8 | 38 s | **0–3%** |
| AI HAT+ 2 | physics (≈660 tok) | 5.5* | 123 s | 2% |
| AI HAT+ 2 | intro (≈209 tok) | 6.8 | 31 s | 0% |

CPU tokens/s come from Ollama's `eval_duration`; `hailo-ollama` does not report timing, so its figures are wall-clock with token counts estimated from word count. \*Two of the three Hailo physics runs dropped to 4.6–5.1 tok/s; the first was 6.9. Something else may have used the Hailo at the same time.

**Rerun on HailoRT 5.2.0 (Oct 13 and 19, 2026):** the zoo now has `qwen2.5:1.5b` (not `qwen2.5-instruct:1.5b`), so both backends use that name. CPU (stock Ollama, same GGUF): DNS 11.8–11.9, physics 10.7–11.4, intro 12.0–12.1 tok/s. Hailo, wall-clock, mean of 3 runs each, Pi otherwise idle:

| Hailo model | DNS | physics | intro | Hailo's own figure |
|---|---|---|---|---|
| `qwen2.5:1.5b` (256 MB CMA, Oct 13) | 6.8 | 6.8 | 6.8 | 7.4 |
| `llama3.2:1b` (Oct 19) | 8.4 | 8.5 | 8.4 | 9.9 |

So 5.2.0 matches 5.1.1 for Qwen, the CMA size makes no difference, and Llama 3.2 1B is ~25% faster because it is smaller. Hailo's published tokens/s for every zoo model are in [MODELS.rst](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst); the run-to-run spread here was under 0.1 tok/s. Llama's answers are no better: its physics answer uses t = 2v/g and gets 11 s, and its blog intro claims a Pi 5 is "1000 times faster than a traditional computer". Results are on the Pi as `~/voice/llm_bench_results_llama32_1b.json` and `*_qwen25_cma256.json` with the matching `answers.md` files; `llm_bench.py` overwrites `llm_bench_results.json`, so copy results aside before another run.

**Why the CPU is faster:** generating a token means streaming every weight of the model through the processor once, so tokens/s ≈ memory bandwidth ÷ bytes per token. Both sides have LPDDR4X-4267 (the HAT's own 8 GB is the same speed grade as the Pi 5's RAM; Hailo does not publish the bus width, so the HAT's bandwidth could equal the Pi's ~17 GB/s or exceed it). What is different is the model file: the Hailo HEF is 2.25 GB against 0.99 GB for the CPU GGUF of the same 1.5B model. At 6.8 tok/s × 2.25 GB the HAT is moving ~15 GB/s, the same class as the Pi's 11.5 tok/s × 0.99 GB ≈ 11 GB/s. So the measurements say the HAT is not short of bandwidth; it is spending ~2.3× the bytes per token on this first-generation LLM build (less compact quantization and packing), plus a young runtime (`hailo-ollama` 5.1.x vs years-old llama.cpp ARM tuning). That gap can shrink with software; the 40 TOPS can't help with it, because batch-1 decode reuses no weights. Vision is the opposite case (small weights reused across a whole image, compute-bound), which is why the HAT runs YOLO at 20 fps and the CPU at ~1.

**Answer quality (first run of each, in `voice/llm_bench_answers.md`):** both are weak and both invent things. Physics (correct: 1.43 s, 10.0 m, 2.86 s): CPU got the times right and the height wrong (arithmetic slip, 9.13 m); Hailo got the time and height right and the total wrong (3.47 s, wrong formula). DNS: CPU better structured, Hailo closer to the word limit but less accurate. Intro: CPU produced only a one-line title; Hailo wrote a real intro but invented products ("Raspberry Pi 3000").

**What this means:**
- The AI HAT+ 2 is bought for **vision**. For a 1.5B LLM it is ~40% slower per token than the CPU, and no accelerator in this class will beat the Pi's own memory bandwidth by much.
- The HAT's LLM advantage is that it leaves the CPU **free** (0–3% vs 100%) for Vosk, Piper, the web page and the camera. Whether that makes the voice assistant feel better is still untested: run the LLM on each backend while Vosk transcribes and Piper speaks, and compare.
- A voice-only topic assistant does not need the HAT. Snapshot-style "what do you see" doesn't either (CPU YOLO ~1 s per frame). Continuous live vision, or vision at the same time as voice, does (HAT, or the cheaper AI Camera/IMX500 with smaller models and no LLM).
- Decision (Oct 19, 2026): **nothing runs on the Pi's CPU.** The stock Ollama install, its models and the staged `ollama.service` were deleted (3.1 GB freed). The measurements above stay as the record of why. To repeat the comparison, reinstall it as below and add the `cpu` entry back to `BACKENDS` in `web/app.py`.

**Stock Ollama on the Pi, if the comparison is ever re-run (user-local, no sudo; removed Oct 19, 2026):**

```
mkdir -p ~/ollama/models && cd ~/ollama
wget https://github.com/ollama/ollama/releases/download/v0.40.3/ollama-linux-arm64.tar.zst   # 1.5 GB
tar --zstd -xf ollama-linux-arm64.tar.zst && rm ollama-linux-arm64.tar.zst                    # 2.1 GB unpacked
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=~/ollama/models OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 ~/ollama/bin/ollama serve
OLLAMA_HOST=127.0.0.1:11434 ~/ollama/bin/ollama pull qwen2.5:1.5b                             # 986 MB
```

It listens on loopback only and stops at reboot (no service is kept for it). Re-run the comparison with `~/voice/.venv/bin/python ~/voice/llm_bench.py cpu=http://127.0.0.1:11434,qwen2.5:1.5b hailo=http://127.0.0.1:8000,qwen2.5:1.5b`, then `rm -rf ~/ollama`.

## Speech recognition accuracy

Free-form recognition is the weak link: the original `listen.py` only had to pick one of five phrases, while `assistant.py` must transcribe anything. Measured on Oct 13, 2026 with `voice/stt_bench.py` on a test set of 10 questions × 6 macOS voices (60 WAVs, 390 words; synthetic voices, so real students will differ):

| Model | Disk | Load | WER | Exact | Speed on Pi 5 |
|---|---|---|---|---|---|
| `vosk-model-small-en-us-0.15` (default) | 68 MB | 1 s | 11.3% | 39/60 | 2.4× real time |
| `vosk-model-en-us-0.22-lgraph` | 205 MB | 1 s | 17.9% | 31/60 | 0.4× (too slow for live use) |
| `vosk-model-en-us-0.22` | 2.7 GB | 10–40 s | 10.0% | 43/60 | 2.0× real time |
| **small + `stt_fix.py`** | 68 MB | 1 s | **6.9%** | **45/60** | 2.4× real time |
| big + `stt_fix.py` | 2.7 GB | 10–40 s | 6.9% | 47/60 | 2.0× real time |

What the errors were: almost all on this project's own words, which general English models don't know: "pi"→"pie", "AI HAT"→"i had / all you had", "three"→"free", "sensors"→"senses". So the fix with the best return is **`voice/stt_fix.py`**: a short list of regex corrections for exactly the mistakes seen in testing, applied to every transcript (`--no-fix` disables it). Students can add their topic's words there. The system prompt also tells the LLM the text came from speech recognition, and `--confirm` reads back what was heard.

The big model is installed at `~/voice/models/vosk-model-en-us-0.22` (`--stt-model big`) but gives no accuracy gain once the corrections are on, and in one run its 2.7 GB load pushed the LLM's first response from 0.5 s to 32 s. Delete it with `rm -r ~/voice/models/vosk-model-en-us-0.22` to free the space if you don't need it. The lgraph model is at `~/voice/models/vosk-model-en-us-0.22-lgraph` and can be deleted too.

Re-run the measurement after changing models or `stt_fix.py` (the test set lives in `~/voice/sttset/`; regenerate it on the Mac with `say -v <voice> -o f.aiff "<text>" && afconvert -f WAVE -d LEI16@16000 -c 1 f.aiff f.wav`, one `file.wav|transcript` line per file in `manifest.txt`):

```
~/voice/.venv/bin/python ~/voice/stt_bench.py --fix ~/voice/sttset/manifest.txt ~/voice/model ~/voice/models/vosk-model-en-us-0.22
```

**Before a demo, test with real voices in the real room**: run `assistant.py --confirm --no-tts`, have a few students ask questions, and add any repeated mis-hearings to `stt_fix.py`. Whisper (used by the Moonlighter guide) is the alternative if Vosk stays too inaccurate; it is more accurate but not streaming, so it would change the interaction.

## Testing without a mic or speaker

- Typed chat on the Pi: `~/voice/.venv/bin/python ~/voice/assistant.py --text --no-tts`
- One request from the Mac:
  ```
  curl -s http://ml-ai.local:8000/api/chat -H 'Content-Type: application/json' \
    -d '{"model":"qwen2.5:1.5b","stream":false,"messages":[{"role":"user","content":"What is a Raspberry Pi?"}]}'
  ```
- Spoken question from a file: make one on the Mac with `say -o q.aiff "what is a raspberry pi" && afconvert -f WAVE -d LEI16@16000 -c 1 q.aiff q.wav`, copy it over, run `assistant.py --wav q.wav`.
- Service health: `systemctl is-active hailo-ollama`, `journalctl -u hailo-ollama -n 50`.

## Gotchas

- **`hailortcli run` refuses the Hailo-10H.** Use `run2`.
- **The Python `hailo_platform` API cannot load any `*_h10.hef` on HailoRT 5.1.1** (not re-tested on 5.2.0). `VDevice.configure()` returns `HAILO_NOT_IMPLEMENTED` (error 7) for all of them. Vision models must go through the GStreamer/TAPPAS plugins (`hailonet`, `hailofilter`, `hailooverlay`), which is what every script here does. `hailo_platform.genai` (LLM/VLM/Speech2Text) does work on 5.2.0 with the wheel from "Vision-language model on the HAT".
- **HAT sharing needs the group id.** With 5.3.0 and `HAILO_OLLAMA_VDEVICE_GROUP_ID` set, any HailoRT app that uses `group_id = "HAILO_OLLAMA_SHARED"` (Python `VDevice.create_params()`) shares the HAT with the LLM. Anything else (`hailortcli run2`, `hailonet`, a VDevice with another group) gets `HAILO_OUT_OF_PHYSICAL_DEVICES` (74) while a model is loaded, and if it grabs the device first `hailo-ollama` returns 500s. Only one LLM/VLM can be loaded at a time, so `vlm_test.py` still needs `hailo-ollama` idle or stopped.
- **hailo-ollama 5.3.0 rejects newlines.** Any message containing `\n` or `\t` returns 500 "Failed to render prompt from JSON strings" (quotes, backslashes, unicode are fine). `assistant.py` flattens whitespace in every message right before sending (`hailo_safe`), which the web app and `rag.py` reuse. This is the "escape character" bug Hailo acknowledged in May 2026.
- **Never release a shared VDevice while a model is configured on it** (see "Everything at boot"); it takes the HAT down for every process until `hailo-ollama` is restarted.
- **Never put `cma=` on the kernel command line.** It breaks the firmware mailbox and with it the camera (see 6b).
- **YOLO11 needs the generic TAPPAS filter.** `hailofilter` with `function-name=yolov8m` hardcodes the `yolov8m/` tensor name; leave `function-name` unset for `yolov11m_h10.hef` and the filter finds the NMS tensor by pattern.
- **A GStreamer pipeline holds back its last frame.** Feeding one image produces no output; loop it (`multifilesrc loop=true num-buffers=10`) and keep the last file.
- **`rpicam-vid --post-process-file` recordings have no boxes** (overlay is drawn on the low-res stream, which isn't recorded) and `rpicam-still` with it prints "HailoRT not ready!". Use the TAPPAS pipelines instead.
- **HDMI audio only exists while a display is connected.** With both HDMI ports disconnected, PipeWire's default sink is "Dummy Output" (silent but succeeds) and `aplay` to HDMI fails with error 524. `assistant.py` prints a one-line `[TTS off …]` notice and carries on in text mode.
- **The USB mic is opened by card name** (`plughw:CARD=Device,DEV=0`, overridable with `ASSISTANT_MIC`) since Oct 19, 2026, so `~/.asoundrc` (`usbmic`) is only a convenience for typing `arecord -D usbmic`; `raspi-config` and the desktop volume applet rewrite that file, which is why it "went missing" before. After one reboot the mic refused to open ("audio open error: No such file or directory") for seven minutes although the card was enumerated two seconds after boot, so `voice.service` now waits for a successful one-second test capture before starting (`ExecStartPre`) instead of restarting every 5 s (36 restarts that morning).
- **The 1.5B model invents facts** (it produced a fictional Raspberry Pi "founder"). Ask it things you can verify, and use RAG with real documents for the topic assistant.
- **Only Hailo zoo models run on the Hailo.** No arbitrary GGUF, no compiling your own LLM to HEF. Embeddings and RAG stay on the CPU.
- **RAG and the 1.5B model.** Retrieval finds the right pages (see "Answering from documents"), but `qwen2.5:1.5b` still merges neighbouring sentences: asked "what is the AMS?" it answered with the definition of the HMS from the same excerpt, three prompt layouts in a row. Keep questions specific ("how do I load filament into the AMS"), keep answers capped (`LLM_OPTIONS` in `assistant.py`: `num_predict` 120, honoured by hailo-ollama; without it the model ran on for minutes inventing filament acronyms), and check the sources line. Putting the instruction after the excerpts made it worse (it echoed the instruction).

## Measured so far

- HailoRT and firmware 5.3.0 on this Pi (5.1.1 → 5.2.0 on Oct 13, 2026 → 5.3.0 on Oct 19). Verified after each upgrade: device node present (`/dev/hailo0` up to 5.2.0, `/dev/h1x-0` from 5.3.0), PCIe link Gen 3 x1.
- ResNet-50: ~4.1 ms per frame (5.1.1).
- Live YOLO11m: ~20 annotated frames/s on 5.1.1 (GStreamer); 15.0 fps on 5.2.0 and 5.3.0 (the loop's cap). On 5.3.0 through the Python API (`live_yolo.py`, 27–35 ms per inference): 15 fps while the LLM is loaded, 5.6 fps while it generates, measured as `latest.jpg` mtime changes over 10 s.
- The Python `hailo_platform` vision API works on 5.3.0: `create_infer_model` + `configure` on `yolov11m_h10.hef` (NMS on chip, output is a list of 80 per-class `(n, 5)` arrays: y1, x1, y2, x2, score). It failed with error 7 on 5.1.1.
- YOLO on a camera still: cup on a table at ~1 ft → "cup 69%" (YOLOv8m); a cup held at the lens was not detected; YOLO11m missed that cup but matched YOLOv8m on people. Four scenes are too few to pick a winner; both models are installed.
- LLM on 5.1.1: `qwen2.5-instruct:1.5b` ~6.5–7 tokens/s, `qwen2.5-coder:1.5b` ~7.5 tokens/s; first request after a model switch adds ~10 s. On 5.2.0: `qwen2.5:1.5b` 6.8 tok/s, `llama3.2:1b` 8.4 tok/s (wall-clock, 3 runs each; see "Rerun on HailoRT 5.2.0"). CMA 64 MB vs 256 MB: no difference.
- Qwen2-VL-2B on the Hailo through the Python GenAI API (5.2.0): ~7–7.5 tok/s including the image prefill; accurate descriptions of both a saved photo and a live camera frame (Oct 19, 2026). Model load is 33 s cold (3.1 GB HEF read from the SD card after a reboot) and 7.8 s once the file is in the page cache. It ignores "answer in one sentence" and runs to `--max-tokens` (default 150), so set that for short answers.
- Piper: a 3.1 s sentence took 4.7 s to synthesize including the one-time voice load (the split was not measured); in the assistant, sentences play with no noticeable gap.
- Voice assistant end to end (WAV in, speech to the dummy sink): first spoken word ~0.5 s after the question, whole 3-sentence answer ~18 s including playback.

## Not yet done

- Audible output has not been heard: no display on HDMI and no USB speaker yet. Plug a monitor/TV into HDMI0 and run `assistant.py`; `wpctl status` should show the HDMI sink.
- Live human voice on the mic has not been tested (all tests used WAV files or typed input).
- **Bootloader EEPROM update** is available (May 2026 installed, Sep 2026 available): `sudo rpi-eeprom-update -a`. Optional.
- **Reader tips not yet tested:** a systemd `ExecStartPre` delay for hailo-ollama and `HAILO_LOG_LEVEL=info`.

## To do

- **RAG, next steps.** The pipeline is in (see "Answering from documents"). Still to do: install `tesseract-ocr` (sudo) so the three image-only H2D quick-start guides get indexed; add the real Moonlighter lesson documents; decide whether off-topic questions should be refused ("not in my documents") instead of answered from the model's memory.

## Sources

- [Raspberry Pi AI software docs](https://www.raspberrypi.com/documentation/computers/ai.html) — Hailo driver and LLM install steps
- [Waveshare AI HAT+ 2 wiki](https://www.waveshare.com/wiki/Raspberry_Pi_AI_HAT%2B_2)
- [pi-private-ai-server](https://github.com/btstevens1984az/pi-private-ai-server) — reference for `hailo-ollama`, the systemd unit and the RAG approach
- [Pi AI Guide (Moonlighter FabLab)](https://aimoonlighter.howto.rocks) — the program this is built for, repo at github.com/EmilMoonlighter/AI-Program
- [Vosk models](https://alphacephei.com/vosk/models), [Piper voices](https://github.com/rhasspy/piper)
