#!/usr/bin/env python3
"""
Measure Vosk speech-to-text accuracy and speed on a set of WAV files.

Each line of the manifest is "<file.wav>|<expected transcript>". Every WAV must
be 16 kHz, mono, 16-bit. For each model directory given, the script
transcribes every file and reports word error rate (WER), the number of
sentences transcribed exactly, and the processing speed relative to real time.

Usage:
  ~/voice/.venv/bin/python ~/voice/stt_bench.py [--fix] manifest.txt ~/voice/models/small ~/voice/models/vosk-model-en-us-0.22
  --fix also runs each transcript through stt_fix.fix() (the vocabulary corrections) before scoring.
"""
import json
import os
import sys
import time
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stt_fix  # noqa: E402

RATE = 16000


def word_errors(ref, hyp):
    """Levenshtein distance between word lists (substitutions + insertions + deletions)."""
    r, h = ref.split(), hyp.split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)], len(r)


def transcribe(model, path):
    rec = KaldiRecognizer(model, RATE)
    with wave.open(path, "rb") as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1 and w.getsampwidth() == 2, path
        audio_s = w.getnframes() / RATE
        t0 = time.time()
        while True:
            data = w.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
        text = json.loads(rec.FinalResult()).get("text", "")
        return text, audio_s, time.time() - t0


def main():
    args = sys.argv[1:]
    use_fix = "--fix" in args
    args = [a for a in args if a != "--fix"]
    if len(args) < 2:
        sys.exit(__doc__)
    manifest, model_dirs = args[0], args[1:]
    base = os.path.dirname(os.path.abspath(manifest))
    items = []
    for line in open(manifest):
        line = line.strip()
        if line and "|" in line:
            f, ref = line.split("|", 1)
            items.append((os.path.join(base, f), ref.strip().lower()))

    SetLogLevel(-1)
    for mdir in model_dirs:
        t0 = time.time()
        model = Model(mdir)
        load_s = time.time() - t0
        errs = words = exact = 0
        audio_total = proc_total = 0.0
        misses = []
        for path, ref in items:
            hyp, audio_s, proc_s = transcribe(model, path)
            if use_fix:
                hyp = stt_fix.fix(hyp)
            e, n = word_errors(ref, hyp)
            errs += e
            words += n
            exact += (hyp == ref)
            audio_total += audio_s
            proc_total += proc_s
            if hyp != ref:
                misses.append((os.path.basename(path), ref, hyp))
        print(f"=== {os.path.basename(mdir.rstrip('/'))}" + (" + stt_fix" if use_fix else ""))
        print(f"load {load_s:.1f}s | WER {100 * errs / max(words, 1):.1f}% ({errs}/{words} words) | "
              f"exact {exact}/{len(items)} | speed {audio_total / max(proc_total, 1e-9):.1f}x real time")
        for f, ref, hyp in misses[:12]:
            print(f"   {f}: '{ref}' -> '{hyp}'")
        if len(misses) > 12:
            print(f"   ... and {len(misses) - 12} more")
        print()


if __name__ == "__main__":
    main()
