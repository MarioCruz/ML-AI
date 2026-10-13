"""
Fix known speech-recognition mistakes for this project's vocabulary.

Vosk's general English models do not know words like "pi" or "AI HAT", so
they substitute common homophones. These rules map the mistakes we have
actually observed (see stt_bench.py output) back to the intended words.
Keep the list short and specific: every rule here was seen in testing.
Students can add their own topic words the same way.
"""
import re

# (pattern, replacement) applied in order to the lower-cased transcript.
RULES = [
    (r"\braspberry pie\b", "raspberry pi"),
    (r"\b(to|on|with|for|the|a) pie\b", r"\1 pi"),
    (r"\bpie\b", "pi"),
    (r"\b(a i|the i|all you|i|eye) (hat|had|hats)\b", "ai hat"),
    (r"\bai hat (to|too)\b", "ai hat do"),
    (r"\bname free\b", "name three"),
    (r"\bsenses\b", "sensors"),
    (r"\btrain and module\b", "train a model"),
]

_COMPILED = [(re.compile(p), r) for p, r in RULES]


def fix(text):
    """Return the transcript with the known mistakes corrected."""
    text = text.lower()
    for pattern, repl in _COMPILED:
        text = pattern.sub(repl, text)
    return text
