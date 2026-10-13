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
| `deploy.sh` | — | Copies all of the above to the Pi (everything except the sudo step) |

## Hardware

- Raspberry Pi 5 (8 GB) with active cooler and 27 W PSU
- Raspberry Pi AI HAT+ 2 (Hailo-10H, 8 GB on-board RAM) on the PCIe connector. No `dtparam=pciex1` line and no stacking board were needed; it was detected as soon as it was seated properly.
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
hailortcli fw-control identify        # Firmware 5.1.1, Device Architecture: HAILO10H
```

This pulls in `h10-hailort`, `h10-hailort-pcie-driver`, `python3-h10-hailort`, `hailo-tappas-core` 5.1.0, `hailo-models` 1.0.0 (the `.hef` files in `/usr/share/hailo-models/`), and `rpicam-apps-hailo-postprocess`. Installed versions: HailoRT 5.1.1.

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

`hailo-ollama` is Hailo's Ollama-compatible server. It runs curated HEF LLMs on the Hailo-10H's own 8 GB. Stock Ollama is CPU-only and is not used. Package version must match HailoRT (5.1.1). Source: the [official Raspberry Pi AI docs](https://www.raspberrypi.com/documentation/computers/ai.html).

```
cd ~ && wget https://dev-public.hailo.ai/2025_12/Hailo10/hailo_gen_ai_model_zoo_5.1.1_arm64.deb   # 7.9 MB
ssh -t admin@192.168.4.28 'sudo dpkg -i ~/hailo_gen_ai_model_zoo_5.1.1_arm64.deb'                   # (sudo)
```

Install the service (unit file comes from `pi-config/hailo-ollama.service` via `deploy.sh`; it runs as `admin`, restarts on failure, working directory `/home/admin`):

```
ssh -t admin@192.168.4.28 'sudo cp ~/hailo-ollama.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now hailo-ollama'   # (sudo)
```

Pull the models (about 1.5–2 MB/s here, so 15–20 minutes each):

```
curl -s http://127.0.0.1:8000/hailo/v1/list        # zoo: qwen2.5-instruct:1.5b, qwen2.5-coder:1.5b, qwen2:1.5b, llama3.2:3b, deepseek_r1_distill_qwen:1.5b
for m in qwen2.5-instruct:1.5b qwen2.5-coder:1.5b; do
  curl -s http://127.0.0.1:8000/api/pull -H 'Content-Type: application/json' -d "{\"model\": \"$m\", \"stream\": true}" | tail -c 200; echo
done
curl -s http://127.0.0.1:8000/api/tags             # shows what is pulled
```

Models land in `/usr/share/hailo-ollama/models/blob/` (instruct 2.25 GB, coder 1.67 GB, both Q4_0). Config is `/etc/xdg/hailo-ollama/hailo-ollama.json`; it binds `0.0.0.0:8000`, so the API is reachable from the LAN. Change `host` to `127.0.0.1` to keep it Pi-only.

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

Speak a question; it transcribes with Vosk, asks `qwen2.5-instruct:1.5b` on the Hailo (short-answer system prompt, last 4 turns kept as context), streams the reply, and speaks each sentence with Piper as it completes (first word about 0.5 s after you stop talking). Mic input is dropped while it speaks. Say "stop listening" to quit.

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

If you ever start it by hand instead (`~/voice/.venv/bin/python ~/web/app.py`), stop that copy before enabling the service: two instances cannot share port 8002, and the service will crash-loop with "Address already in use" until the hand-started one is gone (`pkill -f "^/home/admin/voice/.venv/bin/python app.py"`). After editing `web/app.py`, run `./deploy.sh` and then `sudo systemctl restart pi-web`.

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
    -d '{"model":"qwen2.5-instruct:1.5b","stream":false,"messages":[{"role":"user","content":"What is a Raspberry Pi?"}]}'
  ```
- Spoken question from a file: make one on the Mac with `say -o q.aiff "what is a raspberry pi" && afconvert -f WAVE -d LEI16@16000 -c 1 q.aiff q.wav`, copy it over, run `assistant.py --wav q.wav`.
- Service health: `systemctl is-active hailo-ollama`, `journalctl -u hailo-ollama -n 50`.

## Gotchas

- **`hailortcli run` refuses the Hailo-10H.** Use `run2`.
- **The Python `hailo_platform` API cannot load any `*_h10.hef` on HailoRT 5.1.1.** `VDevice.configure()` returns `HAILO_NOT_IMPLEMENTED` (error 7) for all of them. Vision models must go through the GStreamer/TAPPAS plugins (`hailonet`, `hailofilter`, `hailooverlay`), which is what every script here does. `hailo_platform.genai` only covers LLM/VLM/speech classes.
- **YOLO11 needs the generic TAPPAS filter.** `hailofilter` with `function-name=yolov8m` hardcodes the `yolov8m/` tensor name; leave `function-name` unset for `yolov11m_h10.hef` and the filter finds the NMS tensor by pattern.
- **A GStreamer pipeline holds back its last frame.** Feeding one image produces no output; loop it (`multifilesrc loop=true num-buffers=10`) and keep the last file.
- **`rpicam-vid --post-process-file` recordings have no boxes** (overlay is drawn on the low-res stream, which isn't recorded) and `rpicam-still` with it prints "HailoRT not ready!". Use the TAPPAS pipelines instead.
- **HDMI audio only exists while a display is connected.** With both HDMI ports disconnected, PipeWire's default sink is "Dummy Output" (silent but succeeds) and `aplay` to HDMI fails with error 524. `assistant.py` prints a one-line `[TTS off …]` notice and carries on in text mode.
- **`~/.asoundrc` went missing once** between sessions. If `arecord -D usbmic` fails, re-run `deploy.sh`.
- **The 1.5B model invents facts** (it produced a fictional Raspberry Pi "founder"). Ask it things you can verify, and use RAG with real documents for the topic assistant.
- **Only Hailo zoo models run on the Hailo.** No arbitrary GGUF, no compiling your own LLM to HEF. Embeddings and RAG stay on the CPU.

## Measured so far

- Hailo-10H firmware 5.1.1; no newer packages in the Raspberry Pi trixie repo as of Oct 12, 2026.
- ResNet-50: ~4.1 ms per frame.
- Live YOLO11m: ~20 annotated frames/s written (file-change rate, not display rate).
- YOLO on a camera still: cup on a table at ~1 ft → "cup 69%" (YOLOv8m); a cup held at the lens was not detected; YOLO11m missed that cup but matched YOLOv8m on people. Four scenes are too few to pick a winner; both models are installed.
- LLM: `qwen2.5-instruct:1.5b` ~6.5–7 tokens/s, `qwen2.5-coder:1.5b` ~7.5 tokens/s; first request after a model switch adds ~10 s. A 131-token answer takes ~19 s; a 35-token answer ~5 s.
- Piper: a 3.1 s sentence took 4.7 s to synthesize including the one-time voice load (the split was not measured); in the assistant, sentences play with no noticeable gap.
- Voice assistant end to end (WAV in, speech to the dummy sink): first spoken word ~0.5 s after the question, whole 3-sentence answer ~18 s including playback.

## Not yet done

- Audible output has not been heard: no display on HDMI and no USB speaker yet. Plug a monitor/TV into HDMI0 and run `assistant.py`; `wpctl status` should show the HDMI sink.
- Live human voice on the mic has not been tested (all tests used WAV files or typed input).

## To do

- **RAG with Moonlighter test docs.** Make the assistant answer from real documents instead of inventing facts. Plan: LLM stays on the Hailo via `hailo-ollama`; embeddings and the vector store run on the CPU inside `~/voice/.venv` (no sudo). Steps: collect a few Moonlighter topic docs (markdown/text preferred) into `~/rag/docs/`; chunk and embed with a small sentence-transformers model; store locally (Chroma or a numpy index); add a retrieval step to `assistant.py` that puts the top matching chunks in the prompt; verify answers come from the docs and that removing a doc removes it from retrieval. **Blocked on the test docs from Moonlighter.**

## Sources

- [Raspberry Pi AI software docs](https://www.raspberrypi.com/documentation/computers/ai.html) — Hailo driver and LLM install steps
- [Waveshare AI HAT+ 2 wiki](https://www.waveshare.com/wiki/Raspberry_Pi_AI_HAT%2B_2)
- [pi-private-ai-server](https://github.com/btstevens1984az/pi-private-ai-server) — reference for `hailo-ollama`, the systemd unit and the RAG approach
- [Pi AI Guide (Moonlighter FabLab)](https://aimoonlighter.howto.rocks) — the program this is built for, repo at github.com/EmilMoonlighter/AI-Program
- [Vosk models](https://alphacephei.com/vosk/models), [Piper voices](https://github.com/rhasspy/piper)
