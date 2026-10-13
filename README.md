# Raspberry Pi 5 + AI HAT+ 2 voice assistant (ML-AI)

A Raspberry Pi 5 with an AI HAT+ 2 (Hailo-10H) that listens on a USB mic, answers with a local LLM running on the Hailo, speaks the answer with Piper, and can run YOLO object detection on the Pi camera. Everything runs offline on the Pi. This is the base for the Moonlighter FabLab high-school AI program.

- Pi: `admin@192.168.4.28`, hostname `ML-AI`, Raspberry Pi OS (Debian 13 trixie, 64-bit), kernel 6.18, Python 3.13, 8 GB RAM, 32 GB SD.
- Passwordless sudo is **not** set up. Steps marked **(sudo)** below must be run in an interactive terminal; from the Mac, `ssh -t admin@192.168.4.28 'sudo ...'` prompts for the password.

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
| `web/app.py`, `web/index.html` | `~/web/` | Web front end on port 8002: chat, speak, hold-to-talk, live transcript, camera |
| `pi-config/pi-web.service` | `/etc/systemd/system/` **(sudo)** | Runs the web front end at boot |
| `pi-config/ollama.service` | `/etc/systemd/system/` **(sudo)** | Runs stock Ollama (CPU LLM, port 11434) at boot; optional |
| `voice/llm_bench.py` | `~/voice/` | CPU-vs-Hailo LLM benchmark (speed, CPU load, saved answers) |
| `deploy.sh` | — | Copies all of the above to the Pi (everything except the sudo step) |

## Hardware

- Raspberry Pi 5 (8 GB) with active cooler and 27 W PSU
- Raspberry Pi AI HAT+ 2 (Hailo-10H, 8 GB on-board RAM) on the PCIe connector. No `dtparam=pciex1` line and no stacking board were needed; it was detected as soon as it was seated properly. The link already runs at **PCIe Gen 3 (8.0 GT/s) x1** with no `pciex1_gen=3` line (Raspberry Pi OS negotiates Gen 3 for HAT+ boards automatically; check with `cat /sys/bus/pci/devices/0001:01:00.0/current_link_speed`). The Hailo-10H supports x4 but the Pi 5 has one lane, so there is nothing to gain from PCIe settings.
- Raspberry Pi Camera Module 3 (IMX708) on the CSI connector
- USB microphone: TI PCM2902 codec ("USB PnP Sound Device"), capture only
- Audio out: HDMI for now (needs a display with audio plugged into HDMI0). A USB speaker can be added later with no code change.

## Fresh install, in order

### 1. OS, SSH, updates

Flash Raspberry Pi OS 64-bit (trixie) with the Imager, set user `admin`, enable SSH and Wi-Fi. Then:

```
ssh-copy-id admin@192.168.4.28                      # from the Mac, key login
ssh -t admin@192.168.4.28 'sudo apt update && sudo apt full-upgrade -y && sudo reboot'   # (sudo)
```

### 2. Hailo driver for the AI HAT+ 2 (sudo)

`hailo-h10-all` is for the AI HAT+ 2. Do not install `hailo-all` (that is for the older AI Kit / AI HAT+); they conflict.

```
ssh -t admin@192.168.4.28 'sudo apt install -y dkms hailo-h10-all && sudo reboot'
```

Verify after the reboot:

```
lspci | grep -i hailo                 # Hailo-10H at 0001:01:00.0
ls -l /dev/hailo0
hailortcli fw-control identify        # Firmware 5.2.0, Device Architecture: HAILO10H
```

A fresh install from the Raspberry Pi repo (checked Oct 12, 2026) gives HailoRT 5.1.1. It pulls in `h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`, `hailo-tappas-core` 5.1.0, `hailo-models` 1.0.0 (the `.hef` files in `/usr/share/hailo-models/`), and `rpicam-apps-hailo-postprocess`. Step 2b upgrades it to 5.2.0, which is what this Pi runs now.

### 2b. Upgrade to HailoRT 5.2.0 (sudo, optional)

Download the three packages from Hailo's server (the same server as the 5.1.1 zoo `.deb`, see step 6) into `~/hailo520/` on the Pi: `hailort_5.2.0_arm64.deb`, `hailort-pcie-driver_5.2.0_all.deb`, `hailo_gen_ai_model_zoo_5.2.0_arm64.deb`. Install all three together, or the driver and runtime versions will not match (`HAILO_INVALID_DRIVER_VERSION`):

```
ssh -t admin@192.168.4.28 'sudo dpkg -i ~/hailo520/hailort_5.2.0_arm64.deb ~/hailo520/hailort-pcie-driver_5.2.0_all.deb ~/hailo520/hailo_gen_ai_model_zoo_5.2.0_arm64.deb && sudo reboot'   # (sudo)
```

Before upgrading, save the package list so you can roll back: `dpkg -l 'h10*' 'hailo*' > ~/hailo-rollback-5.1.1.txt`. The zoo install replaces `/usr/share/hailo-ollama`, so the models must be pulled again afterwards (step 6). Verify `hailortcli fw-control identify` shows firmware 5.2.0.

### 3. Camera

Nothing to install. Check and take a still:

```
rpicam-hello --list-cameras           # should list imx708
rpicam-still -n -t 2000 --width 640 --height 640 -o test.jpg
```

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
ssh -t admin@192.168.4.28 'sudo dpkg -i ~/hailo_gen_ai_model_zoo_5.2.0_arm64.deb'                   # (sudo)
```

If you are on 5.1.1, use `hailo_gen_ai_model_zoo_5.1.1_arm64.deb` (7.9 MB) instead. If you did step 2b, the zoo package is already installed, so skip this step.

Install the service (unit file comes from `pi-config/hailo-ollama.service` via `deploy.sh`; it runs as `admin`, restarts on failure, working directory `/home/admin`):

```
ssh -t admin@192.168.4.28 'sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hailo-ollama'   # (sudo)
```

Pull the models (about 1.5–2 MB/s here, so 15–20 minutes each). Pull them again after any zoo package install, because that replaces the model store:

```
curl -s http://127.0.0.1:8000/hailo/v1/list        # zoo (5.2.0): qwen2.5:1.5b, qwen2.5-coder:1.5b, qwen2:1.5b, llama3.2:1b, deepseek_r1:1.5b
for m in qwen2.5:1.5b qwen2.5-coder:1.5b; do
  curl -s http://127.0.0.1:8000/api/pull -H 'Content-Type: application/json' -d "{\"model\": \"$m\", \"stream\": true}" | tail -c 200; echo
done
curl -s http://127.0.0.1:8000/api/tags             # shows what is pulled
```

Models land in `/usr/share/hailo-ollama/models/blob/` (both models together about 3.8 GB on 5.2.0). Config is `/etc/xdg/hailo-ollama/hailo-ollama.json`; it binds `0.0.0.0:8000`, so the API is reachable from the LAN. Change `host` to `127.0.0.1` to keep it Pi-only.

### 6b. Larger CMA memory pool (sudo, optional)

Hailo's driver uses a contiguous memory pool (CMA). The default is 64 MB. On this Pi it was raised to 256 MB by adding `cma=256M` to the kernel command line, which takes effect after a reboot. Nothing failed at 64 MB; this was an experiment to see whether it helps the LLM speed (result in "CPU vs Hailo" below).

```
ssh -t admin@192.168.4.28 'sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak && sudo sed -i "s/$/ cma=256M/" /boot/firmware/cmdline.txt && sudo reboot'   # (sudo)
```

Check after the reboot: `grep CmaTotal /proc/meminfo` should show `262144 kB`. To undo, copy the `.bak` file back and reboot.

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

**http://192.168.4.28:8002/** from any device on the network. It runs as the systemd service `pi-web` (installed and verified on Oct 13, 2026; starts at boot after `hailo-ollama`). Manage with `sudo systemctl {status,restart,stop} pi-web`; logs via `journalctl -u pi-web -n 50`. To install it on a fresh Pi (**sudo**):

```
ssh -t admin@192.168.4.28 'sudo cp ~/pi-web.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now pi-web'
```

If you ever start it by hand instead (`~/voice/.venv/bin/python ~/web/app.py`), stop that copy before enabling the service: two instances cannot share port 8002, and the service will crash-loop with "Address already in use" until the hand-started one is gone (`pkill -f "^/home/admin/voice/.venv/bin/python app.py"`). After editing `web/app.py` or `index.html`, just run `./deploy.sh`: it copies the files and kills the running app, and the unit's `Restart=always` starts it again with the new code, no sudo needed. (With the earlier `Restart=on-failure` a clean kill left the service stopped; that is why it was changed.)

The model picker lists every model from both LLM servers, tagged "AI HAT+ 2" (hailo-ollama, port 8000) or "Pi CPU" (stock Ollama, port 11434, see "CPU vs Hailo" below); chat is routed to whichever server owns the chosen model.

What the page does (all against the same pieces the voice assistant uses):

- **Chat**: type a question, the reply streams in from `hailo-ollama` with the same short-answer prompt and 4-turn history as `assistant.py`. A model picker lists what's pulled. "New conversation" clears the history.
- **Speak replies on the Pi**: when checked, each sentence is spoken through the Pi's audio output (Piper, PipeWire default sink) in order while the text keeps streaming. Set `ASSISTANT_OUT=hdmi|usb|<alsa device>` in the service file to force an output.
- **Hold to talk**: records on the laptop/phone, sends the audio to the Pi, transcribes it with Vosk (small model) plus `stt_fix.py`, and asks the question. **Browsers only allow mic access on HTTPS or `localhost`**, so over plain `http://192.168.4.28:8002` the button will report "mic not available" in Chrome/Safari. Workarounds: open `chrome://flags/#unsafely-treat-insecure-origin-as-secure` and add `http://192.168.4.28:8002`; or run the page over HTTPS with a self-signed certificate (not set up yet). Typing and the Pi's own USB mic are unaffected.
- **Voice assistant transcript**: live `HEARD:` / `ANSWER:` lines from `assistant.py` (it appends each to `~/voice/transcript.jsonl`; the page follows that file). Lets a room see what the mic understood.
- **Camera**: shows the latest YOLO frame while `~/hailo-live/run_live.sh` is running (it checks the frame is under 5 s old).

Endpoints, for students who want to build on it: `POST /api/chat` (NDJSON stream), `POST /api/transcribe` (audio body → `{text, raw}`), `POST /api/speak`, `POST /api/reset`, `GET /api/transcript` (server-sent events), `GET /api/camera`, `GET /api/status`. Needs `flask` in the voice venv (`~/voice/.venv/bin/pip install flask`) and `ffmpeg` (already on the Pi). Ports in use on the Pi: 8000 `hailo-ollama`, 8001 live camera viewer, 8002 this page.

### Live object detection (YOLO11m on the camera)

```
cd ~/hailo-live && ./run_live.sh          # Ctrl-C to stop
```

Open `http://192.168.4.28:8001/viewer.html` from any machine on the network. `capture_letterbox.py` pads each 640×480 camera frame to 640×640 (no stretching) and pipes it into `hailonet`; annotated frames are written to `live/latest.jpg` about 20 times a second. (The viewer is on 8001 because `hailo-ollama` owns 8000.)

### One-off tests

```
~/hailo_test/classify.sh image.jpg out.jpg                              # ResNet-50 label + score drawn on the image
~/yolo_test/compare.sh                                                  # YOLOv8m vs YOLO11m on ~/yolo_test/scenes/*.jpg -> out/<model>/
hailortcli run2 --measure-overall-latency set-net /usr/share/hailo-models/resnet_v1_50_h10.hef   # latency benchmark
```

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

**Rerun on HailoRT 5.2.0 (Oct 13, 2026):** the zoo now has `qwen2.5:1.5b` (not `qwen2.5-instruct:1.5b`), so both backends use that name. CPU (stock Ollama, same GGUF): DNS 11.8–11.9, physics 10.7–11.4, intro 12.0–12.1 tok/s. Hailo: DNS 6.8 and 4.3 tok/s (wall-clock) in the two runs finished before a reboot for the CMA change; the rest was not completed. The Pi was in use during the run, which may have lowered the numbers. A full Hailo rerun at 256 MB CMA is pending. Until it is done, treat the 5.2.0 Hailo speed as unknown and the 5.1.1 table above as the reference.

**Why the CPU is faster:** generating a token means streaming every weight of the model through the processor once, so tokens/s ≈ memory bandwidth ÷ bytes per token. Both sides have LPDDR4X-4267 (the HAT's own 8 GB is the same speed grade as the Pi 5's RAM; Hailo does not publish the bus width, so the HAT's bandwidth could equal the Pi's ~17 GB/s or exceed it). What is different is the model file: the Hailo HEF is 2.25 GB against 0.99 GB for the CPU GGUF of the same 1.5B model. At 6.8 tok/s × 2.25 GB the HAT is moving ~15 GB/s, the same class as the Pi's 11.5 tok/s × 0.99 GB ≈ 11 GB/s. So the measurements say the HAT is not short of bandwidth; it is spending ~2.3× the bytes per token on this first-generation LLM build (less compact quantization and packing), plus a young runtime (`hailo-ollama` 5.1.x vs years-old llama.cpp ARM tuning). That gap can shrink with software; the 40 TOPS can't help with it, because batch-1 decode reuses no weights. Vision is the opposite case (small weights reused across a whole image, compute-bound), which is why the HAT runs YOLO at 20 fps and the CPU at ~1.

**Answer quality (first run of each, in `voice/llm_bench_answers.md`):** both are weak and both invent things. Physics (correct: 1.43 s, 10.0 m, 2.86 s): CPU got the times right and the height wrong (arithmetic slip, 9.13 m); Hailo got the time and height right and the total wrong (3.47 s, wrong formula). DNS: CPU better structured, Hailo closer to the word limit but less accurate. Intro: CPU produced only a one-line title; Hailo wrote a real intro but invented products ("Raspberry Pi 3000").

**What this means:**
- The AI HAT+ 2 is bought for **vision**. For a 1.5B LLM it is ~40% slower per token than the CPU, and no accelerator in this class will beat the Pi's own memory bandwidth by much.
- The HAT's LLM advantage is that it leaves the CPU **free** (0–3% vs 100%) for Vosk, Piper, the web page and the camera. Whether that makes the voice assistant feel better is still untested: run the LLM on each backend while Vosk transcribes and Piper speaks, and compare.
- A voice-only topic assistant does not need the HAT. Snapshot-style "what do you see" doesn't either (CPU YOLO ~1 s per frame). Continuous live vision, or vision at the same time as voice, does (HAT, or the cheaper AI Camera/IMX500 with smaller models and no LLM).
- Both backends stay installed; the web page lists models from both and routes to the right one. `assistant.py` still uses the Hailo by default.

**Stock Ollama on the Pi (user-local, no sudo):**

```
mkdir -p ~/ollama/models && cd ~/ollama
wget https://github.com/ollama/ollama/releases/download/v0.40.3/ollama-linux-arm64.tar.zst   # 1.5 GB
tar --zstd -xf ollama-linux-arm64.tar.zst && rm ollama-linux-arm64.tar.zst                    # 2.1 GB unpacked
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=~/ollama/models OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 ~/ollama/bin/ollama serve
OLLAMA_HOST=127.0.0.1:11434 ~/ollama/bin/ollama pull qwen2.5:1.5b                             # 986 MB
```

It listens on loopback only. To start it at boot, install `pi-config/ollama.service` (**sudo**): `sudo cp ~/ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now ollama`. Re-run the comparison with `~/voice/.venv/bin/python ~/voice/llm_bench.py cpu=http://127.0.0.1:11434,qwen2.5:1.5b hailo=http://127.0.0.1:8000,qwen2.5:1.5b`.

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
  curl -s http://192.168.4.28:8000/api/chat -H 'Content-Type: application/json' \
    -d '{"model":"qwen2.5:1.5b","stream":false,"messages":[{"role":"user","content":"What is a Raspberry Pi?"}]}'
  ```
- Spoken question from a file: make one on the Mac with `say -o q.aiff "what is a raspberry pi" && afconvert -f WAVE -d LEI16@16000 -c 1 q.aiff q.wav`, copy it over, run `assistant.py --wav q.wav`.
- Service health: `systemctl is-active hailo-ollama`, `journalctl -u hailo-ollama -n 50`.

## Gotchas

- **`hailortcli run` refuses the Hailo-10H.** Use `run2`.
- **The Python `hailo_platform` API cannot load any `*_h10.hef` on HailoRT 5.1.1** (not re-tested on 5.2.0). `VDevice.configure()` returns `HAILO_NOT_IMPLEMENTED` (error 7) for all of them. Vision models must go through the GStreamer/TAPPAS plugins (`hailonet`, `hailofilter`, `hailooverlay`), which is what every script here does. `hailo_platform.genai` only covers LLM/VLM/speech classes.
- **YOLO11 needs the generic TAPPAS filter.** `hailofilter` with `function-name=yolov8m` hardcodes the `yolov8m/` tensor name; leave `function-name` unset for `yolov11m_h10.hef` and the filter finds the NMS tensor by pattern.
- **A GStreamer pipeline holds back its last frame.** Feeding one image produces no output; loop it (`multifilesrc loop=true num-buffers=10`) and keep the last file.
- **`rpicam-vid --post-process-file` recordings have no boxes** (overlay is drawn on the low-res stream, which isn't recorded) and `rpicam-still` with it prints "HailoRT not ready!". Use the TAPPAS pipelines instead.
- **HDMI audio only exists while a display is connected.** With both HDMI ports disconnected, PipeWire's default sink is "Dummy Output" (silent but succeeds) and `aplay` to HDMI fails with error 524. `assistant.py` prints a one-line `[TTS off …]` notice and carries on in text mode.
- **`~/.asoundrc` went missing once** between sessions. If `arecord -D usbmic` fails, re-run `deploy.sh`.
- **The 1.5B model invents facts** (it produced a fictional Raspberry Pi "founder"). Ask it things you can verify, and use RAG with real documents for the topic assistant.
- **Only Hailo zoo models run on the Hailo.** No arbitrary GGUF, no compiling your own LLM to HEF. Embeddings and RAG stay on the CPU.

## Measured so far

- HailoRT and firmware 5.2.0 on this Pi (upgraded Oct 13, 2026; 5.1.1 before that). Verified after the upgrade: `/dev/hailo0` present, PCIe link Gen 3 x1.
- ResNet-50: ~4.1 ms per frame (5.1.1).
- Live YOLO11m: ~20 annotated frames/s written (file-change rate, not display rate; 5.1.1). Not re-run on 5.2.0 yet.
- YOLO on a camera still: cup on a table at ~1 ft → "cup 69%" (YOLOv8m); a cup held at the lens was not detected; YOLO11m missed that cup but matched YOLOv8m on people. Four scenes are too few to pick a winner; both models are installed.
- LLM on 5.1.1: `qwen2.5-instruct:1.5b` ~6.5–7 tokens/s, `qwen2.5-coder:1.5b` ~7.5 tokens/s; first request after a model switch adds ~10 s. On 5.2.0, `qwen2.5:1.5b` measured 4.3–6.8 tokens/s (wall-clock, two runs; see "Rerun on HailoRT 5.2.0").
- Piper: a 3.1 s sentence took 4.7 s to synthesize including the one-time voice load (the split was not measured); in the assistant, sentences play with no noticeable gap.
- Voice assistant end to end (WAV in, speech to the dummy sink): first spoken word ~0.5 s after the question, whole 3-sentence answer ~18 s including playback.

## Not yet done

- Audible output has not been heard: no display on HDMI and no USB speaker yet. Plug a monitor/TV into HDMI0 and run `assistant.py`; `wpctl status` should show the HDMI sink.
- Live human voice on the mic has not been tested (all tests used WAV files or typed input).
- **Re-run the speed tests on 5.2.0.** The Hailo LLM benchmark at 256 MB CMA (`~/voice/bench_cma256.log`) and the monitor diagnostic (`~/voice/monitor_result.txt`, which runs `hailortcli monitor` next to `HAILO_MONITOR=1 hailortcli run2`) have not been read yet. Add the results to "CPU vs Hailo" and "Measured so far".
- **YOLO live test on 5.2.0 and 256 MB CMA** (`run_live.sh` on port 8001, or `compare.sh`) has not been run.
- **Reader tips not yet tested:** a systemd `ExecStartPre` delay for hailo-ollama and `HAILO_LOG_LEVEL=info`.
- **Install the CPU Ollama service (sudo).** The CPU Ollama on port 11434 is still started by hand and stops at reboot. Install `pi-config/ollama.service` as in "CPU vs Hailo".

## To do

- **RAG with Moonlighter test docs.** Make the assistant answer from real documents instead of inventing facts. Plan: LLM stays on the Hailo via `hailo-ollama`; embeddings and the vector store run on the CPU inside `~/voice/.venv` (no sudo). Steps: collect a few Moonlighter topic docs (markdown/text preferred) into `~/rag/docs/`; chunk and embed with a small sentence-transformers model; store locally (Chroma or a numpy index); add a retrieval step to `assistant.py` that puts the top matching chunks in the prompt; verify answers come from the docs and that removing a doc removes it from retrieval. **Blocked on the test docs from Moonlighter.**

## Sources

- [Raspberry Pi AI software docs](https://www.raspberrypi.com/documentation/computers/ai.html) — Hailo driver and LLM install steps
- [Waveshare AI HAT+ 2 wiki](https://www.waveshare.com/wiki/Raspberry_Pi_AI_HAT%2B_2)
- [pi-private-ai-server](https://github.com/btstevens1984az/pi-private-ai-server) — reference for `hailo-ollama`, the systemd unit and the RAG approach
- [Pi AI Guide (Moonlighter FabLab)](https://aimoonlighter.howto.rocks) — the program this is built for, repo at github.com/EmilMoonlighter/AI-Program
- [Vosk models](https://alphacephei.com/vosk/models), [Piper voices](https://github.com/rhasspy/piper)
