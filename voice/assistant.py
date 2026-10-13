#!/usr/bin/env python3
"""
Voice -> LLM -> voice assistant for the Pi.

Listens on the USB mic with Vosk (offline speech to text), sends what it hears
to hailo-ollama (the LLM on the AI HAT+ 2), and speaks the reply with Piper
(offline text to speech) through the default audio output.

The LLM reply is streamed; each sentence is spoken as soon as it is complete,
so the first words come out before the whole answer is generated. While the
assistant is speaking, mic audio is dropped so it does not hear itself.

Usage:
  ~/voice/.venv/bin/python ~/voice/assistant.py             # listen on the mic
  ~/voice/.venv/bin/python ~/voice/assistant.py --wav q.wav  # feed a 16 kHz mono WAV instead
  ~/voice/.venv/bin/python ~/voice/assistant.py --text       # type questions instead of speaking
  options: --wake "hey pi"     only answer utterances that start with this phrase
           --model NAME        hailo-ollama model (default qwen2.5-instruct:1.5b)
           --no-tts            print only, do not speak
           --out pw|hdmi|usb|DEVICE
                               "pw" (default) plays via pw-play to PipeWire's default sink
                               (HDMI if a display is attached, else a USB speaker if present);
                               "hdmi" or "usb" force that output via aplay;
                               anything else is an ALSA device name for aplay (e.g. plughw:CARD=X)

Say "stop listening" to quit.
"""
import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave

import requests
from vosk import KaldiRecognizer, Model, SetLogLevel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stt_fix  # noqa: E402  (vocabulary corrections for this project's words)

RATE = 16000
# Speech-to-text models. On our 60-utterance test set (stt_bench.py), with the
# stt_fix corrections both score 6.9% word error rate; without them the small
# model is 11.3% and the big one 10.0%. The big model (2.7 GB on disk) takes
# 10-40 s to load and slowed the LLM's first response, so small is the default.
STT_MODELS = {
    "small": "/home/admin/voice/model",
    "big": "/home/admin/voice/models/vosk-model-en-us-0.22",
}
DEVICE = "usbmic"
LLM_URL = "http://127.0.0.1:8000/api/chat"
DEFAULT_MODEL = "qwen2.5-instruct:1.5b"
PIPER_VOICE = "/home/admin/voice/piper/en_US-lessac-medium.onnx"
HISTORY_TURNS = 4  # user+assistant pairs kept as context

# Short answers: the Hailo runs ~7 tokens/s, so long replies feel slow.
# The transcript hint helps the model read through speech-recognition errors.
SYSTEM_PROMPT = (
    "You are a friendly voice assistant running on a Raspberry Pi. "
    "Answer in one or two short sentences. Do not use lists or markdown. "
    "The user's words come from speech recognition and may contain mis-heard "
    "words; answer the most likely intended question."
)

STOP_PHRASES = {"stop listening", "stop", "goodbye"}
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Every heard question and answer is appended here as one JSON line, so the
# web page (web/app.py) can show a live transcript of the voice assistant.
TRANSCRIPT_LOG = "/home/admin/voice/transcript.jsonl"


def log_event(kind, text):
    try:
        with open(TRANSCRIPT_LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "kind": kind, "text": text}) + "\n")
    except OSError:
        pass


def resolve_alsa_device(name):
    """Map the shortcuts "hdmi" and "usb" to ALSA device names; pass others through.

    "hdmi" is the first HDMI port (needs a display with audio connected).
    "usb" is the first USB playback card found by `aplay -l`.
    """
    if name == "hdmi":
        return "plughw:CARD=vc4hdmi0,DEV=0"
    if name == "usb":
        out = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            m = re.match(r"card \d+: (\S+) \[.*USB.*\]", line)
            if m:
                return f"plughw:CARD={m.group(1)},DEV=0"
        return "plughw:CARD=USB,DEV=0"  # will fail with a clear notice if absent
    return name


class Speaker:
    """Piper text-to-speech played through pw-play or aplay. speak() blocks until done."""

    def __init__(self, enabled, out_device):
        self.enabled = enabled
        self.out_device = out_device
        self.speaking = False
        self.failed = False  # set after the first playback failure; we keep going silently
        if enabled:
            from piper import PiperVoice
            self.voice = PiperVoice.load(PIPER_VOICE)

    def speak(self, text):
        text = text.strip()
        if not self.enabled or self.failed or not text:
            return
        rate = str(self.voice.config.sample_rate)
        if self.out_device == "pw":
            # PipeWire: plays to the current default sink (HDMI when a display is
            # connected, or a USB speaker once one is plugged in)
            cmd = ["pw-play", "--raw", "--format=s16", "--rate=" + rate, "--channels=1", "-"]
        else:
            cmd = ["aplay", "-q", "-D", resolve_alsa_device(self.out_device),
                   "-f", "S16_LE", "-c", "1", "-r", rate, "-t", "raw"]
        self.speaking = True
        try:
            player = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for chunk in self.voice.synthesize(text):
                    player.stdin.write(chunk.audio_int16_bytes)
                player.stdin.close()
            except BrokenPipeError:
                pass
            player.wait()
            if player.returncode != 0:
                err = player.stderr.read().decode(errors="replace").strip().splitlines()
                print(f"\n[TTS off: {cmd[0]} failed on output '{self.out_device}': "
                      f"{err[-1] if err else 'unknown error'}. Is a speaker connected?]", flush=True)
                self.failed = True
        finally:
            self.speaking = False


def mic_reader(q, speaker, wav_path):
    """Feed raw 16 kHz mono PCM into q. Drops audio while the speaker is talking."""
    if wav_path:
        with wave.open(wav_path, "rb") as w:
            assert w.getnchannels() == 1 and w.getframerate() == RATE and w.getsampwidth() == 2, \
                "WAV must be 16 kHz, mono, 16-bit"
            while True:
                data = w.readframes(2000)
                if not data:
                    break
                q.put(data)
        q.put(None)  # end of file
        return
    proc = subprocess.Popen(
        ["arecord", "-q", "-D", DEVICE, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE,
    )
    try:
        while True:
            data = proc.stdout.read(4000)
            if not data:
                break
            if not speaker.speaking:
                q.put(data)
    finally:
        proc.terminate()
        q.put(None)


def ask_llm(model, history, question, speaker):
    """Stream the reply: print it, and speak each sentence as it completes."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": question}
    ]
    t0 = time.time()
    first_word = None
    reply, pending = [], ""
    with requests.post(LLM_URL, json={"model": model, "messages": messages, "stream": True},
                       stream=True, timeout=300) as r:
        r.raise_for_status()
        print("ASSISTANT: ", end="", flush=True)
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                if first_word is None:
                    first_word = time.time() - t0
                print(piece, end="", flush=True)
                reply.append(piece)
                pending += piece
                # Speak complete sentences, keep the tail for the next round
                parts = SENTENCE_END.split(pending)
                for sentence in parts[:-1]:
                    speaker.speak(sentence)
                pending = parts[-1]
            if chunk.get("done"):
                break
    speaker.speak(pending)
    print(f"\n   (first word {first_word or 0:.1f} s, total {time.time() - t0:.1f} s)", flush=True)
    return "".join(reply).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", help="read audio from this 16 kHz mono WAV instead of the mic")
    ap.add_argument("--text", action="store_true", help="type questions on the keyboard instead of using the mic")
    ap.add_argument("--stt-model", default="small", help='speech model: "small" (default), "big", or a Vosk model directory')
    ap.add_argument("--confirm", action="store_true", help='say "I heard: ..." before answering, so mis-hearings are obvious')
    ap.add_argument("--no-fix", action="store_true", help="disable the vocabulary corrections in stt_fix.py")
    ap.add_argument("--wake", default="", help="wake phrase that must start each request")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-tts", action="store_true", help="print replies only, do not speak")
    ap.add_argument("--out", default="pw",
                    help='"pw" (PipeWire default sink), "hdmi", "usb", or an ALSA device name for aplay')
    args = ap.parse_args()
    wake = args.wake.lower().strip()

    speaker = Speaker(enabled=not args.no_tts, out_device=args.out)
    history = []

    if args.text:
        # Keyboard mode: same LLM prompt, history and speech, no Vosk.
        print("Type a question and press Enter. Empty line or Ctrl-D to quit.", flush=True)
        while True:
            try:
                text = input("YOU: ").strip()
            except EOFError:
                print()
                break
            if not text or text.lower() in STOP_PHRASES:
                break
            try:
                answer = ask_llm(args.model, history, text, speaker)
            except requests.RequestException as e:
                print(f"LLM error: {e}", flush=True)
                continue
            history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
            history = history[-2 * HISTORY_TURNS:]
        return

    SetLogLevel(-1)
    model_dir = STT_MODELS.get(args.stt_model, args.stt_model)
    if not os.path.isdir(model_dir):
        print(f"Speech model not found at {model_dir}, falling back to the small model.", flush=True)
        model_dir = STT_MODELS["small"]
    print(f"Loading speech model {model_dir} ...", flush=True)
    rec = KaldiRecognizer(Model(model_dir), RATE)  # free-form, no grammar

    q = queue.Queue()
    threading.Thread(target=mic_reader, args=(q, speaker, args.wav), daemon=True).start()

    print("Listening." + (f' Start with "{wake}".' if wake else "") + " Say 'stop listening' to quit.", flush=True)
    while True:
        data = q.get()
        if data is None:
            # End of WAV input: flush the recognizer
            text = json.loads(rec.FinalResult()).get("text", "").strip() if args.wav else ""
            if not text:
                break
        elif rec.AcceptWaveform(data):
            text = json.loads(rec.Result()).get("text", "").strip()
            if not text:
                continue
        else:
            continue

        raw = text
        if not args.no_fix:
            text = stt_fix.fix(text)
        print(f"HEARD: {text}" + (f"   (raw: {raw})" if text != raw else ""), flush=True)
        log_event("heard", text)
        if text in STOP_PHRASES:
            speaker.speak("Goodbye.")
            break
        if wake:
            if not text.startswith(wake):
                continue
            text = text[len(wake):].strip()
            if not text:
                continue
        if args.confirm:
            speaker.speak(f"I heard: {text}.")
        try:
            answer = ask_llm(args.model, history, text, speaker)
        except requests.RequestException as e:
            print(f"LLM error: {e}", flush=True)
            speaker.speak("Sorry, I could not reach the language model.")
            continue
        log_event("answer", answer)
        history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        history = history[-2 * HISTORY_TURNS:]
        if data is None:
            break


if __name__ == "__main__":
    sys.exit(main())
