# Raspberry Pi 5 + AI HAT+ 2 voice assistant (ML-AI)

A Raspberry Pi 5 with an AI HAT+ 2 (Hailo-10H) that listens on a USB mic, answers with a local LLM running on the HAT, answers from the Maker Space's own documents, speaks with Piper, and watches the room through the Pi camera with YOLO on the same HAT. Everything runs offline on the Pi and starts at boot. The web page at **http://ml-ai.local/** is the front end. This is the base for the AI program at **Moonlighter Maker Space in Miami, Florida**, where students learn about AI and computing by building and running it themselves.

- Pi: `admin@ml-ai.local` (mDNS; the DHCP address moves, use the name), hostname `ML-AI`, Raspberry Pi OS 64-bit (Debian 13 trixie), kernel 6.18, Python 3.13, 8 GB RAM, 32 GB SD (a 64 GB card is on order).
- There is a second Pi, a copy, named `ml-pi` (`admin@ml-pi.local`). Everything here applies to it too; its page is http://ml-pi.local/.
- **Everything runs from the Pi itself, no computer needed.** Plug in a keyboard and screen (or open a terminal on the Pi any other way), then follow "Quick start" below: it downloads this repo from GitHub onto the Pi and installs and updates from there. A Mac is optional (see "Working from a computer").
- HailoRT, firmware, model zoo and TAPPAS all **5.3.0** (since Oct 19, 2026).
- Passwordless sudo is **not** set up. Steps marked **(sudo)** need the `admin` password, which the Pi asks for when you run `sudo ...` in its terminal. (From a computer: `ssh -t admin@ml-ai.local 'sudo ...'`.)
- **Power:** the Pi currently runs on a Mac USB-C charger, which only gives 3 A at 5 V. Under full load it browns out (see Gotchas). The official 27 W / 5 A supply is on order.

## What is in this repo

| Path | Goes to (on the Pi) | What it is |
|---|---|---|
| `setup-pi.sh` | `~/` | From-scratch installer for a new SD card (staged, re-runnable, two reboots) |
| `deploy.sh` | — | Copies everything below to its place on the Pi and restarts the services that need it (no sudo). Run it from the Mac (`./deploy.sh`) or on the Pi from the clone (`./deploy.sh --local`) |
| `voice/assistant.py` | `~/voice/` | Voice assistant: USB mic → Vosk → LLM on the HAT (+ documents, camera) → Piper |
| `voice/stt_fix.py` | `~/voice/` | Vocabulary corrections for every transcript ("pie"→"pi", "i had"→"ai hat", ...) |
| `voice/stt_bench.py`, `voice/llm_bench.py` | `~/voice/` | Speech-recognition and LLM benchmarks (see History) |
| `voice/listen.py` | `~/voice/` | The original fixed-command listener, kept as a teaching example |
| `web/app.py`, `web/index.html` | `~/web/` | The page: chat with sources, speak, hold-to-talk, transcript, camera |
| `rag/rag.py` | `~/rag/` | Document index and retrieval over `~/rag/docs/` (PDF with OCR, .txt, .md) |
| `hailo-live/live_yolo.py`, `run_live.sh`, `stop_live.sh`, `viewer.html` | `~/hailo-live/` | Live YOLO11m on the camera through the HailoRT Python API, shares the HAT with the LLM |
| `hailo-test/vlm_test.py` | `~/hailo_test/` | Qwen2-VL-2B vision-language model on the HAT (image or camera frame) |
| `hailo-test/classify.sh`, `hailo-test/compare.sh` | `~/hailo_test/`, `~/yolo_test/` | One-off vision tests (ResNet-50; YOLOv8m vs YOLO11m through GStreamer) |
| `pi-config/*.service` | `/etc/systemd/system/` **(sudo)** | The four boot services: `hailo-ollama`, `pi-web`, `voice`, `hailo-live` |
| `pi-config/asoundrc` | `~/.asoundrc` | Optional `usbmic` ALSA alias for typing `arecord -D usbmic` |

## Hardware

- Raspberry Pi 5 (8 GB) with active cooler. Needs the official 27 W (5 V / 5 A) supply; a 3 A charger is what is plugged in today and it is not enough (Gotchas).
- Raspberry Pi AI HAT+ 2 (Hailo-10H, 8 GB on-board RAM) on the PCIe connector. Detected as soon as it is seated; no `config.txt` lines needed. The link runs at PCIe Gen 3 x1 automatically.
- Raspberry Pi Camera Module 3 (IMX708) on the CSI connector.
- USB microphone (TI PCM2902, "USB PnP Sound Device"), capture only.
- Audio out: PipeWire's default sink, which is HDMI when a display with audio is on HDMI0, or a USB speaker. Neither has been attached yet, so the assistant has only ever been heard as text.

## Install

### Quick start (on the Pi, no computer needed)

Written for students: every step says what it does and why, so you learn how a computer gets set up while you set one up. Type each command into the Pi's **terminal** (the black window where you type commands). If a command asks for a password, it is the `admin` password; the screen shows nothing while you type it, that is normal.

1. **Flash the SD card.** The SD card is the Pi's hard drive. With the Raspberry Pi Imager, choose Raspberry Pi OS 64-bit (trixie), set hostname `ML-AI` (or `ML-Pi`), user `admin`, turn SSH on, add your Wi-Fi, and keep "verify" on. Put the card in the Pi and power it up.
2. **Install git.** Git is the tool that downloads and tracks code, the way Google Docs tracks versions of a document. Pi OS usually has it already; this makes sure:
   ```
   sudo apt update && sudo apt install -y git
   ```
   (`sudo` means "do this as the boss of the computer", which is why it asks for the password. `apt` is the Pi's app store for the command line.)
3. **Pull the repo.** A *repo* (repository) is a project folder kept on GitHub. *Cloning* it copies the whole project, with its history, onto the Pi. This repo is public, so no password or key is needed:
   ```
   git clone https://github.com/MarioCruz/ML-AI.git ~/ML-AI
   ```
   Add `~/ML-AI` at the end so it lands in your home folder with that name.

   Look at what you downloaded: `ls ~/ML-AI`. The code, the install script and this README are all there.
4. **Put the files in place.** `~/ML-AI/deploy.sh --local` copies each program from the repo folder to where the Pi runs it from (the voice assistant to `~/voice`, the web page to `~/web`, and so on). A *script* is just a text file of commands the computer runs for you; open it and read it: `less ~/ML-AI/deploy.sh` (press `q` to leave).
5. **Add the documents** the assistant should know about: copy PDFs, `.txt` or `.md` files into `~/rag/docs/` (USB stick, or `curl -L -o ~/rag/docs/name.pdf <url>`). The install turns them into a searchable index.
6. **Run the installer.** `~/setup-pi.sh` installs everything else: the Hailo AI chip's driver and software, the speech and voice tools, the AI models, and the four services that start at boot. It takes a while and reboots the Pi twice; after each reboot run `~/setup-pi.sh` again and it carries on where it stopped. Use the wait to read it: `less ~/setup-pi.sh`.
7. **Try it.** Open http://ml-ai.local/ (or http://ml-pi.local/) on any phone or laptop on the same Wi-Fi, ask a question, then say "hey pi" to the USB microphone. "Test checklist" below shows how to check each part is healthy.

**To update later**, on the Pi: `cd ~/ML-AI && git pull && ./deploy.sh --local`. `git pull` downloads whatever changed on GitHub since you cloned.

**Things to explore** once it runs: change what the assistant says by editing the wake phrase in `~/ML-AI/pi-config/voice.service`, add your own notes to `~/rag/docs/` and rebuild (see "Answering from documents"), or look at what the camera sees at http://ml-ai.local/. Each of these teaches one idea: configuration files, giving a program new information, and how a computer sees.

The script records each finished stage in `~/.setup-pi.done` and stops twice to ask for a reboot (after the OS update if the kernel changed, and after the Hailo driver); after each reboot run `~/setup-pi.sh` again and it continues. Stages: OS packages (including `tesseract-ocr`, `hailo-models`, not `hailo-h10-all`), kernel command line sanity, HailoRT 5.3.0 from Hailo's bucket with the driver patch (below), the Python venv with the speech, TTS, embedding and HailoRT packages plus the Vosk and Piper models, the four services, the LLM pulls (about 2 minutes each at 29 MB/s) and the 3.2 GB VLM file, and the document index. Stages 1 and 2 are proven; the rest was written from the by-hand steps below and gets its first full run on the next card.

### By hand (what the script does)

**OS.** `sudo apt update && sudo apt full-upgrade -y`, then `dkms build-essential linux-headers-rpi-2712 ffmpeg poppler-utils tesseract-ocr python3-venv python3-picamera2 hailo-models`. Do not install `hailo-h10-all` or `hailo-tappas-core` from apt: they pin HailoRT 5.1.1 and TAPPAS 5.1.0.

**HailoRT 5.3.0 (sudo).** The four packages are in Hailo's bucket, `https://dev-public.hailo.ai/2026_04/Hailo10/`: `hailort_5.3.0_arm64.deb`, `hailort-pcie-driver_5.3.0_all.deb`, `hailo_gen_ai_model_zoo_5.3.0_arm64.deb`, `hailo-tappas-core_5.3.0_arm64.deb`, plus the Python wheel `hailort-5.3.0-cp313-cp313-linux_aarch64.whl` (not linked from Hailo's site). The driver source does not build on kernel 6.15+ as shipped (`del_timer_sync` was removed from the kernel), so unpack first, patch one line, then configure:

```
sudo dpkg --unpack ~/hailo530/hailort_5.3.0_arm64.deb ~/hailo530/hailort-pcie-driver_5.3.0_all.deb ~/hailo530/hailo_gen_ai_model_zoo_5.3.0_arm64.deb
sudo sed -i 's/\bdel_timer_sync(/timer_delete_sync(/' /usr/src/hailort-pcie-driver/linux/vdma/monitor.c
sudo dpkg --configure -a                                            # builds the driver through dkms, a few minutes
sudo apt install -y ~/hailo530/hailo-tappas-core_5.3.0_arm64.deb    # apt resolves its -dev dependencies
sudo apt-mark manual hailo-models hailo-tappas-core                 # or a later autoremove deletes the vision models
sudo reboot
```

Verify: `hailortcli fw-control identify` says firmware 5.3.0; the device node is `/dev/h1x-0` (mode 0666 from the package's udev rule). The `hailo-gen-ai-model-zoo` package depends on the generic `hailort`, which is why this Pi uses the generic packages rather than the `h10-*` ones from apt.

**Camera and mic.** Nothing to install. `rpicam-hello --list-cameras` lists the imx708; `arecord -D plughw:CARD=Device,DEV=0 -f S16_LE -r 16000 -c 1 -d 3 test.wav` records from the USB mic. The assistant opens the mic by that card name, so `~/.asoundrc` is optional.

**Voice environment (no sudo).**

```
python3 -m venv ~/voice/.venv
~/voice/.venv/bin/pip install vosk==0.3.45 requests sounddevice piper-tts==1.8.0 flask fastembed opencv-python-headless numpy ~/hailo530/hailort-5.3.0-cp313-cp313-linux_aarch64.whl
cd ~/voice && curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && unzip -q vosk-model-small-en-us-0.15.zip && mv vosk-model-small-en-us-0.15 model && rm vosk-model-small-en-us-0.15.zip
mkdir -p ~/voice/piper && cd ~/voice/piper && ~/voice/.venv/bin/python -m piper.download_voices en_US-lessac-medium
```

**Services (sudo).** The unit files are copied to `~` by `deploy.sh`.

```
sudo cp ~/hailo-ollama.service ~/pi-web.service ~/hailo-live.service ~/voice.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo loginctl enable-linger admin
sudo systemctl enable --now hailo-ollama pi-web voice hailo-live
```

`enable-linger` keeps the admin user session (PipeWire, the mic) alive without a login. `pi-web` binds port 80 through `AmbientCapabilities=CAP_NET_BIND_SERVICE`.

**LLM models.** `hailo-ollama` is Hailo's Ollama-compatible server for the HAT. The 5.3.0 zoo lists `qwen2.5:1.5b`, `llama3.2:1b`, `qwen2.5-coder:1.5b`, `qwen2:1.5b`, `deepseek_r1:1.5b`, `qwen3:1.7b` (`curl -s localhost:8000/hailo/v1/list`). Pulled here: `qwen2.5:1.5b` (default, 2.5 GB) and `llama3.2:1b` (1.4 GB, faster, not smarter). Models land in `~/.local/share/hailo-ollama/models/blob/`.

```
for m in qwen2.5:1.5b llama3.2:1b; do curl -s -N -X POST localhost:8000/api/pull -H 'Content-Type: application/json' -d "{\"model\":\"$m\"}" | tail -c 100; echo; done
curl -s localhost:8000/api/tags            # what is pulled
```

**Documents.** Copy PDFs, `.txt` or `.md` into `~/rag/docs/` and run `~/voice/.venv/bin/python ~/rag/rag.py build` (see "Answering from documents").

**Vision-language model.** `wget -O ~/hailo530/Qwen2-VL-2B-Instruct.hef https://dev-public.hailo.ai/v5.3.0/blob/Qwen2-VL-2B-Instruct.hef` (3.2 GB; the HEF version must match HailoRT).

### Updating code

**On the Pi:** `cd ~/ML-AI && git pull && ./deploy.sh --local`. The script copies the files and kills the running `pi-web`, `voice` and `hailo-live` processes; their units have `Restart=always`, so systemd starts them again with the new code, no sudo needed. Changing a unit file still needs `sudo cp ... /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart <unit>`.

### Working from a computer (optional)

Not required. From a Mac you can do the same without touching the Pi: `ssh-copy-id admin@ml-ai.local`, then in a clone of this repo `./deploy.sh` (copies over SSH and restarts the services), and `ssh -t admin@ml-ai.local ~/setup-pi.sh` to install. Edit on the Mac, `./deploy.sh`; or edit on the Pi in `~/ML-AI`, `./deploy.sh --local`.

### The four services

| service | what | where |
|---|---|---|
| `hailo-ollama` | LLM server on the HAT, one request at a time, one model loaded at a time (switching costs ~10 s) | port 8000 |
| `pi-web` | the page: chat, speak, hold-to-talk, transcript, camera, sources | **http://ml-ai.local/** |
| `hailo-live` | YOLO11m on the camera at 15 fps, sharing the HAT with the LLM; the page's camera panel shows its frames | raw viewer on port 8001 |
| `voice` | microphone assistant, wake phrase "hey pi", speaks through the PipeWire default sink; questions and answers appear in the page's transcript | — |

Logs: `journalctl -u voice -f` (same for the others). Idle cost: `voice` keeps Vosk transcribing the room, about 30% of one core; `hailo-live` about 10%; the HAT does the detection. Speech that does not start with the wake phrase shows in the voice log as `HEARD:` lines but is neither logged to the page nor able to stop the assistant. To change the wake phrase or output device, edit `pi-config/voice.service`, deploy, and reinstall the unit (sudo).

### The page

- **Chat**: the reply streams from the LLM with a short-answer system prompt and the last 4 turns as history; answers are capped at 120 tokens. "New conversation" clears the history. A model picker lists what is pulled.
- **Sources line** under each answer: the manual pages the answer came from, or "camera".
- **Asking about the camera**: a question containing camera, see, look, watch, "in front of you", "what is this", recognize or detect gets the detector's current list put in front of the model ("The camera currently sees: person (92%), cup (69%). Question: ..."). It knows the 80 COCO object classes, no colours or text. Works by voice too: "hey pi, what do you see?"
- **Speak replies on the Pi**: each sentence is spoken through the Pi's audio output while the text streams. Silent until a speaker or HDMI display is attached.
- **Hold to talk**: records in the browser and transcribes on the Pi. Browsers only allow the mic on HTTPS or `localhost`, so over `http://ml-ai.local` it reports "mic not available"; typing and the Pi's own USB mic are unaffected.
- **Transcript**: live `HEARD:` / `ANSWER:` lines from the voice assistant.
- **Camera**: the latest annotated frame while `hailo-live` runs.

Endpoints for students: `POST /api/chat` (NDJSON stream, body `{"message": ..., "model": "hailo|qwen2.5:1.5b", "no_rag": false}`), `POST /api/transcribe`, `POST /api/speak`, `POST /api/reset`, `GET /api/transcript` (server-sent events), `GET /api/camera`, `GET /api/status`.

### Voice assistant by hand

`~/voice/.venv/bin/python ~/voice/assistant.py` (stop the `voice` service first, they share the mic). Options: `--text` type instead of speaking, `--no-tts` print only, `--wav file.wav` feed a 16 kHz mono WAV, `--wake "hey pi"`, `--confirm` read back what was heard, `--model llama3.2:1b`, `--no-rag`, `--no-fix` (disable `stt_fix.py`), `--stt-model small|big|DIR`, `--out pw|hdmi|usb|DEVICE`.

### Answering from documents (RAG)

The 1.5B models invent facts, so the assistant and the page answer from `~/rag/docs/` when an index exists. The LLM stays on the HAT; the only CPU work is a 65 MB sentence-embedding model (`BAAI/bge-small-en-v1.5` through `fastembed`): about 15 ms per question.

```
cp manual.pdf notes.md ~/rag/docs/
~/voice/.venv/bin/python ~/rag/rag.py build                              # rebuild after adding or removing documents
~/voice/.venv/bin/python ~/rag/rag.py search "how do I load filament"    # retrieval only: scores, document, page
~/voice/.venv/bin/python ~/rag/rag.py ask "how do I load filament"       # retrieval + answer from the HAT, with sources
```

How it works: `pdftotext` splits each PDF into pages; pages without a text layer are OCR'd with `tesseract`; pages are cut into ~180-word chunks (40-word overlap) that remember their file and page, embedded, and stored as a numpy array in `~/rag/index/`. For a question, the top 3 chunks with cosine score ≥ 0.60 (plus a small boost for chunks dense in the question's own words) go into the user turn, capped at ~420 words because the HAT models have a 2048-token context. Below 0.60 nothing is added and the model answers on its own. History keeps the plain question only.

Current index: 360 chunks from 5 documents (Bambu Lab H2D 3D Printing User Manual, three H2D quick-start guides via OCR, xTool O1 Omni quick start). Manual questions retrieve the right pages at scores 0.69–0.85; an off-topic question scores ~0.41 and gets no excerpts; removing a document and rebuilding removes its pages. **Rebuild with the voice and camera services paused until the 5 A supply is in** (`kill -STOP`/`-CONT` on their PIDs, no sudo; the embedding step is capped at 2 threads by `RAG_THREADS`): the OCR of 108 pages takes about 2 minutes and the embedding 106 s.

### Live object detection

`hailo-live/live_yolo.py` runs `yolov11m_h10.hef` through the HailoRT Python API with the same VDevice group id as `hailo-ollama`, so both use the HAT at once: 15 fps while the LLM is loaded, about 5.6 fps while it generates. Each frame is letterboxed to 640×640, run through the on-chip NMS, drawn, and written to `live/latest.jpg` with the detections in `live/latest.json`. `run_live.sh` starts it plus the viewer on 8001; `stop_live.sh` stops both; `live_yolo.py --image in.jpg --out out.jpg` runs one image and prints what it found. The service holds the camera: stop it (`sudo systemctl stop hailo-live`) before `rpicam-still` or `vlm_test.py --camera`.

### Vision-language model (Qwen2-VL-2B)

`hailo-ollama` serves text LLMs only; the VLM runs through the HailoRT Python GenAI API, and only one generative model can be loaded on the HAT, so the LLM must be stopped first:

```
sudo systemctl stop hailo-ollama                                                              # (sudo)
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --image photo.jpg --prompt "Describe this image in two sentences."
~/voice/.venv/bin/python ~/hailo_test/vlm_test.py --camera --max-tokens 80                    # stop hailo-live first
sudo systemctl start hailo-ollama                                                             # (sudo)
```

About 7 tok/s including the image prefill; 8 s to load warm, 33 s cold from the SD card. It recognises open-vocabulary things ("a 3D printer") that YOLO cannot. It ignores sentence limits in the prompt, so bound answers with `--max-tokens`.

### One-off tests

```
~/hailo_test/classify.sh image.jpg out.jpg      # ResNet-50 label on the image (~4 ms per frame)
~/yolo_test/compare.sh                          # YOLOv8m vs YOLO11m on ~/yolo_test/scenes/*.jpg; GStreamer, needs the LLM idle
~/voice/.venv/bin/python ~/voice/llm_bench.py hailo=http://127.0.0.1:8000,llama3.2:1b   # LLM speed; copy results aside first
~/voice/.venv/bin/python ~/voice/stt_bench.py --fix ~/voice/sttset/manifest.txt ~/voice/model   # speech accuracy on the WAV test set
curl -s localhost:8000/api/chat -H 'Content-Type: application/json' -d '{"model":"qwen2.5:1.5b","stream":false,"messages":[{"role":"user","content":"What is a Raspberry Pi?"}]}'
```

## Test checklist

After any upgrade, kernel change or reboot:

```
hailortcli fw-control identify | grep -i "firmware version"   # 5.3.0; device node /dev/h1x-0
vcgencmd get_throttled                                        # 0x0 is healthy; 0x50000 = under-voltage happened (Gotchas)
grep CmaTotal /proc/meminfo                                   # 65536 kB (never set cma= by hand)
rpicam-hello --list-cameras                                   # imx708 listed
systemctl is-active hailo-ollama pi-web voice hailo-live      # four times "active"
curl -s localhost/api/status                                  # "backends": ["hailo"], "camera": true, "rag_docs": [...]
curl -s localhost:8000/api/tags | grep -o '"name":"[^"]*"'    # pulled models
cat /sys/fs/ext4/mmcblk0p2/errors_count                       # 0
```

Then open http://ml-ai.local/, ask "How do I load filament into the AMS?" (sources: manual pages) and "What does the camera see?" (source: camera).

## Measurements

| What | Result |
|---|---|
| LLM on the HAT, `qwen2.5:1.5b` | 6.8 tok/s (wall-clock; Hailo quotes 7.4), 0–3% CPU, ~15–23 s per short answer with retrieval |
| LLM on the HAT, `llama3.2:1b` | 8.4 tok/s (Hailo quotes 9.9); answers no better |
| Same model on the Pi CPU (llama.cpp, removed) | 11.5 tok/s at 100% of 4 cores; see History for why the CPU wins on 1.5B decode |
| Live YOLO11m, Python API | 27–35 ms per inference; 15 fps alongside the loaded LLM, 5.6 fps while it generates |
| ResNet-50 | 4.1 ms per frame |
| Qwen2-VL-2B | ~7 tok/s incl. image prefill; load 8 s warm, 33 s cold |
| Speech (Vosk small + `stt_fix.py`) | 6.9% word error rate on the synthetic test set, 2.4× real time; raw small 11.3% |
| Retrieval | 15 ms per query; 106 s to embed 360 chunks on 2 threads |
| Voice end to end (WAV in) | first spoken word ~0.5 s after the question |
| Idle load with all four services | ~0.5 load average, 48 °C |
| Model pulls | ~29 MB/s from Hailo's CDN, 1–3 min per model |

## Gotchas

- **Power supply.** A USB-C charger that only offers 5 V at 3 A (a Mac charger does) is not enough. `vcgencmd get_throttled` showed `0x50000` (under-voltage and throttling occurred) and later `0x50005` (happening now) during a single chat with the camera and voice running; `/proc/device-tree/chosen/power/max_current` reads 3000 mA; the kernel logged "Undervoltage detected!" and the Pi hung twice in one evening. Answers slowed from ~15 s to 41 s while throttled. Brownout resets can corrupt the SD card. Use the official 27 W supply. `usb_max_current_enable=1` in `config.txt` only raises the USB port budget; it does not fix this.
- **HAT sharing.** `hailo-ollama.service` sets `HAILO_OLLAMA_VDEVICE_GROUP_ID=HAILO_OLLAMA_SHARED`; any HailoRT app that opens its VDevice with `group_id = "HAILO_OLLAMA_SHARED"` (Python `VDevice.create_params()`) shares the HAT with the LLM. Anything else gets `HAILO_OUT_OF_PHYSICAL_DEVICES` (74) while a model is loaded (`hailortcli run2`, GStreamer `hailonet` even with `vdevice-group-id`, any other group). If something else grabs the device first, `hailo-ollama` returns 500s and may segfault until restarted. Only one LLM/VLM can be loaded at a time.
- **Never release a shared VDevice while a model is still configured on it.** It takes the HAT down for every process (kernel: "Trying to enable channels ... already enabled", hailo-ollama status 72) until `hailo-ollama` is restarted. `live_yolo.py` closes the model first.
- **hailo-ollama 5.3.0 rejects newlines.** Any message containing `\n` or `\t` returns 500 "Failed to render prompt from JSON strings". `assistant.hailo_safe()` flattens whitespace right before sending; the page and `rag.py` reuse it.
- **The 1.5B model is weak.** It invents facts without documents, and with documents it still merges neighbouring sentences ("what is the AMS?" came back with the HMS definition from the same excerpt). Keep questions specific, keep answers capped (`LLM_OPTIONS` in `assistant.py`), check the sources line. Putting the instruction after the excerpts made it worse.
- **Only Hailo zoo models run on the HAT.** No GGUF, no compiling your own LLM. The Python `hailo_platform` vision API works on 5.3.0 (it failed with error 7 on 5.1.1); the zoo's HEF version must match the installed HailoRT.
- **Never put `cma=` on the kernel command line.** It moves the CMA pool out of the firmware's reach: the firmware mailbox dies, `vcgencmd` says `ioctl_set_msg failed`, `rpicam-hello` says "only supports the Raspberry Pi platforms", no camera, no 3D. Use `dtoverlay=vc4-kms-v3d,cma-256` in `config.txt` if a bigger pool is ever wanted. It gave the LLM nothing anyway.
- **Forcing a filesystem check.** `/forcefsck` is ignored for the root filesystem on this image; put `fsck.mode=force` on `/boot/firmware/cmdline.txt` for one boot (`setup-pi.sh` stage 2 removes it again).
- **SD cards.** A card that passes a full write-and-read test on the Mac can still corrupt on the Pi if the Pi browns out while writing (first boot is the heaviest write). After a corruption: `fsck.mode=force`, then check `/sys/fs/ext4/mmcblk0p2/errors_count` stays 0. One 64 GB card corrupted twice and then stopped answering the Mac's reader entirely; it went back to the seller.
- **The USB mic is opened by card name** (`plughw:CARD=Device,DEV=0`, overridable with `ASSISTANT_MIC`). `~/.asoundrc` is optional; `raspi-config` and the desktop volume applet rewrite it. After one boot the mic refused to open for seven minutes, so `voice.service` waits for a successful one-second test capture before starting.
- **`apt autoremove` would delete `hailo-models`** (the vision HEFs) now that no meta-package depends on it: `sudo apt-mark manual hailo-models hailo-tappas-core`.
- **`pkill -f` inside an ssh command kills the ssh shell too** when the pattern appears in the command line. Use `stop_live.sh`, or `kill` by PID.
- **HDMI audio only exists while a display is connected.** Otherwise the default sink is "Dummy Output": silent, no error; the assistant prints `[TTS off ...]` and carries on in text.
- **GStreamer notes** (still used by `compare.sh`): `hailortcli run` refuses the Hailo-10H, use `run2`; YOLO11 needs the generic TAPPAS filter (no `function-name`); a pipeline holds back its last frame, so loop single images with `multifilesrc loop=true num-buffers=10`; `rpicam-vid --post-process-file` recordings have no boxes.

## History and lessons

- **Oct 11–12, 2026, bring-up on HailoRT 5.1.1** from apt (`hailo-h10-all`). ResNet-50 and YOLOv8m/YOLO11m through TAPPAS; the Python vision API failed (error 7). Vosk + hailo-ollama + Piper assistant, `stt_fix.py` after a 60-WAV benchmark (small model 11.3% WER → 6.9% with the fixes; the 2.7 GB "big" model gained nothing and slowed the LLM's first word to 32 s, deleted since). Web front end on port 8002.
- **Oct 13, CPU vs Hailo.** The same `qwen2.5:1.5b` as a GGUF on the Pi CPU (stock Ollama) ran at 11.5 tok/s at 100% of 4 cores against 6.8 tok/s on the HAT at 0–3% CPU. Token generation is memory-bandwidth bound; the HAT's HEF moves 2.25 GB per token against 0.99 GB for the GGUF, so the chip's 40 TOPS cannot help. The HAT's value is vision (YOLO at 15–20 fps vs ~1 on the CPU) and a free CPU. Both backends stayed until Oct 19, when the decision became **nothing runs on the Pi CPU except Vosk, Piper and the embedding model** and the CPU Ollama was removed. The benchmark script and the answers are in `voice/`.
- **Oct 13, HailoRT 5.2.0** from Hailo's bucket (`2026_01/Hailo10/`): first attempt mismatched driver and runtime; models renamed (`qwen2.5-instruct` → `qwen2.5`). Also the `cma=256M` experiment, which broke the camera (see Gotchas) and was reverted Oct 19.
- **Oct 19, morning.** Llama 3.2 1B pulled and benchmarked. Qwen2-VL-2B running through the Python GenAI API with a wheel found in the bucket. The camera bug traced to `cma=` and fixed. CPU Ollama removed. Boot services for everything, page moved to port 80. Google's Gemma models are not in Hailo's zoo, so they cannot run on the HAT; `llmfit` only scores CPU fits and knows nothing about the HAT.
- **Oct 19, afternoon.** RAG built over the H2D and xTool manuals (fastembed on the CPU, numpy index, sources in the page). `hailo-live` enabled at boot collided with the LLM on 5.2.0 (the HAT cannot be shared there: hailo-ollama releases it after 5 idle minutes and cannot get it back). Upgrade to **5.3.0** (driver patch for kernel 6.18; models now in `~/.local/share`; TAPPAS 5.3.0 too). Sharing works through the Python API but not through `hailonet`, so the live viewer was rewritten in Python. hailo-ollama 5.3.0's newline bug found and worked around.
- **Oct 19, evening.** A new 64 GB card corrupted on first boot twice and then died; `setup-pi.sh` written and its first two stages verified on it. The real cause of the crashes identified: a 3 A charger. `tesseract` installed, all five manuals indexed. Camera questions added. Unused models deleted (card 73% → 56% full).

## Teaching it about local equipment

Two different things, with very different answers.

**Knowledge (the LLM): use the documents, not training.** Nothing can be trained or fine-tuned for the HAT: only Hailo's precompiled models run on it and Hailo publishes no tool to compile an LLM. What the assistant knows about the Maker Space's equipment comes from `~/rag/docs/`: manuals, lesson notes, a markdown file of house rules. Copy files in, run `~/voice/.venv/bin/python ~/rag/rag.py build`, and it answers from them with page citations. Students can do this without sudo.

**Recognising the equipment (the camera): a custom YOLO, compiled for the Hailo-10H.** The detector knows the 80 COCO classes (person, cup, laptop ...), not "H2D printer" or "xTool". Training your own detector is a real project, roughly a weekend for someone comfortable with Python; the compile step is where people get stuck.

1. **Photos and labels.** A few hundred photos of each machine from different angles, distances and lighting, with boxes drawn around them. [Roboflow](https://roboflow.com) is the usual tool and exports straight to YOLO format. This is the students' part.
2. **Train.** YOLOv8n/s or YOLO11n/s with [Ultralytics](https://docs.ultralytics.com) on the Mac (an hour or two for a small model) or free on Google Colab. Not on the Pi. Small models only: the HAT runs `yolov11m` at 15 fps now; a nano/small model is faster and easier to compile.
3. **Compile to a HEF.** The awkward step. Hailo's Dataflow Compiler (DFC) is x86-64 Linux only, downloaded from the [Developer Zone](https://hailo.ai/developer-zone/), and the Hailo-10H needs its own DFC package, not the common Hailo-8 one (the Hailo-8 CLI rejects `--hw-arch hailo10h`). It needs a Linux PC, a cloud VM or an x86 Docker container, not the Mac; a calibration set of a few hundred representative images (Ultralytics recommends ~1,000 for production accuracy; INT8 only); and a DFC version that matches the HailoRT on the Pi (5.3.0: a HEF compiled for another version fails with `HAILO_NOT_IMPLEMENTED`). The community pattern is `hailomz compile yolov8s --hw-arch hailo10h --ckpt model.onnx --calib-path calib/ --yaml yolov8s.yaml --classes N`. Ultralytics 8.4.97 reportedly added direct Hailo-10H HEF export (`yolo export format=hailo`), unverified here, and still x86.
4. **Deploy.** Get `model.hef` onto the Pi into `~/hailo-live/` (USB stick, or `scp` from the machine you compiled on), then in `hailo-live/live_yolo.py` set `HEF` to it and replace the `COCO` tuple with your class names in training order; `./deploy.sh --local` (after committing the change to the repo, or edit the copy in `~/hailo-live/` directly) and the service picks it up. The NMS runs on the chip, so the output format does not change. Test first with `live_yolo.py --image photo.jpg --out out.jpg`.

**The shortcut that needs no training:** the vision-language model (`vlm_test.py`) already recognises "a 3D printer" or "a laser cutter" from a camera frame because it understands open vocabulary. It cannot run while the chat LLM is loaded, so it is a demo, not a live feature.

Sources: [custom HEF with DFC and model zoo](https://community.hailo.ai/t/creating-custom-hef-using-dfc-model-zoo/739), [training with Roboflow](https://community.hailo.ai/t/training-with-roboflow/19190), [YOLOv8 ONNX to HEF](https://community.hailo.ai/t/converting-yolov8n-onnx-to-hef-on-windows/17835), [YOLO on RPi5 Hailo-10H](https://github.com/MichalAnatolSkora/yolo-on-rpi5-hailo10h), [Ultralytics 8.4.97 notes](https://newreleases.io/project/pypi/ultralytics/release/8.4.97).

## To do

- **Hardware on order:** the official 27 W supply (fixes the brownouts) and a 64 GB SD card from a known brand (first full run of `setup-pi.sh` stages 3 onward).
- **Never heard out loud:** attach a speaker or an HDMI display with audio and listen to an answer.
- **Live human voice on the mic** has only been tested with WAV files and typing; run `assistant.py --confirm --no-tts` with students in the real room and add repeated mis-hearings to `stt_fix.py`.
- **Documents:** replace the printer manuals with the real Moonlighter lesson documents; decide whether off-topic questions should be refused ("not in my documents") instead of answered from the model's memory.
- **Optional:** bootloader EEPROM update (`sudo rpi-eeprom-update -a`); `qwen3:1.7b` from the 5.3.0 zoo is untested; HTTPS for the page so hold-to-talk works from phones.

## Sources

- [Raspberry Pi AI software docs](https://www.raspberrypi.com/documentation/computers/ai.html) — Hailo driver and LLM install steps
- [Hailo GenAI model zoo](https://github.com/hailo-ai/hailo_model_zoo_genai) — models, hailo-ollama usage, changelog; [Hailo community forum](https://community.hailo.ai) for the 5.3.0 driver patch and sharing threads
- [raspberrypi/linux #7230](https://github.com/raspberrypi/linux/issues/7230) — the `cma=` firmware mailbox bug
- [pi-private-ai-server](https://github.com/btstevens1984az/pi-private-ai-server) — reference for `hailo-ollama`, the systemd unit and the RAG approach
- [Pi AI Guide (Moonlighter Maker Space)](https://aimoonlighter.howto.rocks) — the program this is built for, repo at github.com/EmilMoonlighter/AI-Program
- [Vosk models](https://alphacephei.com/vosk/models), [Piper voices](https://github.com/rhasspy/piper), [fastembed](https://github.com/qdrant/fastembed)
