#!/usr/bin/env python3
"""
Web front end for the Pi assistant. Runs on port 8002.

  http://<pi-ip>:8002/

- Chat: text in, streamed reply out, from the LLM on the AI HAT+ 2 (hailo-ollama).
  Same system prompt and history rules as voice/assistant.py.
- Speak: when the toggle is on, each sentence of the reply is spoken through the
  Pi's audio output (Piper) while the text keeps streaming.
- Talk: hold the button, speak into the laptop/phone mic; the audio is sent to
  the Pi, transcribed with Vosk + stt_fix, and put in the chat box.
- Transcript: live view of what the voice assistant (assistant.py) hears and
  answers, read from ~/voice/transcript.jsonl.
- Camera: shows ~/hailo-live/live/latest.jpg when the live YOLO pipeline runs.

Run:  ~/voice/.venv/bin/python ~/web/app.py
Needs: flask in the voice venv (pip install flask), ffmpeg (for browser audio).
"""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

import requests
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

VOICE_DIR = "/home/admin/voice"
sys.path.insert(0, VOICE_DIR)
import stt_fix  # noqa: E402
from assistant import (DEFAULT_MODEL, HISTORY_TURNS, LLM_URL, RATE, STT_MODELS,  # noqa: E402
                       SYSTEM_PROMPT, TRANSCRIPT_LOG, Speaker)
from vosk import KaldiRecognizer, Model, SetLogLevel  # noqa: E402

PORT = 8002
CAMERA_FRAME = "/home/admin/hailo-live/live/latest.jpg"
# LLM servers the page can talk to. Both speak the Ollama API.
BACKENDS = {
    "hailo": "http://127.0.0.1:8000",   # hailo-ollama: models run on the AI HAT+ 2
    "cpu": "http://127.0.0.1:11434",    # stock Ollama: models run on the Pi's CPU
}
DEFAULT_CHOICE = "hailo|" + DEFAULT_MODEL  # picker value is "<backend>|<model>"
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
HERE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)

# One shared conversation for the page (it is a classroom demo, not a multi-user app).
history = []
history_lock = threading.Lock()


class SpeechQueue:
    """Speaks sentences in order on a background thread so chat text never waits."""

    def __init__(self):
        self.q = queue.Queue()
        self.speaker = Speaker(enabled=True, out_device=os.environ.get("ASSISTANT_OUT", "pw"))
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            text = self.q.get()
            try:
                self.speaker.speak(text)
            except Exception as e:  # keep the worker alive
                print(f"speak failed: {e}", flush=True)

    def say(self, text):
        if text.strip():
            self.q.put(text)


speech = SpeechQueue()

SetLogLevel(-1)
stt_model = Model(STT_MODELS["small"])


@app.get("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.post("/api/chat")
def chat():
    body = request.get_json(force=True)
    message = (body.get("message") or "").strip()
    speak = bool(body.get("speak"))
    choice = body.get("model") or DEFAULT_CHOICE
    backend, _, model = choice.partition("|")
    if not model:  # plain model name: assume the Hailo
        backend, model = "hailo", backend
    llm_url = BACKENDS.get(backend, BACKENDS["hailo"]) + "/api/chat"
    if not message:
        return jsonify({"error": "empty message"}), 400

    with history_lock:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(history) + [
            {"role": "user", "content": message}
        ]

    def generate():
        reply, pending = [], ""
        t0 = time.time()
        try:
            with requests.post(llm_url, json={"model": model, "messages": messages, "stream": True},
                               stream=True, timeout=300) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        reply.append(piece)
                        pending += piece
                        yield json.dumps({"t": piece}) + "\n"
                        if speak:
                            parts = SENTENCE_END.split(pending)
                            for s in parts[:-1]:
                                speech.say(s)
                            pending = parts[-1]
                    if chunk.get("done"):
                        break
        except requests.RequestException as e:
            yield json.dumps({"error": f"LLM not reachable: {e}"}) + "\n"
            return
        if speak:
            speech.say(pending)
        answer = "".join(reply).strip()
        with history_lock:
            history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": answer}])
            del history[:-2 * HISTORY_TURNS]
        yield json.dumps({"done": True, "seconds": round(time.time() - t0, 1)}) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@app.post("/api/reset")
def reset():
    with history_lock:
        history.clear()
    return jsonify({"ok": True})


@app.post("/api/speak")
def speak_text():
    text = (request.get_json(force=True).get("text") or "").strip()
    speech.say(text)
    return jsonify({"ok": True})


@app.post("/api/transcribe")
def transcribe():
    """Browser audio (webm/opus or similar) -> ffmpeg -> 16 kHz mono PCM -> Vosk."""
    blob = request.get_data()
    if not blob:
        return jsonify({"error": "no audio"}), 400
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(blob)
        path = f.name
    try:
        pcm = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
            capture_output=True, timeout=60,
        )
        if pcm.returncode != 0:
            return jsonify({"error": "ffmpeg: " + pcm.stderr.decode(errors="replace")[-200:]}), 500
        rec = KaldiRecognizer(stt_model, RATE)
        data = pcm.stdout
        for i in range(0, len(data), 8000):
            rec.AcceptWaveform(data[i:i + 8000])
        raw = json.loads(rec.FinalResult()).get("text", "").strip()
    finally:
        os.unlink(path)
    fixed = stt_fix.fix(raw) if raw else ""
    return jsonify({"text": fixed, "raw": raw, "seconds": round(len(data) / (2 * RATE), 1)})


@app.get("/api/transcript")
def transcript_stream():
    """Server-sent events: new lines of ~/voice/transcript.jsonl as they appear."""
    def tail():
        last = []
        try:
            with open(TRANSCRIPT_LOG) as f:
                last = f.readlines()[-20:]
        except OSError:
            pass
        for line in last:
            yield "data: " + line.strip() + "\n\n"
        pos = os.path.getsize(TRANSCRIPT_LOG) if os.path.exists(TRANSCRIPT_LOG) else 0
        while True:
            if os.path.exists(TRANSCRIPT_LOG):
                size = os.path.getsize(TRANSCRIPT_LOG)
                if size < pos:
                    pos = 0  # file was truncated
                if size > pos:
                    with open(TRANSCRIPT_LOG) as f:
                        f.seek(pos)
                        for line in f:
                            if line.strip():
                                yield "data: " + line.strip() + "\n\n"
                        pos = f.tell()
            yield ": keepalive\n\n"
            time.sleep(0.5)

    return Response(tail(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def camera_live():
    """True only if the live pipeline wrote a frame in the last few seconds."""
    try:
        return time.time() - os.path.getmtime(CAMERA_FRAME) < 5
    except OSError:
        return False


@app.get("/api/camera")
def camera():
    if not camera_live():
        return jsonify({"error": "live camera not running (start ~/hailo-live/run_live.sh)"}), 404
    return send_file(CAMERA_FRAME, mimetype="image/jpeg", max_age=0)


@app.get("/api/status")
def status():
    """Models from every reachable backend, as {"id": "<backend>|<model>", "label": ...}."""
    choices, reachable = [], []
    for backend, base in BACKENDS.items():
        try:
            models = requests.get(base + "/api/tags", timeout=3).json().get("models", [])
        except Exception:
            continue
        reachable.append(backend)
        for m in models:
            name = m["name"]
            choices.append({"id": f"{backend}|{name}",
                            "label": f"{name}  ({'AI HAT+ 2' if backend == 'hailo' else 'Pi CPU'})"})
    return jsonify({
        "models": choices,
        "default": DEFAULT_CHOICE,
        "backends": reachable,
        "llm_models": [c["id"] for c in choices],  # kept for older clients
        "camera": camera_live(),
        "history_turns": len(history) // 2,
    })


if __name__ == "__main__":
    print(f"Pi assistant web UI on http://0.0.0.0:{PORT}/", flush=True)
    app.run(host="0.0.0.0", port=PORT, threaded=True)
